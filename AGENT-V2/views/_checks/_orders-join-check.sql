-- ===========================================================================
-- ORDERS JOIN CHECK — do deals lose their orders on the way into
-- VW_ORDER_DETAIL? 2026-08-17: "deal size + total allocations per deal" for
-- 40 Exchangable Notes deals returned ZERO order rows; every allocation
-- showed "Not Available". Two readings: (a) those deals truly have no orders
-- (QA junk — answer was right, wording was wrong), or (b) the ECM order
-- branch's transaction-spine join DROPS their orders (view bug — known
-- monitored invariant: the deal card's ORDER_COUNT counts a wider population
-- than the order object returns).
-- ===========================================================================

-- Q1 — the population in question: Exchangable Notes deals, card count vs
-- order-view count side by side. CARD > 0 with VIEW_ROWS = 0 is the bug.
SELECT D.DEAL_ID, D.DEAL_NAME, D.ORDER_COUNT AS CARD_ORDER_COUNT,
       NVL(OV.CNT, 0) AS ORDER_VIEW_ROWS
FROM   DGSTREAM.VW_DEAL_SUMMARY D
LEFT JOIN (SELECT DEAL_ID, PRODUCT, COUNT(*) AS CNT
           FROM DGSTREAM.VW_ORDER_DETAIL GROUP BY DEAL_ID, PRODUCT) OV
  ON OV.DEAL_ID = D.DEAL_ID AND OV.PRODUCT = D.PRODUCT
WHERE  D.PRODUCT = 'ECM'
AND    UPPER(D.EQUITY_TYPE) LIKE '%EXCHANG%'
ORDER  BY D.ORDER_COUNT DESC NULLS LAST
FETCH FIRST 25 ROWS ONLY;

-- Q2 — blast radius across ALL deals: how many deals does the card say have
-- orders that the order view cannot see? Per product.
SELECT D.PRODUCT,
       COUNT(*) AS DEALS_CARD_HAS_ORDERS,
       SUM(CASE WHEN OV.CNT IS NULL THEN 1 ELSE 0 END) AS INVISIBLE_IN_ORDER_VIEW
FROM   DGSTREAM.VW_DEAL_SUMMARY D
LEFT JOIN (SELECT DEAL_ID, PRODUCT, COUNT(*) AS CNT
           FROM DGSTREAM.VW_ORDER_DETAIL GROUP BY DEAL_ID, PRODUCT) OV
  ON OV.DEAL_ID = D.DEAL_ID AND OV.PRODUCT = D.PRODUCT
WHERE  D.ORDER_COUNT > 0
GROUP  BY D.PRODUCT;

-- Q3 — ground truth at SOURCE for five of the exact deals from the trace:
-- does OB_ORDER hold rows for them at all? Rows here + zero in Q1's
-- ORDER_VIEW_ROWS = the join drops them (view bug). No rows = truly no orders.
SELECT DEAL_ID, COUNT(*) AS SOURCE_ORDER_ROWS
FROM   DGSTREAM.OB_ORDER
WHERE  DEAL_ID IN ('75066945', '75022788', '85AA4663', '3F262C01', '40EE5A03')
GROUP  BY DEAL_ID;
