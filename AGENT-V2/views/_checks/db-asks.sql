-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- AG / AH answered (UAT 2026-10-19): DEMAND_QTY is never the sum; the 1,566
-- 'other' scaled orders are CURRENCY / PERCENT bids where DEMAND_QTY is the
-- share-equivalent — correct. The ladder now shows the bid's unit and decimals.

-- AK. CALIBRATE AGAINST THE ORDERBOOK SCREEN (UAT, three statements). AJ found
-- OB_ECM_ORDER.SOURCE, SOURCE_SYSTEM and RELATIVE_INDICATION (no USD / PB column).
-- AK1. Their values on the ECM book.
SELECT SOURCE, SOURCE_SYSTEM, IS_OWNED, IS_SHARED_ORDER, COUNT(*) AS ORDERS_,
       COUNT(RELATIVE_INDICATION) AS WITH_RELATIVE_IND
FROM   DGSTREAM.OB_ECM_ORDER
GROUP  BY SOURCE, SOURCE_SYSTEM, IS_OWNED, IS_SHARED_ORDER
ORDER  BY ORDERS_ DESC
FETCH FIRST 20 ROWS ONLY;

-- AK2. Find the deal on the screen shot (ADIA LONDON, COATUE, THE OTT LLC,
--      BRANDES, WELLINGTON MANAGEMENT TRUST on one book).
SELECT DEAL_ID, COUNT(DISTINCT INVESTOR_NAME) AS MATCHED_NAMES, COUNT(*) AS ORDERS_
FROM   DGSTREAM.OB_ECM_ORDER
WHERE  INVESTOR_NAME IN ('ADIA LONDON', 'COATUE MANAGEMENT LLC', 'THE OTT LLC', 'BRANDES',
                         'WELLINGTON MANAGEMENT TRUST', 'ARTISAN PARTNERS', 'AMERICAN CENTURY')
GROUP  BY DEAL_ID
HAVING COUNT(DISTINCT INVESTOR_NAME) >= 4
ORDER  BY MATCHED_NAMES DESC;

-- AK3. That deal's book, every field the screen shows (put AK2's DEAL_ID in;
--      the screen deal should be the top row of AK2).
SELECT O.INVESTOR_NAME, O.SOURCE, O.ORDER_TYPE, O.IS_POT_ORDER, O.INVESTOR_GPNUM,
       O.IOI_UNIT, O.DEMAND_QTY, O.RELATIVE_INDICATION, O.PRIVATE_ALLOC,
       I.IOI_QTY, I.LIMIT_VALUE, I.IOI_QTY * I.LIMIT_VALUE AS QTY_X_LIMIT
FROM   DGSTREAM.OB_ECM_ORDER O
LEFT JOIN DGSTREAM.OB_ECM_ORDER_IOI I ON I.ORDER_ID = O.ORDER_ID
WHERE  O.DEAL_ID = (SELECT DEAL_ID FROM (
                      SELECT DEAL_ID FROM DGSTREAM.OB_ECM_ORDER
                      WHERE INVESTOR_NAME IN ('ADIA LONDON', 'COATUE MANAGEMENT LLC', 'THE OTT LLC', 'BRANDES',
                                              'WELLINGTON MANAGEMENT TRUST', 'ARTISAN PARTNERS', 'AMERICAN CENTURY')
                      GROUP BY DEAL_ID ORDER BY COUNT(DISTINCT INVESTOR_NAME) DESC)
                    WHERE ROWNUM = 1)
ORDER  BY O.INVESTOR_NAME, I.IOI_QTY DESC;

-- After it: deploy vw_order_detail (IOI_LEVELS, +1 column), then on UAT
-- deploy-check A0 + A (A03 = 71) + D-ECM (D16, D17 must PASS).
