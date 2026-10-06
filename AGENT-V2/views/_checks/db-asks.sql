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
-- Q. QA, ONE STATEMENT (deploy-check C09, 2026-10-05: IS_CALLABLE and IS_TAP
-- are non-NULL on every QA DCM tranche, unlike UAT). What do the six flags
-- store in QA? One scan of the DCM tranche branch (~15 s), ~50 rows.
-- ===========================================================================
SELECT IS_CALLABLE, IS_TAP, IS_CONVERTIBLE, IS_PUTTABLE, MAKE_WHOLE_CALLABLE, IS_PERPETUAL,
       COUNT(*) AS TRANCHES
FROM   DGSTREAM.VW_TRANCHE_SUMMARY
WHERE  PRODUCT = 'DCM'
GROUP  BY IS_CALLABLE, IS_TAP, IS_CONVERTIBLE, IS_PUTTABLE, MAKE_WHOLE_CALLABLE, IS_PERPETUAL
ORDER  BY TRANCHES DESC;

-- ===========================================================================
-- R. DCM ALLOCATION SOURCE (UAT, before deploying the order + deal views).
-- User 2026-10-06: OB_ORDER.FINAL_ALLOC is not populated for DCM — the
-- allocation sits on OB_ORDER_MATCH_GROUP.FINAL_ALLOC, matched through
-- PRIMARY_ORDER_ID. The views now read NVL(group, order). Four statements
-- confirm coverage, keys and precedence. SELECTs only.
-- ===========================================================================

-- R1. The match-group table itself: rows, distinct primary orders, how many
--     carry FINAL_ALLOC, and the STATUS / ITEM_SOURCE vocabularies.
SELECT STATUS, ITEM_SOURCE,
       COUNT(*) AS ROWS_,
       COUNT(DISTINCT PRIMARY_ORDER_ID) AS PRIMARY_ORDERS,
       COUNT(FINAL_ALLOC) AS WITH_FINAL_ALLOC,
       COUNT(CASE WHEN FINAL_ALLOC > 0 THEN 1 END) AS POSITIVE_ALLOC,
       COUNT(CASE WHEN PRIMARY_ORDER_ID IS NULL THEN 1 END) AS NO_PRIMARY
FROM   DGSTREAM.OB_ORDER_MATCH_GROUP
GROUP  BY STATUS, ITEM_SOURCE
ORDER  BY ROWS_ DESC;

-- R2. Coverage of in-scope DCM orders (non-RQ, status in scope, latest row
--     per order) by a group row on PRIMARY_ORDER_ID, and whether the group's
--     ROOT_ID / PARENT_ID agree with the order's (the view joins on all three).
WITH O AS (
  SELECT ORDER_ID, ROOT_ID, PARENT_ID, FINAL_ALLOC
  FROM (
    SELECT ORDER_ID, ROOT_ID, PARENT_ID, FINAL_ALLOC,
           ROW_NUMBER() OVER (PARTITION BY ROOT_ID, PARENT_ID, ORDER_ID ORDER BY ROWID) AS RN_
    FROM   DGSTREAM.OB_ORDER
    WHERE  ORDER_ID IS NOT NULL
    AND    (ITEM_SOURCE IS NULL OR UPPER(ITEM_SOURCE) <> 'RQ')
    AND    (STATUS IS NULL OR UPPER(STATUS) NOT IN ('DELETED', 'CANCELLED'))
  ) WHERE RN_ = 1
), G AS (
  SELECT PRIMARY_ORDER_ID, ROOT_ID, PARENT_ID, FINAL_ALLOC
  FROM (
    SELECT PRIMARY_ORDER_ID, ROOT_ID, PARENT_ID, FINAL_ALLOC,
           ROW_NUMBER() OVER (PARTITION BY PRIMARY_ORDER_ID ORDER BY DG_VERSION DESC, ROWID) AS RN_
    FROM   DGSTREAM.OB_ORDER_MATCH_GROUP
    WHERE  PRIMARY_ORDER_ID IS NOT NULL
  ) WHERE RN_ = 1
)
SELECT COUNT(*) AS ORDERS_IN_SCOPE,
       COUNT(G.PRIMARY_ORDER_ID) AS WITH_GROUP,
       COUNT(CASE WHEN G.FINAL_ALLOC IS NOT NULL THEN 1 END) AS GROUP_ALLOC,
       COUNT(CASE WHEN G.FINAL_ALLOC > 0 THEN 1 END) AS GROUP_ALLOC_POSITIVE,
       COUNT(CASE WHEN O.FINAL_ALLOC IS NOT NULL THEN 1 END) AS ORDER_ALLOC,
       COUNT(CASE WHEN G.PRIMARY_ORDER_ID IS NOT NULL
                   AND (G.ROOT_ID <> O.ROOT_ID OR G.PARENT_ID <> O.PARENT_ID) THEN 1 END) AS KEY_MISMATCH
FROM   O
LEFT JOIN G ON G.PRIMARY_ORDER_ID = O.ORDER_ID;

-- R3. Precedence: where BOTH the order and its group carry FINAL_ALLOC, do
--     they agree? (The view takes the group's.)
SELECT CASE WHEN O.FINAL_ALLOC = G.FINAL_ALLOC THEN 'EQUAL'
            WHEN O.FINAL_ALLOC = 0 THEN 'ORDER ZERO, GROUP SET'
            ELSE 'DIFFER' END AS CMP,
       COUNT(*) AS ORDERS_
FROM   DGSTREAM.OB_ORDER O
JOIN   DGSTREAM.OB_ORDER_MATCH_GROUP G ON G.PRIMARY_ORDER_ID = O.ORDER_ID
WHERE  O.FINAL_ALLOC IS NOT NULL AND G.FINAL_ALLOC IS NOT NULL
GROUP  BY CASE WHEN O.FINAL_ALLOC = G.FINAL_ALLOC THEN 'EQUAL'
               WHEN O.FINAL_ALLOC = 0 THEN 'ORDER ZERO, GROUP SET'
               ELSE 'DIFFER' END;

-- R4 (OPTIONAL). The rest of the allocation block — is it also on the group
--     only? Populations on OB_ORDER vs the match group.
SELECT 'OB_ORDER' AS SRC, COUNT(*) AS ROWS_, COUNT(DRAFT_ALLOC) AS DRAFT_, COUNT(SOFT_ALLOC) AS SOFT_,
       COUNT(ISN_ALLOC) AS ISN_, COUNT(RETENTION) AS RETENTION_, COUNT(RATIONALE) AS RATIONALE_,
       COUNT(FX_CURRENCY) AS FX_, COUNT(ESG_TAG) AS ESG_, COUNT(BND) AS BND_
FROM   DGSTREAM.OB_ORDER
WHERE  (ITEM_SOURCE IS NULL OR UPPER(ITEM_SOURCE) <> 'RQ')
UNION ALL
SELECT 'OB_ORDER_MATCH_GROUP', COUNT(*), COUNT(DRAFT_ALLOC), COUNT(SOFT_ALLOC), COUNT(ISN_ALLOC),
       COUNT(RETENTION), COUNT(RATIONALE), COUNT(FX_CURRENCY), COUNT(ESG_TAG), COUNT(BND)
FROM   DGSTREAM.OB_ORDER_MATCH_GROUP;
