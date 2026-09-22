-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on the
-- environment where the views are deployed and screenshot into ~/Desktop/ADK.
-- A section is deleted once its results are recorded. (N4 smoke + N3-5
-- census of 2026-09-22 are recorded.)
-- ===========================================================================


-- ===========================================================================
-- N5. 2026-09-22 — IPREO FOLLOW-UPS. Five statements; ELAPSED matters on
-- N5-2 / N5-3 (the zero-row runs of N4-4 / N4-5 took 85 s and 34 s, which
-- says the deal predicate is not reaching the big Ipreo blocks).
-- ===========================================================================

-- N5-1. Three Ipreo deal cards (N4-3 was not in the set) — pick DEAL_ID for
--       N5-2 / N5-3 from row 1.
SELECT DEAL_ID, DEAL_NAME, ISSUER_NAME, EQUITY_TYPE, DEAL_STATUS, DEAL_SIZE, CURRENCIES,
       TRANCHE_COUNT, ORDER_COUNT, INVESTOR_COUNT, TOTAL_DEMAND, TOTAL_ALLOCATION, LAST_PRICED
FROM   DGSTREAM.VW_DEAL_SUMMARY
WHERE  PRODUCT = 'ECM' AND REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') AND ORDER_COUNT > 0
ORDER  BY ORDER_COUNT DESC FETCH FIRST 3 ROWS ONLY;

-- N5-2. Its tranches, then the SAME statement with an OPUS ECM deal id
--       (8-char, e.g. from SELECT DEAL_ID FROM DGSTREAM.VW_DEAL_SUMMARY WHERE
--       PRODUCT = 'ECM' AND NOT REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') AND
--       TRANCHE_COUNT > 0 FETCH FIRST 1 ROW ONLY). Two elapsed times: the
--       difference is what the Ipreo branch adds to an ECM deal card.
SELECT TRANCHE_ID, TRANCHE_NAME, TRANCHE_SIZE, PRODUCT_TYPE, PRICE, PRICING_TS, SETTLEMENT_TS,
       SYNDICATE_MEMBER_NAME, DEAL_SHARING_TYPE, SELLING_CONCESSION_FEE, OVER_ALLOTMENT_AUTHORIZED_SHARES
FROM   DGSTREAM.VW_TRANCHE_SUMMARY
WHERE  PRODUCT = 'ECM' AND DEAL_ID = '<DEAL_ID from N5-1 row 1>';

-- N5-3. Its top 10 orders, same two runs (Ipreo id, then OPUS id).
SELECT INVESTOR_NAME, INVESTOR_GP_ID, INVESTOR_CATEGORY, INVESTOR_REGION, IOI_TYPE, DEMAND_UNIT,
       ORDER_DEMAND_QTY, DEMAND_AS_SUBMITTED, ORDER_AMOUNT, ORDER_ALLOCATION, ORDER_STATUS,
       BILLED_BY, SALES_PERSON, TRANCHE_NAME
FROM   DGSTREAM.VW_ORDER_DETAIL
WHERE  PRODUCT = 'ECM' AND DEAL_ID = '<DEAL_ID from N5-1 row 1>'
ORDER  BY ORDER_ALLOCATION DESC FETCH FIRST 10 ROWS ONLY;

-- N5-4. Fee unit — five priced issues with their fee rows (per-share amounts
--       or totals? decides how IPREO_PRODUCTFEE maps onto the tranche fee
--       columns). Column names beyond those censused may need adjusting.
SELECT * FROM (
  SELECT F.ISS_ID, F.PRD_ID, F.GROSS_SPREAD_AMT, F.U_W_FEE_AMT, F.MGMT_FEE_AMT, F.SELLING_CONC_FEE_AMT,
         P.OFFER_PX, P.PAR_VALUE, I.ISSUE_SIZE_AMT, I.ISSUE_NM
  FROM   DGSTREAM.IPREO_PRODUCTFEE F
  JOIN   DGSTREAM.IPREO_PRODUCT P ON P.PRD_ID = F.PRD_ID
  JOIN   DGSTREAM.IPREO_ISSUE   I ON I.ISS_ID = F.ISS_ID
  WHERE  F.SELLING_CONC_FEE_AMT IS NOT NULL AND P.OFFER_PX IS NOT NULL
  ORDER  BY I.PRICING_DT DESC NULLS LAST) WHERE ROWNUM <= 5;

-- N5-5. Through Starburst (the agent's path; run in the Trino client — N4-8
--       was not in the set):
--   SELECT deal_id, deal_name, issuer_name, tranche_count, order_count
--   FROM bds_dg_oraas.dgstream.vw_deal_summary
--   WHERE product = 'ECM' AND regexp_like(deal_id, '^[0-9]{10}$') LIMIT 3;
