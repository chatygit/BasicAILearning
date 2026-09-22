-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on the
-- environment where the views are deployed and screenshot into ~/Desktop/ADK.
-- A section is deleted once its results are recorded. (N5-1 deal cards and
-- N5-4 fee sample of 2026-09-22 are recorded.)
-- ===========================================================================


-- ===========================================================================
-- N6. 2026-09-22 — IPREO, ROUND 3. No placeholders this time: the Visa deal
-- 1447528575 (2,425 orders, 1 tranche in the deal view) is the literal.
-- N6-1/N6-2 came back EMPTY twice with a placeholder; if they are empty with
-- this literal it is our bug and N6-3 says which join. ELAPSED on N6-1/N6-2
-- and on the OPUS pair N6-4 is the timing split.
-- ===========================================================================

-- N6-1. Visa's tranches.
SELECT TRANCHE_ID, TRANCHE_NAME, TRANCHE_SIZE, PRODUCT_TYPE, PRICE, PRICING_TS, SETTLEMENT_TS,
       SYNDICATE_MEMBER_NAME, DEAL_SHARING_TYPE, SELLING_CONCESSION_FEE, OVER_ALLOTMENT_AUTHORIZED_SHARES
FROM   DGSTREAM.VW_TRANCHE_SUMMARY
WHERE  PRODUCT = 'ECM' AND DEAL_ID = '1447528575';

-- N6-2. Visa's top 10 orders.
SELECT INVESTOR_NAME, INVESTOR_GP_ID, INVESTOR_CATEGORY, INVESTOR_REGION, IOI_TYPE, DEMAND_UNIT,
       ORDER_DEMAND_QTY, DEMAND_AS_SUBMITTED, ORDER_AMOUNT, ORDER_ALLOCATION, ORDER_STATUS,
       BILLED_BY, SALES_PERSON, TRANCHE_NAME
FROM   DGSTREAM.VW_ORDER_DETAIL
WHERE  PRODUCT = 'ECM' AND DEAL_ID = '1447528575'
ORDER  BY ORDER_ALLOCATION DESC FETCH FIRST 10 ROWS ONLY;

-- N6-3. The same deal straight from the source tables (diagnoses an empty
--       N6-1 / N6-2: every count here should be > 0).
SELECT (SELECT COUNT(*) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T
         WHERE T.DEAL_TRANSACTION_ID = '1447528575') AS TXN_ROWS_,
       (SELECT COUNT(*) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE TT
         JOIN DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T ON T.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
         WHERE T.DEAL_TRANSACTION_ID = '1447528575') AS TRANCHE_ROWS_,
       (SELECT COUNT(*) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_STATUS S
         JOIN DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T ON T.ECM_TRANSACTION_ID = S.ECM_TRANSACTION_ID
         WHERE T.DEAL_TRANSACTION_ID = '1447528575' AND S.STATUS_TYPE = 'Execution_Status') AS STATUS_ROWS_,
       (SELECT COUNT(*) FROM DGSTREAM.IPREO_OB_ECM_ORDER O
         WHERE O.DEAL_ID = '1447528575') AS ORDER_ROWS_,
       (SELECT COUNT(*) FROM DGSTREAM.IPREO_OB_ECM_ORDER O
         WHERE O.DEAL_ID = '1447528575'
         AND EXISTS (SELECT 1 FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE TT
                     WHERE TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) = O.TRANCHE_ID)) AS ORDERS_WITH_TRANCHE_
FROM   DUAL;

-- N6-4. The OPUS twin: pick one OPUS ECM deal with orders, then run N6-1 and
--       N6-2 with ITS id (the only paste in this section). The elapsed
--       difference Ipreo-id vs OPUS-id is what the new branch costs a deal card.
SELECT DEAL_ID, DEAL_NAME, ORDER_COUNT, TRANCHE_COUNT
FROM   DGSTREAM.VW_DEAL_SUMMARY
WHERE  PRODUCT = 'ECM' AND NOT REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') AND ORDER_COUNT > 0
ORDER  BY ORDER_COUNT DESC FETCH FIRST 1 ROW ONLY;

-- N6-5. Pricing dates at source — the three top Ipreo deals had LAST_PRICED
--       NULL, so every date window drops them. The views now fall back to
--       IPREO_ISSUE.PRICING_DT (repo, not yet deployed); these counts say how
--       far that reaches, and validate SETTLEMENT_DT / OFFER_DT before they
--       are wired the same way.
SELECT COUNT(*) AS TRANCHES_, COUNT(PRICING_TS) AS HAS_PRICING_TS_, COUNT(SETTLEMENT_TS) AS HAS_SETTLEMENT_TS_,
       COUNT(TRADE_DATE) AS HAS_TRADE_DATE_, COUNT(SELLING_CONCESSION_FEE) AS HAS_SELL_FEE_
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE;
SELECT COUNT(*) AS ISSUES_, COUNT(PRICING_DT) AS HAS_PRICING_DT_, COUNT(OFFER_DT) AS HAS_OFFER_DT_,
       COUNT(SETTLEMENT_DT) AS HAS_SETTLEMENT_DT_, MIN(PRICING_DT) AS FIRST_, MAX(PRICING_DT) AS LAST_
FROM   DGSTREAM.IPREO_ISSUE;

-- N6-6. OPUS fee unit — Ipreo fees are PER SHARE (N5-4: gross spread = UW +
--       mgmt + selling concession, e.g. 1.125 on a 50.00 offer). Before Ipreo
--       fees go into the same tranche columns we need the OPUS unit: five
--       OPUS ECM tranches with fees beside price and size.
SELECT DEAL_ID, TRANCHE_ID, PRICE, TRANCHE_SIZE, TOTAL_FEE, UNDERWRITING_FEE, MANAGEMENT_FEES,
       SELLING_CONCESSION_FEE, GROSS_SPREAD_PER_FEE, PRAECIPIUM_FEES
FROM   DGSTREAM.VW_TRANCHE_SUMMARY
WHERE  PRODUCT = 'ECM' AND NOT REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$')
AND    TOTAL_FEE IS NOT NULL AND PRICE IS NOT NULL
FETCH  FIRST 5 ROWS ONLY;
