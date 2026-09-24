-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on QA and
-- screenshot into ~/Desktop/ADK. SELECTs only, never session settings.
-- (N12 of 2026-09-24 is recorded: all four Visa cards returned.)
-- ===========================================================================

-- AFTER THE NEXT REDEPLOY of the three views (repo 2026-09-24: converted
-- currency bids rounded to whole shares; the order view's raw-order window
-- keyed by issue): the Visa order card once more — expect ORDER_DEMAND_QTY
-- 340,909 (not 340,909.0909) on the Kuwait rows.
SELECT INVESTOR_NAME, INVESTOR_CATEGORY, INVESTOR_REGION, DEMAND_UNIT, ORDER_DEMAND_QTY,
       DEMAND_AS_SUBMITTED, ORDER_ALLOCATION, PRICING_TS, TRANCHE_SIZE, TRANCHE_NAME
FROM   DGSTREAM.VW_ORDER_DETAIL
WHERE  PRODUCT = 'ECM' AND DEAL_ID = '1447528575'
ORDER  BY ORDER_ALLOCATION DESC FETCH FIRST 10 ROWS ONLY;
