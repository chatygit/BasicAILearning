-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- AG. SCALED-ORDER DEMAND (UAT, one statement). The PO saw 60,000 where the
-- order is 30,000 (levels 10k / 20k / 30k are CUMULATIVE). ORDER_DEMAND_QTY takes
-- OB_ECM_ORDER.DEMAND_QTY first and the largest IOI level only as a fallback —
-- is DEMAND_QTY the largest level, the SUM of the levels, or something else?
SELECT CASE WHEN O.DEMAND_QTY IS NULL THEN 'DEMAND_QTY blank'
            WHEN O.DEMAND_QTY = L.MAX_QTY THEN 'equals largest level'
            WHEN O.DEMAND_QTY = L.SUM_QTY THEN 'equals SUM of levels'
            ELSE 'other' END AS DEMAND_QTY_IS,
       COUNT(*) AS SCALED_ORDERS
FROM   (SELECT ORDER_ID, MAX(DEMAND_QTY) AS DEMAND_QTY FROM DGSTREAM.OB_ECM_ORDER
        WHERE UPPER(IOI_TYPE) = 'SCALED' GROUP BY ORDER_ID) O
JOIN   (SELECT ORDER_ID, MAX(IOI_QTY) AS MAX_QTY, SUM(IOI_QTY) AS SUM_QTY, COUNT(*) AS LEVELS
        FROM (SELECT DISTINCT ORDER_ID, IOI_QTY, LIMIT_VALUE FROM DGSTREAM.OB_ECM_ORDER_IOI)
        GROUP BY ORDER_ID HAVING COUNT(*) > 1) L
       ON L.ORDER_ID = O.ORDER_ID
GROUP  BY CASE WHEN O.DEMAND_QTY IS NULL THEN 'DEMAND_QTY blank'
               WHEN O.DEMAND_QTY = L.MAX_QTY THEN 'equals largest level'
               WHEN O.DEMAND_QTY = L.SUM_QTY THEN 'equals SUM of levels'
               ELSE 'other' END;

-- After it: deploy vw_order_detail (IOI_LEVELS, +1 column), then on UAT
-- deploy-check A0 + A (A03 = 71) + D-ECM (D16, D17 must PASS).
