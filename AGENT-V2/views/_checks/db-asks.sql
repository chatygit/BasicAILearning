-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- AG answered (UAT 2026-10-19): DEMAND_QTY never equals the SUM of the levels.
-- Of 6,128 multi-level scaled orders: 1,531 equal the largest level, 3,031 are
-- blank (the view then falls back to the largest level), 1,566 hold another
-- figure. OPTIONAL — AH shows ten of those 1,566 so we can see what they are.
SELECT O.ORDER_ID, O.DEMAND_QTY, O.IOI_UNIT, L.LEVELS_
FROM   (SELECT ORDER_ID, MAX(DEMAND_QTY) AS DEMAND_QTY, MAX(IOI_UNIT) AS IOI_UNIT
        FROM DGSTREAM.OB_ECM_ORDER WHERE UPPER(IOI_TYPE) = 'SCALED' GROUP BY ORDER_ID) O
JOIN   (SELECT ORDER_ID, MAX(IOI_QTY) AS MAX_QTY, SUM(IOI_QTY) AS SUM_QTY,
               LISTAGG(IOI_QTY || ' @ ' || NVL(TO_CHAR(LIMIT_VALUE), '-'), ' | ')
                 WITHIN GROUP (ORDER BY IOI_QTY) AS LEVELS_
        FROM (SELECT DISTINCT ORDER_ID, IOI_QTY, LIMIT_VALUE FROM DGSTREAM.OB_ECM_ORDER_IOI)
        GROUP BY ORDER_ID HAVING COUNT(*) > 1) L
       ON L.ORDER_ID = O.ORDER_ID
WHERE  O.DEMAND_QTY IS NOT NULL AND O.DEMAND_QTY <> L.MAX_QTY AND O.DEMAND_QTY <> L.SUM_QTY
FETCH FIRST 10 ROWS ONLY;

-- After it: deploy vw_order_detail (IOI_LEVELS, +1 column), then on UAT
-- deploy-check A0 + A (A03 = 71) + D-ECM (D16, D17 must PASS).
