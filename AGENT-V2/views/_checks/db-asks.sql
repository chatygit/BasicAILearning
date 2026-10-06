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
-- U. CROSS-BANK MATCH GROUPS (UAT). T showed the orphaned SBB allocations are
-- the volume-load deals (Pembina 23,930 groups, Air France-KLM 6,010, the
-- Apple / Microsoft loads of Nov-2024) — not a feed gap. What remains is
-- ~3k ISN / DRB / GSP / GB allocated groups on real deals that DO have other
-- orders: the group's PRIMARY_ORDER_ID is probably another bank's order and
-- OUR order sits in REF_SOURCE_SECONDARY_ORDER_LIST. Two statements.
-- ===========================================================================

-- U1. What the secondary list looks like (format, delimiter) on ten such
--     groups, with the per-source allocation columns beside FINAL_ALLOC.
SELECT MG.ITEM_SOURCE, MG.PRIMARY_ORDER_ID, MG.REF_SOURCE_SECONDARY_ORDER_LIST,
       MG.FINAL_ALLOC, MG.GB_ALLOC, MG.ISN_ALLOC
FROM   DGSTREAM.OB_ORDER_MATCH_GROUP MG
WHERE  MG.FINAL_ALLOC > 0 AND MG.PRIMARY_ORDER_ID IS NOT NULL AND MG.ITEM_SOURCE <> 'SBB'
AND    NOT EXISTS (SELECT 1 FROM DGSTREAM.OB_ORDER O WHERE O.ORDER_ID = MG.PRIMARY_ORDER_ID)
AND    MG.REF_SOURCE_SECONDARY_ORDER_LIST IS NOT NULL
FETCH FIRST 10 ROWS ONLY;

-- U2. Split those groups' secondary lists and look the ids up in OB_ORDER:
--     how many orphaned groups contain one of OUR orders. (Generic delimiter
--     class — commas, pipes, semicolons, spaces, brackets, quotes.)
WITH G AS (
    SELECT MG.ORDER_GROUP_ID, MG.REF_SOURCE_SECONDARY_ORDER_LIST AS L
    FROM   DGSTREAM.OB_ORDER_MATCH_GROUP MG
    WHERE  MG.FINAL_ALLOC > 0 AND MG.PRIMARY_ORDER_ID IS NOT NULL AND MG.ITEM_SOURCE <> 'SBB'
    AND    NOT EXISTS (SELECT 1 FROM DGSTREAM.OB_ORDER O WHERE O.ORDER_ID = MG.PRIMARY_ORDER_ID)
    AND    MG.REF_SOURCE_SECONDARY_ORDER_LIST IS NOT NULL
), X AS (
    SELECT ORDER_GROUP_ID,
           TRIM(REGEXP_SUBSTR(L, '[^,|; \[\]"]+', 1, LEVEL)) AS SEC_ID
    FROM   G
    CONNECT BY LEVEL <= REGEXP_COUNT(L, '[^,|; \[\]"]+')
           AND PRIOR ORDER_GROUP_ID = ORDER_GROUP_ID
           AND PRIOR SYS_GUID() IS NOT NULL
)
SELECT COUNT(DISTINCT X.ORDER_GROUP_ID) AS ORPHANED_GROUPS_WITH_A_LIST,
       COUNT(DISTINCT CASE WHEN O.ORDER_ID IS NOT NULL THEN X.ORDER_GROUP_ID END) AS GROUPS_NAMING_OUR_ORDER,
       COUNT(DISTINCT O.ORDER_ID) AS OUR_ORDERS_FOUND
FROM   X
LEFT JOIN DGSTREAM.OB_ORDER O ON O.ORDER_ID = X.SEC_ID;
