-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- AG / AH answered (UAT 2026-10-19): DEMAND_QTY is never the sum; the 1,566
-- 'other' scaled orders are CURRENCY / PERCENT bids where DEMAND_QTY is the
-- share-equivalent — correct. The ladder now shows the bid's unit and decimals.

-- AI. SCALED-ORDER LADDER SPOT CHECK (run wherever vw_order_detail was just
-- deployed — QA 2026-10-20). Expect: IOI_LEVELS ascending by quantity, e.g.
-- '10,000 @ 12.00 | 20,000 @ 11.00 | 30,000 @ 10.00'; 'amounts:' / '% of deal:'
-- prefixes on currency / percent bids; decimals kept; '@ market' on a level
-- with no limit; LIMIT_VALUE = ORDER_AMOUNT; for SHARES bids ORDER_DEMAND_QTY =
-- the last (largest) level. Zero rows = no multi-level orders in this
-- environment (then deploy-check D17 FAILs for lack of data, not the view).
SELECT ORDER_ID, IOI_TYPE, DEMAND_UNIT, ORDER_DEMAND_QTY, LIMIT_VALUE, ORDER_AMOUNT, IOI_LEVELS
FROM   DGSTREAM.VW_ORDER_DETAIL
WHERE  PRODUCT = 'ECM' AND IOI_LEVELS IS NOT NULL
FETCH FIRST 10 ROWS ONLY;

-- After it: deploy vw_order_detail (IOI_LEVELS, +1 column), then on UAT
-- deploy-check A0 + A (A03 = 71) + D-ECM (D16, D17 must PASS).
