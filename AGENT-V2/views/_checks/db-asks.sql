-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- AG / AH answered (UAT 2026-10-19): DEMAND_QTY is never the sum; the 1,566
-- 'other' scaled orders are CURRENCY / PERCENT bids where DEMAND_QTY is the
-- share-equivalent — correct. The ladder now shows the bid's unit and decimals.

-- AJ. ORDERBOOK SCREEN COLUMNS WE DO NOT CARRY YET (UAT, three statements).
-- Product wants the agent's orderbook to look like the Orderbook screen. Three
-- screen fields have no view column: SOURCE ('1B' / 'ISN'), the 'PB' badge,
-- and INDICATION USD. AJ1 names the candidate columns; AJ2 / AJ3 show values.
-- AJ1. Candidate columns on the order and IOI tables (names only).
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM'
AND   ((TABLE_NAME = 'OB_ECM_ORDER'
        AND (COLUMN_NAME LIKE '%SOURCE%' OR COLUMN_NAME LIKE '%THRU%' OR COLUMN_NAME LIKE '%SHARED%'
             OR COLUMN_NAME LIKE '%OWNED%' OR COLUMN_NAME LIKE '%PB%' OR COLUMN_NAME LIKE '%PRIME%'
             OR COLUMN_NAME LIKE '%USD%' OR COLUMN_NAME LIKE '%AMOUNT%' OR COLUMN_NAME LIKE '%NOTIONAL%'
             OR COLUMN_NAME LIKE '%RELATIVE%' OR COLUMN_NAME LIKE '%POT%'))
    OR TABLE_NAME = 'OB_ECM_ORDER_IOI')
ORDER  BY TABLE_NAME, COLUMN_ID;

-- AJ2. Which flags tell '1B' from 'ISN' (and what Status shows): value mix on
--      the ECM book.
SELECT IS_OWNED, IS_SHARED_ORDER, ORDER_TYPE, IS_POT_ORDER, COUNT(*) AS ORDERS_
FROM   DGSTREAM.OB_ECM_ORDER
GROUP  BY IS_OWNED, IS_SHARED_ORDER, ORDER_TYPE, IS_POT_ORDER
ORDER  BY ORDERS_ DESC
FETCH FIRST 25 ROWS ONLY;

-- AJ3. Indication USD: does quantity x limit reproduce it? Ten priced share
--      bids with their limit, for comparison against the screen.
SELECT O.ORDER_ID, O.INVESTOR_NAME, I.IOI_QTY, I.LIMIT_VALUE, I.IOI_QTY * I.LIMIT_VALUE AS QTY_X_LIMIT
FROM   DGSTREAM.OB_ECM_ORDER O
JOIN   DGSTREAM.OB_ECM_ORDER_IOI I ON I.ORDER_ID = O.ORDER_ID
WHERE  O.IOI_UNIT = 'SHARES' AND I.LIMIT_VALUE IS NOT NULL
FETCH FIRST 10 ROWS ONLY;

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
