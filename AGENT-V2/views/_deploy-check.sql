-- ===========================================================================
-- POST-DEPLOY CHECK — one query. Every row must read PASS.
-- If any row says FAIL, the deployed view is not this revision.
-- ===========================================================================
SELECT check_, expected_, actual_,
       CASE WHEN actual_ = expected_ THEN 'PASS' ELSE 'FAIL' END AS verdict_
FROM (
  -- 1. the three new order columns exist
  SELECT '1. order view has issuer/sector/tranche_size' AS check_,
         '3' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_ORDER_DETAIL'
  AND    column_name IN ('ISSUER_NAME','SECTOR','TRANCHE_SIZE')
  UNION ALL
  -- 2. tranche size is a real NUMBER on BOTH views, not VARCHAR2
  SELECT '2. TRANCHE_SIZE is NUMBER (was VARCHAR2)',
         'NUMBER,NUMBER',
         LISTAGG(data_type, ',') WITHIN GROUP (ORDER BY table_name)
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND column_name = 'TRANCHE_SIZE'
  AND    table_name IN ('VW_ORDER_DETAIL','VW_TRANCHE_SUMMARY')
  UNION ALL
  -- 3. maturity is a DATE, not an NLS string
  SELECT '3. SECURITIES_MATURITY is DATE', 'DATE', MAX(data_type)
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_TRANCHE_SUMMARY'
  AND    column_name = 'SECURITIES_MATURITY'
  UNION ALL
  -- 4. ECM currencies are CODES now, not internal ids (the 3-hop bug).
  -- Token-wise: '^[0-9]+$' only caught a WHOLE-string numeric value, so a
  -- multi-currency fallback like '1 | 4' sailed through (QA 2026-08-14).
  -- Numeric tokens are the view's unmapped-id fallback — expected to be RARE;
  -- a large count here means the CURRENCY_NAME lookup is not joining.
  SELECT '4. ECM currencies are codes not ids', 'Y',
         CASE WHEN COUNT(*) = 0 THEN 'Y' ELSE 'N' END
  FROM   DGSTREAM.VW_DEAL_SUMMARY
  WHERE  PRODUCT = 'ECM' AND CURRENCIES IS NOT NULL
  AND    REGEXP_LIKE(CURRENCIES, '(^|\| )[0-9]+( \||$)')
  UNION ALL
  -- 5. DCM currency list is deduped ('USD | USD | USD' is gone)
  SELECT '5. DCM currencies deduped', 'Y',
         CASE WHEN COUNT(*) = 0 THEN 'Y' ELSE 'N' END
  FROM   DGSTREAM.VW_DEAL_SUMMARY
  WHERE  PRODUCT = 'DCM'
  AND    REGEXP_LIKE(CURRENCIES, '(^|\| )([A-Za-z]+)( \|.*\| | \| )\2( \||$)')
  UNION ALL
  -- 6. DCM allocations are populated, not silently zero
  SELECT '6. DCM allocation non-zero', 'Y',
         CASE WHEN SUM(ORDER_ALLOCATION) > 0 THEN 'Y' ELSE 'N' END
  FROM   DGSTREAM.VW_ORDER_DETAIL
  WHERE  PRODUCT = 'DCM'
  AND    ROWNUM <= 200000
  UNION ALL
  -- 7. GRAIN — the whole point of the split. rows must equal grain.
  SELECT '7. deal grain', 'Y',
         CASE WHEN COUNT(*) = COUNT(DISTINCT PRODUCT||'~'||DEAL_ID)
              THEN 'Y' ELSE 'N' END
  FROM   DGSTREAM.VW_DEAL_SUMMARY
  UNION ALL
  SELECT '8. tranche grain', 'Y',
         CASE WHEN COUNT(*) = COUNT(DISTINCT PRODUCT||'~'||DEAL_ID||'~'||TRANCHE_ID)
              THEN 'Y' ELSE 'N' END
  FROM   DGSTREAM.VW_TRANCHE_SUMMARY
  UNION ALL
  SELECT '9. order grain', 'Y',
         CASE WHEN COUNT(*) = COUNT(DISTINCT PRODUCT||'~'||ORDER_ID)
              THEN 'Y' ELSE 'N' END
  FROM   DGSTREAM.VW_ORDER_DETAIL
)
ORDER BY check_;
