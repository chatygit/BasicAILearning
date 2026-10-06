-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on QA and
-- screenshot into ~/Desktop/ADK. SELECTs only, never session settings.
-- ===========================================================================

-- VIEWS DEPLOYED 2026-09-29 (status exclusion + allocation NULL). RUN NOW:
-- views/_deploy-check.sql A0, then sections B-DCM, C, D-ECM, D-DCM. Rows to
-- read: 27 / 27b (deal count, no excluded status), 25 / 25b (tranche),
-- 26 / 26b / 26c (order statuses in scope, ~1.25M rows, no NULL status),
-- 28 / 28b (orders with no allocation recorded, by product — expect > 0).
--
-- ONE MORE DEPLOY, vw_deal_summary ONLY (PR bot 2026-09-29): the DCM currency
-- roll-up (CU block) now drops cancelled / postponed / deleted / archived
-- tranches like the rest of the branch. After it: A0 + B-DCM again (27 / 27b
-- unchanged; the CURRENCIES column of a deal with a cancelled tranche loses
-- that tranche's currency).

-- BATCH C IS CLEARED TO DEPLOY (db-asks P0, 2026-10-05: all 21 source names
-- valid; the Ipreo mirror carries ISSUER_COUNTRY_NAME, nothing else of the
-- batch). Deploy vw_deal_summary, vw_tranche_summary, vw_order_detail (the
-- deal view also carries the currency roll-up fix from 2026-09-29), then run
-- views/_deploy-check.sql (rewritten 2026-10-05): A0, A (A01-A03 = the three
-- views' column counts 43 / 89 / 65), B-ECM (B08), B-DCM (B14), C (C08 / C09).
-- Sections D-ECM / D-DCM are unchanged by this batch.

-- ===========================================================================
-- T. THE MISSING BOOKS (same environment as S). S1 found ~46.5k allocated
-- match groups whose PRIMARY_ORDER_ID has NO row in OB_ORDER (42,967 of
-- them 'SBB'); the id shape matches, so the orders are simply not loaded.
-- Two statements characterise them for the DataGlobe / orderbook team.
-- ===========================================================================

-- T1. Which deals and years the orphaned allocations belong to, and whether
--     the deal has ANY order in OB_ORDER (a partial book) or none (a book that
--     never arrived).
WITH G AS (
    SELECT MG.ROOT_ID, MG.PARENT_ID, MG.PRIMARY_ORDER_ID, MG.ITEM_SOURCE, MG.FINAL_ALLOC
    FROM   DGSTREAM.OB_ORDER_MATCH_GROUP MG
    WHERE  MG.FINAL_ALLOC > 0 AND MG.PRIMARY_ORDER_ID IS NOT NULL
    AND    NOT EXISTS (SELECT 1 FROM DGSTREAM.OB_ORDER O WHERE O.ORDER_ID = MG.PRIMARY_ORDER_ID)
)
SELECT G.ITEM_SOURCE,
       TO_CHAR(MAX(DT.PRICING_TS), 'YYYY') AS YEAR_,
       CASE WHEN EXISTS (SELECT 1 FROM DGSTREAM.OB_ORDER O WHERE O.ROOT_ID = G.ROOT_ID)
            THEN 'deal has other orders' ELSE 'deal has NO orders' END AS BOOK_,
       COUNT(DISTINCT G.ROOT_ID) AS DEALS,
       COUNT(*) AS GROUPS,
       SUM(G.FINAL_ALLOC) AS ALLOCATION
FROM   G
LEFT JOIN DGSTREAM.OB_DEAL_TRANCHE DT ON DT.DEAL_ID = G.ROOT_ID AND DT.TRANCHE_ID = G.PARENT_ID
GROUP  BY G.ITEM_SOURCE, G.ROOT_ID
ORDER  BY GROUPS DESC
FETCH FIRST 40 ROWS ONLY;

-- T2. Ten orphaned SBB groups with their deal names — concrete examples for
--     the feed team (and to spot-check in the source UI).
SELECT MG.ROOT_ID, MAX(DT.DEAL_NAME) AS DEAL_NAME, TO_CHAR(MAX(DT.PRICING_TS), 'YYYY-MM-DD') AS PRICED,
       COUNT(*) AS ORPHANED_GROUPS, SUM(MG.FINAL_ALLOC) AS ALLOCATION
FROM   DGSTREAM.OB_ORDER_MATCH_GROUP MG
LEFT JOIN DGSTREAM.OB_DEAL_TRANCHE DT ON DT.DEAL_ID = MG.ROOT_ID AND DT.TRANCHE_ID = MG.PARENT_ID
WHERE  MG.ITEM_SOURCE = 'SBB' AND MG.FINAL_ALLOC > 0 AND MG.PRIMARY_ORDER_ID IS NOT NULL
AND    NOT EXISTS (SELECT 1 FROM DGSTREAM.OB_ORDER O WHERE O.ORDER_ID = MG.PRIMARY_ORDER_ID)
GROUP  BY MG.ROOT_ID
ORDER  BY ORPHANED_GROUPS DESC
FETCH FIRST 10 ROWS ONLY;
