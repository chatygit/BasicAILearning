-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- PENDING DEPLOY (repo, after PROD commit 43fd526): vw_order_detail — one limit
-- per order (ECM ORDER_AMOUNT = LIMIT_VALUE). After it, on UAT,
-- views/_deploy-check.sql A0 + section D-ECM: D16 must PASS.

-- AF. ONE LINE (UAT). D16 reported PASS, but the UAT order view (recreated
-- 08-Oct 13:55) predates the one-limit fix, so the scaled order you showed on
-- 2026-10-08 (2362660896406: 10 / 20 / 30 on three IOI rows) should still read
-- ORDER_AMOUNT 30 vs LIMIT_VALUE 10. Expect two DIFFERENT numbers until the
-- vw_order_detail redeploy; after it, the same number.
SELECT ORDER_ID, LIMIT_TYPE, LIMIT_VALUE, ORDER_AMOUNT
FROM   DGSTREAM.VW_ORDER_DETAIL
WHERE  PRODUCT = 'ECM' AND ORDER_ID = '2362660896406';

-- ===========================================================================
-- AE. ECM ALLOCATION SOURCE (UAT — PROD is not runnable). A PROD answer showed
-- "Not recorded" allocations for every top investor on Space Exploration
-- Technologies: the ECM order view reads OB_ECM_ORDER.PRIVATE_ALLOC only. Find
-- the same symptom on UAT and see which column carries the allocation there.
-- ===========================================================================

-- AE1. Across the ECM book: how often each other allocation column is filled
--      where PRIVATE_ALLOC is blank, and how often PRIVATE and FINAL disagree.
SELECT COUNT(*) AS ORDER_ROWS,
       COUNT(PRIVATE_ALLOC) AS PRIVATE_,
       COUNT(CASE WHEN PRIVATE_ALLOC IS NULL AND FINAL_ALLOC IS NOT NULL THEN 1 END) AS FINAL_ONLY,
       COUNT(CASE WHEN PRIVATE_ALLOC IS NULL AND DRAFT_ALLOC IS NOT NULL THEN 1 END) AS DRAFT_ONLY,
       COUNT(CASE WHEN PRIVATE_ALLOC IS NULL AND INST_ALLOCATION_QTY IS NOT NULL THEN 1 END) AS INST_ONLY,
       COUNT(CASE WHEN PRIVATE_ALLOC IS NOT NULL AND FINAL_ALLOC IS NOT NULL
                   AND PRIVATE_ALLOC <> FINAL_ALLOC THEN 1 END) AS PRIVATE_NE_FINAL
FROM   DGSTREAM.OB_ECM_ORDER;

-- AE2. The PROD symptom on UAT: ECM deals with 20+ orders where NO order has
--      PRIVATE_ALLOC — the 15 largest, with every other allocation column and
--      the allocation status. (Space Exploration is included if UAT has it.)
SELECT O.DEAL_ID, MAX(ET.SYNDICATE_DEAL_NAME) AS DEAL_NAME,
       COUNT(DISTINCT O.ORDER_ID) AS ORDERS_,
       MAX(O.ALLOCATION_STATUS) AS SOME_ALLOC_STATUS,
       COUNT(O.FINAL_ALLOC) AS FINAL_, SUM(O.FINAL_ALLOC) AS FINAL_SUM,
       COUNT(O.DRAFT_ALLOC) AS DRAFT_, SUM(O.DRAFT_ALLOC) AS DRAFT_SUM,
       COUNT(O.INST_ALLOCATION_QTY) AS INST_, SUM(O.INST_ALLOCATION_QTY) AS INST_SUM
FROM   DGSTREAM.OB_ECM_ORDER O
LEFT JOIN (SELECT DEAL_TRANSACTION_ID, MAX(SYNDICATE_DEAL_NAME) AS SYNDICATE_DEAL_NAME
           FROM DGSTREAM.OPUS_ECM_TRANSACTION GROUP BY DEAL_TRANSACTION_ID) ET
       ON ET.DEAL_TRANSACTION_ID = O.DEAL_ID
GROUP  BY O.DEAL_ID
HAVING COUNT(O.PRIVATE_ALLOC) = 0 AND COUNT(DISTINCT O.ORDER_ID) >= 20
ORDER  BY CASE WHEN UPPER(MAX(ET.SYNDICATE_DEAL_NAME)) LIKE '%SPACE EXPLORATION%' THEN 0 ELSE 1 END,
          ORDERS_ DESC
FETCH FIRST 15 ROWS ONLY;
