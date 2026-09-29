-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on QA and
-- screenshot into ~/Desktop/ADK. SELECTs only, never session settings.
-- ===========================================================================

-- AFTER THE NEXT VIEW DEPLOY (DCM status exclusion 2026-09-28 + allocation
-- NULL 2026-09-29 — the SAME order-view file, re-copy it): views/_deploy-check.sql
-- sections B-DCM, C, D-ECM and D-DCM. New rows: 27 / 27b (deal count and no
-- excluded status), 25 / 25b (tranche), 26 / 26b / 26c (order statuses in
-- scope, row count ~1.25M, no NULL status), 28 / 28b (orders with no
-- allocation recorded, by product — INFO, expect > 0 now).

-- ===========================================================================
-- L. PO ECM LABELLING FEEDBACK 2026-09-29 (UAT, before the deploy above).
-- Four statements, run as a script. Results into ~/Desktop/ADK.
-- ===========================================================================

-- L1. Equity-type vocabulary on ECM deals (PO item 4: 'IPO' / 'Equity' show
--     up in the SECURITY column — they are deal types recorded as the equity
--     type at source). Counts per value, split by offering type and source.
SELECT EQUITY_TYPE, OFFERING_TYPE, COUNT(*) AS DEALS,
       COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN 1 END) AS IPREO_DEALS,
       TO_CHAR(MIN(FIRST_PRICED), 'YYYY-MM-DD') AS EARLIEST,
       TO_CHAR(MAX(FIRST_PRICED), 'YYYY-MM-DD') AS LATEST
FROM   DGSTREAM.VW_DEAL_SUMMARY
WHERE  PRODUCT = 'ECM'
GROUP  BY EQUITY_TYPE, OFFERING_TYPE
ORDER  BY DEALS DESC;

-- L2. The deals behind the odd values — the names say whether they are real.
SELECT DEAL_ID, DEAL_NAME, EQUITY_TYPE, OFFERING_TYPE,
       TO_CHAR(FIRST_PRICED, 'YYYY-MM-DD') AS PRICED, DEAL_SIZE
FROM   DGSTREAM.VW_DEAL_SUMMARY
WHERE  PRODUCT = 'ECM' AND EQUITY_TYPE IN ('IPO', 'Ipo', 'Equity', 'EQUITY')
ORDER  BY FIRST_PRICED DESC NULLS LAST
FETCH FIRST 20 ROWS ONLY;

-- L3. Allocation at source: NULL vs 0 vs positive (PO item 2 — the view has
--     been turning NULL into 0). Base tables carry every DG version, so read
--     these as proportions. One statement per source.
SELECT 'OB_ECM_ORDER' AS SRC, ALLOCATION_STATUS,
       CASE WHEN PRIVATE_ALLOC IS NULL THEN 'NULL' WHEN PRIVATE_ALLOC = 0 THEN 'ZERO' ELSE 'POSITIVE' END AS ALLOC,
       COUNT(*) AS ROWS_
FROM   DGSTREAM.OB_ECM_ORDER
GROUP  BY ALLOCATION_STATUS,
          CASE WHEN PRIVATE_ALLOC IS NULL THEN 'NULL' WHEN PRIVATE_ALLOC = 0 THEN 'ZERO' ELSE 'POSITIVE' END
ORDER  BY 1, 2, 3;

SELECT 'IPREO_OB_ECM_ORDER' AS SRC,
       CASE WHEN PRIVATE_ALLOC IS NULL THEN 'NULL' WHEN PRIVATE_ALLOC = 0 THEN 'ZERO' ELSE 'POSITIVE' END AS ALLOC,
       COUNT(*) AS ROWS_
FROM   DGSTREAM.IPREO_OB_ECM_ORDER
GROUP  BY CASE WHEN PRIVATE_ALLOC IS NULL THEN 'NULL' WHEN PRIVATE_ALLOC = 0 THEN 'ZERO' ELSE 'POSITIVE' END
ORDER  BY 2;

SELECT 'OB_ORDER (non-RQ)' AS SRC,
       CASE WHEN FINAL_ALLOC IS NULL THEN 'NULL' WHEN FINAL_ALLOC = 0 THEN 'ZERO' ELSE 'POSITIVE' END AS ALLOC,
       COUNT(*) AS ROWS_
FROM   DGSTREAM.OB_ORDER
WHERE  (ITEM_SOURCE IS NULL OR UPPER(ITEM_SOURCE) <> 'RQ')
GROUP  BY CASE WHEN FINAL_ALLOC IS NULL THEN 'NULL' WHEN FINAL_ALLOC = 0 THEN 'ZERO' ELSE 'POSITIVE' END
ORDER  BY 2;
