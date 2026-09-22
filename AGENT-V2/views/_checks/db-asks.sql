-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on the
-- environment where the views are deployed and screenshot into ~/Desktop/ADK
-- WITH the status bar. A section is deleted once its results are recorded.
-- (N8 of 2026-09-22 is recorded.)
-- ===========================================================================


-- ===========================================================================
-- N9. 2026-09-22 — IPREO, ROUND 6. Three censuses that need no new views,
-- then the deploy-check once the views are up.
-- ===========================================================================

-- N9-1. PERCENT indications (12,313 orders; N8-1 returned none because they
--       carry no raw amount): what is the mirror's IOI_QTY there — the percent
--       itself, or a share-equivalent? Five rows with the deal size.
SELECT * FROM (
  SELECT O.INVESTOR_NAME, M.IOI_QTY AS MIRROR_QTY_, R.IOI_QTY AS RAW_QTY_, R.IOI_AMT AS RAW_AMT_,
         T.DEAL_SIZE, T.PRODUCT_EQUITY_TYPE_VALUE AS EQUITY_TYPE_, O.PRIVATE_ALLOC
  FROM   DGSTREAM.IPREO_OB_ECM_ORDER O
  JOIN   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T ON T.DEAL_TRANSACTION_ID = O.DEAL_ID
  LEFT JOIN DGSTREAM.IPREO_OB_ECM_ORDER_IOI M ON M.ORDER_ID = O.ORDER_ID
  LEFT JOIN DGSTREAM.IPREO_ORDERIOI R ON R.ORD_ID = TO_NUMBER(O.ORDER_ID DEFAULT NULL ON CONVERSION ERROR)
  WHERE  O.IOI_UNIT = 'PERCENT' AND M.IOI_QTY IS NOT NULL
  ORDER  BY O.ORDER_ID) WHERE ROWNUM <= 5;

-- N9-2. Tranche size columns: the active size includes the shoe on 4,293
--       tranches and not on 5,711 (N8-2). Which raw column is the BASE size?
--       (N3-5c's column listing was not in the set; TRN_UN_SIZE_QTY was a
--       misread.) Names first, then Visa's values on each.
SELECT COLUMN_NAME, DATA_TYPE FROM ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'IPREO_TRANCHE'
AND    (COLUMN_NAME LIKE '%SIZE%' OR COLUMN_NAME LIKE '%QTY%' OR COLUMN_NAME LIKE '%AMT%')
ORDER  BY COLUMN_NAME;
SELECT * FROM DGSTREAM.IPREO_TRANCHE WHERE TRN_ID = 1447542813;

-- N9-3. The 94 Ipreo deals whose allocations exceed 1.2x their size (N8-4) —
--       the ten largest, for the data owner (~60 s).
SELECT DEAL_ID, DEAL_NAME, DEAL_SIZE, TOTAL_ALLOCATION,
       ROUND(TOTAL_ALLOCATION / DEAL_SIZE, 2) AS RATIO_, ORDER_COUNT, LAST_PRICED
FROM   DGSTREAM.VW_DEAL_SUMMARY
WHERE  PRODUCT = 'ECM' AND REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') AND DEAL_SIZE > 0
AND    TOTAL_ALLOCATION > 1.2 * DEAL_SIZE
ORDER  BY TOTAL_ALLOCATION DESC FETCH FIRST 10 ROWS ONLY;

-- N9-4. AFTER THE VIEWS ARE UP: views/_deploy-check.sql sections A0, B, C, D
--       (new rows 22c LAST_PRICED, 23c fees/price, 24c exclusion), then K8/K9.
