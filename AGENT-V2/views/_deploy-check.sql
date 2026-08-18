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
  -- 1b. ROUND 2: order view carries BILLED_BY + OFFERING_TYPE
  SELECT '1b. order view has billed_by/offering_type (round 2)', '2',
         TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_ORDER_DETAIL'
  AND    column_name IN ('BILLED_BY','OFFERING_TYPE')
  UNION ALL
  -- 1c. ROUND 2: tranche view carries EQUITY_TYPE
  SELECT '1c. tranche view has equity_type (round 2)', '1',
         TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_TRANCHE_SUMMARY'
  AND    column_name = 'EQUITY_TYPE'
  UNION ALL
  -- 1d. INFO: BILLED_BY population per product (measured pre-deploy:
  -- ECM 90.2%, DCM 74% — a big drop here means a broken join, not data).
  SELECT '1d. orders with billed_by (INFO)', '(info)',
         (SELECT TO_CHAR(COUNT(BILLED_BY)) || ' of ' || TO_CHAR(COUNT(*))
          FROM DGSTREAM.VW_ORDER_DETAIL)
  FROM   dual
  UNION ALL
  -- 1e. ROUND 2 INFO: ECM deals with an issuer name. Pre-fix this was ZERO
  -- (the old source is 100% dead in QA); the GFCID join resolves ~6,892 in
  -- QA (more in PROD, where deals are real and carry GFCIDs). Zero here
  -- post-deploy means the OB_DEAL_ISSUER join regressed.
  SELECT '1e. ECM deals with issuer name (INFO)', '(info)',
         (SELECT TO_CHAR(COUNT(ISSUER_NAME)) || ' of ' || TO_CHAR(COUNT(*))
          FROM DGSTREAM.VW_DEAL_SUMMARY WHERE PRODUCT = 'ECM')
  FROM   dual
  UNION ALL
  -- 1f/1g. BATCH 3 (ticket #100): DCM deal-region + settlement roll-ups.
  -- Measured pre-deploy at the source (R3): 8,260 of 46,931 DCM deals carry
  -- a region, 30,749 a settlement date. Zero on either post-deploy means
  -- the batch-3 deal-view rollups did not land.
  SELECT '1f. DCM deals with region (INFO, expect ~8,260)', '(info)',
         (SELECT TO_CHAR(COUNT(DEAL_REGION)) || ' of ' || TO_CHAR(COUNT(*))
          FROM DGSTREAM.VW_DEAL_SUMMARY WHERE PRODUCT = 'DCM')
  FROM   dual
  UNION ALL
  SELECT '1g. DCM deals with settlement_ts (INFO, expect ~30,749)', '(info)',
         (SELECT TO_CHAR(COUNT(SETTLEMENT_TS)) || ' of ' || TO_CHAR(COUNT(*))
          FROM DGSTREAM.VW_DEAL_SUMMARY WHERE PRODUCT = 'DCM')
  FROM   dual
  UNION ALL
  -- 1h. BATCH 3: ECM tranche region now inherits the deal region (its own
  -- column measured 3/36,352). Expect roughly the ECM deal-region rate
  -- (~5%; R1: 1,457/29,384 deal transactions). Staying at 0-3 means the
  -- NVL fallback did not deploy.
  SELECT '1h. ECM tranches with a region (INFO, expect ~5%)', '(info)',
         (SELECT TO_CHAR(COUNT(TRANCHE_REGION)) || ' of ' || TO_CHAR(COUNT(*))
          FROM DGSTREAM.VW_TRANCHE_SUMMARY WHERE PRODUCT = 'ECM')
  FROM   dual
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
  -- 4. ECM currency names RESOLVE (the 3-hop bug was: ids everywhere). A
  -- numeric-row count cannot be the logic check — a single-tranche deal with
  -- one unmapped id yields CURRENCIES='1', numeric whole-string, so QA seed
  -- data fails it forever (measured 2026-08-14). The signal that separates
  -- "join broken" from "some deals unmapped": a broken CURRENCY_NAME join
  -- produces ZERO rows containing an alphabetic code; a healthy join
  -- produces thousands. Unmapped volume is tracked by INFO row 4b.
  SELECT '4. ECM currency names resolve (view logic)', 'Y',
         CASE WHEN COUNT(CASE WHEN REGEXP_LIKE(CURRENCIES, '[A-Za-z]') THEN 1 END) > 0
              THEN 'Y' ELSE 'N' END
  FROM   DGSTREAM.VW_DEAL_SUMMARY
  WHERE  PRODUCT = 'ECM' AND CURRENCIES IS NOT NULL
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
