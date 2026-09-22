-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on the
-- environment where the views are deployed and screenshot into ~/Desktop/ADK
-- WITH the status bar. A section is deleted once its results are recorded.
-- (N9 of 2026-09-22 is recorded.)
-- ===========================================================================


-- ===========================================================================
-- N10. 2026-09-22 — THE LAST PRE-DEPLOY CENSUS: convertible allocations.
-- N9-3 shows Ipreo convertibles allocated in FACE MONEY while their deal size
-- and demand are in BONDS (Liberty Interactive: 675,000 bonds, 750,000,000
-- allocated; Pluralsight 550,000 / 633,500,000; Vonage 300,000 / 345,000,000
-- — each ≈ size × 1,000 par × 1.15 shoe). Two statements, seconds each.
-- ===========================================================================

-- N10-1. Is it every convertible, or only some? Allocation-to-size ratio
--        buckets by equity type, Ipreo deals with allocations.
SELECT T.PRODUCT_EQUITY_TYPE_VALUE AS EQUITY_TYPE_,
       SUM(CASE WHEN A.ALLOC > 500 * T.DEAL_SIZE THEN 1 ELSE 0 END) AS RATIO_GT_500_,
       SUM(CASE WHEN A.ALLOC BETWEEN 1.2 * T.DEAL_SIZE AND 500 * T.DEAL_SIZE THEN 1 ELSE 0 END) AS RATIO_1_2_TO_500_,
       SUM(CASE WHEN A.ALLOC < 1.2 * T.DEAL_SIZE THEN 1 ELSE 0 END) AS RATIO_LE_1_2_,
       COUNT(*) AS DEALS_
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T
JOIN   (SELECT DEAL_ID, SUM(PRIVATE_ALLOC) AS ALLOC FROM DGSTREAM.IPREO_OB_ECM_ORDER
        WHERE PRIVATE_ALLOC > 0 GROUP BY DEAL_ID) A ON A.DEAL_ID = T.DEAL_TRANSACTION_ID
WHERE  T.DEAL_SIZE > 0
GROUP  BY T.PRODUCT_EQUITY_TYPE_VALUE ORDER BY 5 DESC;

-- N10-2. On one convertible (Pluralsight 1447754429): the mirror allocation
--        beside the raw quantity / size columns and the par value — which raw
--        column is in bonds? Five orders.
SELECT O.INVESTOR_NAME, O.IOI_UNIT, M.IOI_QTY AS MIRROR_QTY_, O.PRIVATE_ALLOC AS MIRROR_ALLOC_,
       R.INST_ALLOC_QTY AS RAW_ALLOC_QTY_, R.INST_ALLOC_SIZE AS RAW_ALLOC_SIZE_, P.PAR_VALUE, P.OFFER_PX
FROM   DGSTREAM.IPREO_OB_ECM_ORDER O
LEFT JOIN DGSTREAM.IPREO_OB_ECM_ORDER_IOI M ON M.ORDER_ID = O.ORDER_ID
LEFT JOIN DGSTREAM.IPREO_ORDER R ON R.ORD_ID = TO_NUMBER(O.ORDER_ID DEFAULT NULL ON CONVERSION ERROR)
LEFT JOIN (SELECT ISS_ID, MAX(PAR_VALUE) AS PAR_VALUE, MAX(OFFER_PX) AS OFFER_PX
           FROM DGSTREAM.IPREO_PRODUCT GROUP BY ISS_ID) P ON P.ISS_ID = 1447754429
WHERE  O.DEAL_ID = '1447754429' AND O.PRIVATE_ALLOC > 0
ORDER  BY O.PRIVATE_ALLOC DESC FETCH FIRST 5 ROWS ONLY;

-- AFTER THE VIEWS ARE UP: views/_deploy-check.sql sections A0, B, C, D (new
-- rows 22c LAST_PRICED, 23c fees/price, 24c exclusion), then K8/K9.
