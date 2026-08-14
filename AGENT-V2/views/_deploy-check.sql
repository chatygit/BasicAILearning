-- ===========================================================================
-- POST-DEPLOY CHECK — one query. Every row must read PASS (INFO rows report
-- data-state for tracking, not deploy correctness — they never fail).
-- If any row says FAIL, the deployed view is not this revision.
-- ===========================================================================
SELECT check_, expected_, actual_,
       CASE WHEN expected_ = '(info)' THEN 'INFO'
            WHEN actual_ = expected_ THEN 'PASS' ELSE 'FAIL' END AS verdict_
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
  -- 3. maturity stays VARCHAR2 — the DATE conversion was REVERTED on
  -- ORA-01790 (source MATURITY_DATE is character data) and the ontology now
  -- treats the column as text with no range operators. DATE appearing here
  -- means someone re-attempted the conversion without re-blessing the
  -- ontology/skill — coordinate both or range filters go silently wrong.
  SELECT '3. SECURITIES_MATURITY is VARCHAR2 (DATE was reverted)', 'VARCHAR2', MAX(data_type)
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_TRANCHE_SUMMARY'
  AND    column_name = 'SECURITIES_MATURITY'
  UNION ALL
  -- 4. ECM currencies are CODES, not internal ids (the 3-hop bug). This is
  -- the VIEW-LOGIC check: a whole-string numeric value means the
  -- CURRENCY_NAME lookup join is broken and the fallback fires everywhere.
  SELECT '4. ECM currencies are codes not ids', 'Y',
         CASE WHEN COUNT(*) = 0 THEN 'Y' ELSE 'N' END
  FROM   DGSTREAM.VW_DEAL_SUMMARY
  WHERE  PRODUCT = 'ECM' AND CURRENCIES IS NOT NULL
  AND    REGEXP_LIKE(CURRENCIES, '^[0-9]+$')
  UNION ALL
  -- 4b. INFO, not a deploy verdict: deals carrying at least one UNMAPPED
  -- currency token ('1 | 4' — the NVL fallback for ids with no name row).
  -- QA measured 377 deals on 2026-08-14. This is a DATA gap, not a view
  -- regression: presentation doctrine renders these tokens "not recorded",
  -- and the mapping decision waits on the PROD count (_currency-check.sql).
  SELECT '4b. deals with unmapped currency tokens (INFO)', '(info)',
         TO_CHAR(COUNT(DISTINCT DEAL_ID))
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
