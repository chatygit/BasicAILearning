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
-- AA. ECM ORDER GRAIN FIX — two facts before the view changes (UAT). W showed
-- the 32 duplicates are one perf-test deal (85AA3193) with TWO ECM
-- transaction records: the order view joins the transaction on deal id, so
-- every order of such a deal appears once per transaction (one row with its
-- tranche, one without). The fix keys the tranche join on the tranche id
-- and keeps one transaction per deal; it needs:
-- ===========================================================================

-- AA1. Is ECM_TRANSACTION_TRANCHE_ID unique across transactions? (If the two
--      distinct counts are equal, the tranche id alone identifies a tranche.)
SELECT COUNT(*) AS ROWS_,
       COUNT(DISTINCT ECM_TRANSACTION_TRANCHE_ID) AS DISTINCT_TRANCHE_IDS,
       COUNT(DISTINCT ECM_TRANSACTION_ID || '~' || ECM_TRANSACTION_TRANCHE_ID) AS DISTINCT_PAIRS
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE;

-- AA2. How common is a deal with several ECM transactions, and how many
--      orders sit on them (the blast radius of the fix).
WITH M AS (
    SELECT DEAL_TRANSACTION_ID
    FROM   DGSTREAM.OPUS_ECM_TRANSACTION
    WHERE  DEAL_TRANSACTION_ID IS NOT NULL
    GROUP  BY DEAL_TRANSACTION_ID
    HAVING COUNT(DISTINCT ECM_TRANSACTION_ID) > 1
)
SELECT (SELECT COUNT(*) FROM M) AS MULTI_TXN_DEALS,
       COUNT(DISTINCT O.ORDER_ID) AS ORDERS_ON_THEM
FROM   DGSTREAM.OB_ECM_ORDER O
JOIN   M ON M.DEAL_TRANSACTION_ID = O.DEAL_ID;

-- AB (tiny, with the next round). IPREO_PRODUCTFEE: does it carry DG_VERSION?
-- Its dedupe orders by ROWID for now; switch to DG_VERSION DESC if present.
SELECT COLUMN_NAME FROM ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'IPREO_PRODUCTFEE' AND COLUMN_NAME IN ('DG_VERSION', 'SOURCE_PUBLISHED_TS');
