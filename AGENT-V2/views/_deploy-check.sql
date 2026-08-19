-- ===========================================================================
-- POST-DEPLOY CHECK — FOUR independent statements. Run as a script (F5).
-- 2026-08-19 (2nd revision): B/C/D each read their view EXACTLY ONCE — the
-- first revision ran one scalar subquery per row (7 full evaluations of the
-- deal view alone) and took forever; all population facts now come from a
-- single conditional-aggregation pass (/*+ MATERIALIZE */ pins one scan).
-- Statement A is structural (all_tab_columns only — can never ORA-00904,
-- always reports WHICH views are current); an old view kills only its own
-- section. Every non-INFO row must read PASS. INFO expectations are
-- UAT-measured; in another env judge zero-vs-healthy, not exact.
-- ===========================================================================

-- A. STRUCTURAL — always runs. FAIL here = that view is not this revision.
SELECT check_, expected_, actual_,
       CASE WHEN actual_ = expected_ THEN 'PASS' ELSE 'FAIL' END AS verdict_
FROM (
  SELECT '1. order view has issuer/sector/tranche_size' AS check_,
         '3' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_ORDER_DETAIL'
  AND    column_name IN ('ISSUER_NAME','SECTOR','TRANCHE_SIZE')
  UNION ALL
  SELECT '1b. order view has billed_by/offering_type (round 2)', '2',
         TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_ORDER_DETAIL'
  AND    column_name IN ('BILLED_BY','OFFERING_TYPE')
  UNION ALL
  SELECT '1c. tranche view has equity_type (round 2)', '1',
         TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_TRANCHE_SUMMARY'
  AND    column_name = 'EQUITY_TYPE'
  UNION ALL
  SELECT '2. TRANCHE_SIZE is NUMBER (was VARCHAR2)',
         'NUMBER,NUMBER',
         LISTAGG(data_type, ',') WITHIN GROUP (ORDER BY table_name)
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND column_name = 'TRANCHE_SIZE'
  AND    table_name IN ('VW_ORDER_DETAIL','VW_TRANCHE_SUMMARY')
  UNION ALL
  -- maturity stays VARCHAR2 — the DATE conversion was REVERTED (ORA-01790).
  SELECT '3. SECURITIES_MATURITY is VARCHAR2 (DATE was reverted)', 'VARCHAR2',
         MAX(data_type)
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_TRANCHE_SUMMARY'
  AND    column_name = 'SECURITIES_MATURITY'
)
ORDER BY check_;

-- B. DEAL VIEW — ONE scan. Dies alone if VW_DEAL_SUMMARY is old.
WITH agg AS (
  SELECT /*+ MATERIALIZE */
         COUNT(*) AS rows_,
         COUNT(DISTINCT PRODUCT||'~'||DEAL_ID) AS keys_,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN 1 END) AS ecm_rows,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN ISSUER_NAME END) AS ecm_issuer,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN 1 END) AS dcm_rows,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN DEAL_REGION END) AS dcm_region,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN SETTLEMENT_TS END) AS dcm_settle,
         COUNT(CASE WHEN PRODUCT = 'ECM' AND CURRENCIES IS NOT NULL
                     AND REGEXP_LIKE(CURRENCIES, '[A-Za-z]')
                    THEN 1 END) AS ecm_alpha,
         COUNT(DISTINCT CASE WHEN PRODUCT = 'ECM' AND CURRENCIES IS NOT NULL
                              AND REGEXP_LIKE(CURRENCIES, '(^|\| )[0-9]+( \||$)')
                             THEN DEAL_ID END) AS ecm_unmapped,
         COUNT(CASE WHEN PRODUCT = 'DCM' AND REGEXP_LIKE(CURRENCIES,
                     '(^|\| )([A-Za-z]+)( \|.*\| | \| )\2( \||$)')
                    THEN 1 END) AS dcm_dupcur
  FROM DGSTREAM.VW_DEAL_SUMMARY
)
SELECT '1e. ECM deals with issuer name (INFO, expect ~6,892 UAT)' AS check_,
       '(info)' AS expected_,
       TO_CHAR(ecm_issuer) || ' of ' || TO_CHAR(ecm_rows) AS actual_,
       'INFO' AS verdict_
FROM agg
UNION ALL
SELECT '1f. DCM deals with region (INFO, expect ~8,260 UAT)', '(info)',
       TO_CHAR(dcm_region) || ' of ' || TO_CHAR(dcm_rows), 'INFO' FROM agg
UNION ALL
SELECT '1g. DCM deals with settlement_ts (INFO, expect ~30,749 UAT)', '(info)',
       TO_CHAR(dcm_settle) || ' of ' || TO_CHAR(dcm_rows), 'INFO' FROM agg
UNION ALL
-- broken CURRENCY_NAME join = ZERO alphabetic codes; healthy = thousands.
SELECT '4. ECM currency names resolve (view logic)', 'Y',
       CASE WHEN ecm_alpha > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN ecm_alpha > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT '4b. deals with unmapped currency tokens (INFO, ~377 UAT)', '(info)',
       TO_CHAR(ecm_unmapped), 'INFO' FROM agg
UNION ALL
SELECT '5. DCM currencies deduped', 'Y',
       CASE WHEN dcm_dupcur = 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_dupcur = 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT '7. deal grain (rows = PRODUCT+DEAL_ID)', 'Y',
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END FROM agg
ORDER BY 1;

-- C. TRANCHE VIEW — ONE scan. Dies alone if VW_TRANCHE_SUMMARY is old.
WITH agg AS (
  SELECT /*+ MATERIALIZE */
         COUNT(*) AS rows_,
         COUNT(DISTINCT PRODUCT||'~'||DEAL_ID||'~'||TRANCHE_ID) AS keys_,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN 1 END) AS ecm_rows,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN TRANCHE_REGION END) AS ecm_region
  FROM DGSTREAM.VW_TRANCHE_SUMMARY
)
SELECT '1h. ECM tranches with a region (INFO, expect ~5% UAT)' AS check_,
       '(info)' AS expected_,
       TO_CHAR(ecm_region) || ' of ' || TO_CHAR(ecm_rows) AS actual_,
       'INFO' AS verdict_
FROM agg
UNION ALL
SELECT '8. tranche grain (rows = PRODUCT+DEAL+TRANCHE)', 'Y',
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END FROM agg
ORDER BY 1;

-- D. ORDER VIEW — ONE scan. Dies alone if VW_ORDER_DETAIL is old (DEV
-- 2026-08-19: no BILLED_BY -> only this section errors; A/B/C still report).
WITH agg AS (
  SELECT /*+ MATERIALIZE */
         COUNT(*) AS rows_,
         COUNT(DISTINCT PRODUCT||'~'||ORDER_ID) AS keys_,
         COUNT(BILLED_BY) AS billed_,
         SUM(CASE WHEN PRODUCT = 'DCM' THEN ORDER_ALLOCATION END) AS dcm_alloc
  FROM DGSTREAM.VW_ORDER_DETAIL
)
SELECT '1d. orders with billed_by (INFO, ~90/74% UAT)' AS check_,
       '(info)' AS expected_,
       TO_CHAR(billed_) || ' of ' || TO_CHAR(rows_) AS actual_,
       'INFO' AS verdict_
FROM agg
UNION ALL
SELECT '6. DCM allocation non-zero', 'Y',
       CASE WHEN dcm_alloc > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_alloc > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT '9. order grain (rows = PRODUCT+ORDER_ID)', 'Y',
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END FROM agg
ORDER BY 1;
