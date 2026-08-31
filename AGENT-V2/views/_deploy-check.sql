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
  -- RELEASE 2: order view gained EQUITY_TYPE + ORDER_OWNERSHIP (away
  -- orders included; HOME/AWAY exposed).
  SELECT '1i. order view has equity_type/order_ownership (release 2)', '2',
         TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_ORDER_DETAIL'
  AND    column_name IN ('EQUITY_TYPE','ORDER_OWNERSHIP')
  UNION ALL
  SELECT '1l. tranche view has settlement_ts (release 2)', '1',
         TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_TRANCHE_SUMMARY'
  AND    column_name = 'SETTLEMENT_TS'
  UNION ALL
  SELECT '1m. all three views expose TRANSACTION_ID (release 2/D1)', '3',
         TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND column_name = 'TRANSACTION_ID'
  AND    table_name IN ('VW_DEAL_SUMMARY','VW_TRANCHE_SUMMARY','VW_ORDER_DETAIL')
  UNION ALL
  -- RELEASE 3: issuer LEI (deal+tranche), salesperson (order).
  SELECT '1n. ISSUER_LEI on deal+tranche, SALES_PERSON on order (rel 3)', '3',
         TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM'
  AND   ((column_name = 'ISSUER_LEI'
          AND table_name IN ('VW_DEAL_SUMMARY','VW_TRANCHE_SUMMARY'))
      OR (column_name = 'SALES_PERSON' AND table_name = 'VW_ORDER_DETAIL'))
  UNION ALL
  -- V3 FINAL WAVE: the four new views exist.
  SELECT '1u. four new views exist (hedge order/trade, designation, trade synd)', '4',
         TO_CHAR(COUNT(DISTINCT table_name))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM'
  AND    table_name IN ('VW_HEDGE_ORDER','VW_HEDGE_TRADE',
                        'VW_DESIGNATION','VW_TRADE_SYNDICATE')
  UNION ALL
  SELECT '1v. final-wave columns landed (trade/order/tranche/deal)', '10',
         TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM'
  AND   ((table_name = 'VW_TRADE_DETAIL' AND column_name IN
            ('TRADE_PRICE','FIRM_ACCOUNT_NUMBER','EXECUTION_TS'))
      OR (table_name = 'VW_ORDER_DETAIL' AND column_name IN
            ('WALL_CROSSED','INVESTOR_CLASSIFICATION','ACTIVE_PRICE'))
      OR (table_name = 'VW_TRANCHE_SUMMARY' AND column_name IN
            ('GROSS_SPREAD_PER_FEE','OVER_ALLOTMENT_AUTHORIZED_SHARES'))
      OR (table_name = 'VW_DEAL_SUMMARY' AND column_name IN
            ('REOFFER_LOW_PRICE','ISSUER_DOMICILE')))
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
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN ISSUER_LEI END) AS ecm_lei,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN REOFFER_LOW_PRICE END) AS ecm_reoffer,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN ISSUER_DOMICILE END) AS ecm_domicile,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN TRANSACTION_ID END) AS dcm_txn,
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
SELECT '1o. ECM deals with issuer LEI (INFO, expect ~83% — rel 3)', '(info)',
       TO_CHAR(ecm_lei) || ' of ' || TO_CHAR(ecm_rows), 'INFO' FROM agg
UNION ALL
SELECT '1w. ECM deals w/ reoffer price range / domicile (INFO — final wave)',
       '(info)', TO_CHAR(ecm_reoffer) || ' range / ' ||
       TO_CHAR(ecm_domicile) || ' domicile', 'INFO' FROM agg
UNION ALL
SELECT '1p. DCM deals with TRANSACTION_ID (INFO, ~945 PROD, fwd-populated)',
       '(info)', TO_CHAR(dcm_txn) || ' of ' || TO_CHAR(dcm_rows), 'INFO'
FROM agg
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
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN TRANCHE_REGION END) AS ecm_region,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN SETTLEMENT_TS END) AS dcm_settle,
         COUNT(CASE WHEN PRODUCT = 'DCM'
                     AND SYNDICATE_MEMBER_NAME LIKE '%|%'
                    THEN 1 END) AS dcm_multi_synd,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN TOTAL_FEE END) AS ecm_fee,
         COUNT(CASE WHEN PRODUCT = 'ECM'
                    THEN OVER_ALLOTMENT_AUTHORIZED_SHARES END) AS ecm_greenshoe
  FROM DGSTREAM.VW_TRANCHE_SUMMARY
)
SELECT '1h. ECM tranches with a region (INFO, expect ~5% UAT)' AS check_,
       '(info)' AS expected_,
       TO_CHAR(ecm_region) || ' of ' || TO_CHAR(ecm_rows) AS actual_,
       'INFO' AS verdict_
FROM agg
UNION ALL
SELECT '1k. DCM tranches with settlement_ts (INFO, expect ~50,198 UAT)',
       '(info)', TO_CHAR(dcm_settle), 'INFO'
FROM agg
UNION ALL
SELECT '1q. DCM tranches with MULTI-member syndicate list (INFO — rel 3;' ||
       ' 0 means the SYNM join did not land)',
       '(info)', TO_CHAR(dcm_multi_synd), 'INFO'
FROM agg
UNION ALL
SELECT '1x. ECM tranches w/ fees / greenshoe (INFO — final wave)', '(info)',
       TO_CHAR(ecm_fee) || ' fee / ' || TO_CHAR(ecm_greenshoe) || ' greenshoe',
       'INFO'
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
         SUM(CASE WHEN PRODUCT = 'DCM' THEN ORDER_ALLOCATION END) AS dcm_alloc,
         COUNT(CASE WHEN ORDER_OWNERSHIP = 'AWAY' THEN 1 END) AS away_,
         COUNT(CASE WHEN ORDER_OWNERSHIP = 'HOME' THEN 1 END) AS home_,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN INVESTOR_REGION END) AS dcm_geo,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN INVESTOR_CATEGORY END) AS dcm_cat,
         COUNT(SALES_PERSON) AS sales_
  FROM DGSTREAM.VW_ORDER_DETAIL
)
SELECT '1d. orders with billed_by (INFO, ~90/74% UAT)' AS check_,
       '(info)' AS expected_,
       TO_CHAR(billed_) || ' of ' || TO_CHAR(rows_) AS actual_,
       'INFO' AS verdict_
FROM agg
UNION ALL
SELECT '1j. ECM orders home vs away (INFO, release 2 — away was excluded)',
       '(info)',
       TO_CHAR(home_) || ' home / ' || TO_CHAR(away_) || ' away', 'INFO'
FROM agg
UNION ALL
SELECT '1r. DCM orders w/ investor geography (INFO, ~95% source — rel 3)',
       '(info)', TO_CHAR(dcm_geo), 'INFO' FROM agg
UNION ALL
SELECT '1s. DCM orders w/ investor type (INFO, ~67% source — rel 3)',
       '(info)', TO_CHAR(dcm_cat), 'INFO' FROM agg
UNION ALL
SELECT '1t. orders with SALES_PERSON (INFO, ~30% of DCM — rel 3)',
       '(info)', TO_CHAR(sales_), 'INFO' FROM agg
UNION ALL
SELECT '6. DCM allocation non-zero', 'Y',
       CASE WHEN dcm_alloc > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_alloc > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT '9. order grain (rows = PRODUCT+ORDER_ID)', 'Y',
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END FROM agg
ORDER BY 1;

-- E. HEDGE ORDER VIEW — ONE scan (new in V3).
WITH agg AS (
  SELECT /*+ MATERIALIZE */
         COUNT(*) AS rows_,
         COUNT(DISTINCT HEDGE_ORDER_ID) AS keys_,
         COUNT(DISTINCT INVESTOR_GP_ID) AS investors_,
         COUNT(HEDGE_MANAGER) AS managed_
  FROM DGSTREAM.VW_HEDGE_ORDER
)
SELECT '10. hedge orders (INFO, ~300,741 source)' AS check_, '(info)' AS expected_,
       TO_CHAR(rows_) || ' rows / ' || TO_CHAR(investors_) || ' investors / ' ||
       TO_CHAR(managed_) || ' managed' AS actual_, 'INFO' AS verdict_
FROM agg
UNION ALL
SELECT '10b. hedge-order grain', 'Y',
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END FROM agg
ORDER BY 1;

-- F. HEDGE TRADE VIEW — ONE scan (new in V3).
WITH agg AS (
  SELECT /*+ MATERIALIZE */
         COUNT(*) AS rows_, COUNT(DISTINCT HEDGE_TRADE_ID) AS keys_
  FROM DGSTREAM.VW_HEDGE_TRADE
)
SELECT '11. hedge trades (INFO, ~155,693 source)' AS check_, '(info)' AS expected_,
       TO_CHAR(rows_) AS actual_, 'INFO' AS verdict_ FROM agg
UNION ALL
SELECT '11b. hedge-trade grain', 'Y',
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END FROM agg
ORDER BY 1;

-- G. TRADE VIEW — ONE scan; now TWO branches.
WITH agg AS (
  SELECT /*+ MATERIALIZE */
         COUNT(*) AS rows_, COUNT(DISTINCT PRODUCT||'~'||TRADE_ID) AS keys_,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN 1 END) AS dcm_,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN 1 END) AS ecm_,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN FIRM_ACCOUNT_NUMBER END) AS firm_
  FROM DGSTREAM.VW_TRADE_DETAIL
)
SELECT '12. trades by product (INFO, ~489k DCM / ~724 ECM source)' AS check_,
       '(info)' AS expected_,
       TO_CHAR(dcm_) || ' DCM / ' || TO_CHAR(ecm_) || ' ECM / ' ||
       TO_CHAR(firm_) || ' w/ firm acct' AS actual_, 'INFO' AS verdict_
FROM agg
UNION ALL
SELECT '12b. trade grain', 'Y',
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END FROM agg
ORDER BY 1;

-- H. DESIGNATION VIEW — ONE scan (new in V3).
WITH agg AS (
  SELECT /*+ MATERIALIZE */
         COUNT(*) AS rows_, COUNT(DISTINCT DESIGNATION_ID) AS keys_,
         COUNT(FIRM_ACCOUNT) AS firm_
  FROM DGSTREAM.VW_DESIGNATION
)
SELECT '13. designations (INFO, ~10,696 source)' AS check_, '(info)' AS expected_,
       TO_CHAR(rows_) || ' rows / ' || TO_CHAR(firm_) || ' w/ firm acct'
         AS actual_, 'INFO' AS verdict_ FROM agg
UNION ALL
SELECT '13b. designation grain', 'Y',
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END FROM agg
ORDER BY 1;

-- I. TRADE SYNDICATE VIEW — expected EMPTY today (schema-only source;
-- forward-population possible). Any rows here = news, not a failure.
SELECT '14. trade-syndicate rows (INFO, source EMPTY today)' AS check_,
       '(info)' AS expected_, TO_CHAR(COUNT(*)) AS actual_, 'INFO' AS verdict_
FROM DGSTREAM.VW_TRADE_SYNDICATE;
