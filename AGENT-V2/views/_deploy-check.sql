-- ===========================================================================
-- POST-DEPLOY CHECK — run as a script (F5) after every view deploy and
-- screenshot into ~/Desktop/ADK. SELECTs only; never a session command.
-- Every non-INFO row must read PASS. INFO rows were measured on UAT — in
-- another environment judge zero-vs-healthy, not the exact number.
-- Each view is scanned at most once per product (a literal PRODUCT predicate
-- keeps Oracle to that branch set; QA 2026-09-23 hit the instance PGA limit
-- materialising every branch at once). Rows are labelled by SECTION. When a
-- view changes: regenerate the A counts (contract-test parser) and add the
-- wave's PASS/FAIL row to its section; retire INFO rows once they stop moving.
-- Rewritten 2026-10-05 (738 → ~330 lines); the history lives in git.
-- ===========================================================================

-- A0. WHICH REVISION IS DEPLOYED — expect today's date on every changed view.
SELECT object_name AS view_,
       TO_CHAR(last_ddl_time, 'DD-MON-YYYY HH24:MI') AS recreated_,
       'INFO' AS verdict_
FROM   all_objects
WHERE  owner = 'DGSTREAM' AND object_type = 'VIEW'
AND    object_name IN ('VW_DEAL_SUMMARY','VW_TRANCHE_SUMMARY','VW_ORDER_DETAIL','VW_TRADE_DETAIL','VW_HEDGE_ORDER','VW_HEDGE_TRADE','VW_DESIGNATION','VW_TRADE_SYNDICATE','VW_ENTITY_SEARCH')
ORDER BY object_name;

-- A. STRUCTURE — one row per view: the column count must equal the repo's
-- projection (views/_reference/view-columns.md). A mismatch names the view
-- that is not this revision; it can never ORA-00904.
SELECT check_, expected_, actual_,
       CASE WHEN actual_ = expected_ THEN 'PASS' ELSE 'FAIL' END AS verdict_
FROM (
  SELECT 'A01. VW_DEAL_SUMMARY has every repo column' AS check_, '43' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns WHERE owner = 'DGSTREAM' AND table_name = 'VW_DEAL_SUMMARY'
  UNION ALL
  SELECT 'A02. VW_TRANCHE_SUMMARY has every repo column' AS check_, '89' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns WHERE owner = 'DGSTREAM' AND table_name = 'VW_TRANCHE_SUMMARY'
  UNION ALL
  SELECT 'A03. VW_ORDER_DETAIL has every repo column' AS check_, '65' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns WHERE owner = 'DGSTREAM' AND table_name = 'VW_ORDER_DETAIL'
  UNION ALL
  SELECT 'A04. VW_TRADE_DETAIL has every repo column' AS check_, '30' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns WHERE owner = 'DGSTREAM' AND table_name = 'VW_TRADE_DETAIL'
  UNION ALL
  SELECT 'A05. VW_HEDGE_ORDER has every repo column' AS check_, '34' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns WHERE owner = 'DGSTREAM' AND table_name = 'VW_HEDGE_ORDER'
  UNION ALL
  SELECT 'A06. VW_HEDGE_TRADE has every repo column' AS check_, '33' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns WHERE owner = 'DGSTREAM' AND table_name = 'VW_HEDGE_TRADE'
  UNION ALL
  SELECT 'A07. VW_DESIGNATION has every repo column' AS check_, '33' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns WHERE owner = 'DGSTREAM' AND table_name = 'VW_DESIGNATION'
  UNION ALL
  SELECT 'A08. VW_TRADE_SYNDICATE has every repo column' AS check_, '8' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns WHERE owner = 'DGSTREAM' AND table_name = 'VW_TRADE_SYNDICATE'
  UNION ALL
  SELECT 'A09. VW_ENTITY_SEARCH has every repo column' AS check_, '8' AS expected_,
         TO_CHAR(COUNT(*)) AS actual_
  FROM   all_tab_columns WHERE owner = 'DGSTREAM' AND table_name = 'VW_ENTITY_SEARCH'
  UNION ALL
  SELECT 'A10. TRANCHE_SIZE is NUMBER on order + tranche', 'NUMBER,NUMBER',
         LISTAGG(data_type, ',') WITHIN GROUP (ORDER BY table_name)
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND column_name = 'TRANCHE_SIZE'
  AND    table_name IN ('VW_ORDER_DETAIL','VW_TRANCHE_SUMMARY')
  UNION ALL
  SELECT 'A11. SECURITIES_MATURITY stays VARCHAR2 (DATE reverted, ORA-01790)', 'VARCHAR2',
         MAX(data_type)
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM' AND table_name = 'VW_TRANCHE_SUMMARY'
  AND    column_name = 'SECURITIES_MATURITY'
  UNION ALL
  -- Every cast metric column publishes precision/scale, or Starburst maps
  -- decimal(38,0) and fractional values fail to read.
  SELECT 'A12. metric columns with no declared scale', '0', TO_CHAR(COUNT(*))
  FROM   all_tab_columns
  WHERE  owner = 'DGSTREAM'
  AND    table_name IN ('VW_DEAL_SUMMARY','VW_TRANCHE_SUMMARY','VW_ORDER_DETAIL','VW_TRADE_DETAIL','VW_HEDGE_ORDER','VW_HEDGE_TRADE','VW_DESIGNATION','VW_TRADE_SYNDICATE','VW_ENTITY_SEARCH')
  AND    data_type = 'NUMBER' AND data_scale IS NULL
  AND    column_name IN ('ORDER_AMOUNT','ORDER_DEMAND_QTY','ORDER_ALLOCATION',
                         'TRANCHE_SIZE','DEAL_SIZE','ACTIVE_PRICE','ORDER_SIZE_CHANGE',
                         'TOTAL_DEMAND','TOTAL_ALLOCATION','SUBSCRIPTION_RATIO',
                         'ORDER_COUNT','INVESTOR_COUNT','TRANCHE_COUNT',
                         'DEAL_FEE_MM','DEAL_SIZE_MM','BASE_PRICE',
                         'REOFFER_LOW_PRICE','REOFFER_HIGH_PRICE','FX_RATE','PRICE',
                         'TOTAL_FEE','UNDERWRITING_FEE','MANAGEMENT_FEES',
                         'SELLING_CONCESSION_FEE','PRAECIPIUM_FEES','RETAIL_UW_FEE',
                         'GROSS_SPREAD_PER_FEE','DESIGNATION_FEE',
                         'OVER_ALLOTMENT_AUTHORIZED_SHARES','OVER_ALLOTMENT_EXERCISED_SHARES',
                         'PRIMARY_SHARES','SECONDARY_SHARES','LAST_CLOSE_BEFORE_OFFER',
                         'LAST_CLOSE_BEFORE_LAUNCH','INITIAL_DEAL_SIZE','TRANCHE_OFFER_AMOUNT',
                         'TRADE_SIZE','TRADE_ALLOCATION','PRICE_BASIS_VALUE',
                         'TRADE_PRICE','COMMISSION_RATE','HEDGE_AMOUNT',
                         'HEDGE_ISN_AMOUNT','HEDGE_PCT_FACE','SECURITY_COUPON',
                         'QUANTITY','DESIGNABLE_SHARES','POT_SPLIT',
                         'POT_SPLIT_PERCENTAGE','SELLING_CONCESSION','UNDERWRITING_FEES',
                         'EV','DESIGNATION_AMT','ADJUSTED_DESIGNATION_AMT',
                         'ADJUSTED_DESIGNATION_PCT','CARVEOUT_AMT','DISTRIBUTED_CARVEOUT',
                         'ENTITY_ACTIVITY_COUNT')
)
ORDER BY check_;

-- B-ECM. DEAL VIEW, ECM branches (OPUS + Ipreo) — one scan.
WITH agg AS (
  SELECT /*+ MATERIALIZE NO_PARALLEL */
         COUNT(*) AS rows_,
         COUNT(DISTINCT DEAL_ID) AS keys_,
         COUNT(CASE WHEN CURRENCIES IS NOT NULL
                     AND REGEXP_LIKE(CURRENCIES, '[A-Za-z]') THEN 1 END) AS ecm_alpha,
         COUNT(DISTINCT CASE WHEN CURRENCIES IS NOT NULL
                              AND REGEXP_LIKE(CURRENCIES, '(^|\| )[0-9]+( \||$)')
                             THEN DEAL_ID END) AS ecm_unmapped,
         COUNT(CASE WHEN TOTAL_ALLOCATION > 0 THEN 1 END) AS ecm_alloc_deals,
         COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN 1 END) AS ecm_ipreo_rows,
         COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') AND ORDER_COUNT > 0 THEN 1 END) AS ecm_ipreo_ordered,
         COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN LAST_PRICED END) AS ecm_ipreo_priced,
         COUNT(DEAL_CLASS) AS ecm_class,
         COUNT(CASE WHEN SIZE_UNIT = 'bonds' THEN 1 END) AS ecm_bond_unit
  FROM DGSTREAM.VW_DEAL_SUMMARY
  WHERE PRODUCT = 'ECM'
)
SELECT 'B01. deal grain, ECM (rows = DEAL_ID)' AS check_, 'Y' AS expected_,
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END AS verdict_ FROM agg
UNION ALL
SELECT 'B02. ECM currency names resolve (a broken CURRENCY_NAME join = zero alphabetic codes)', 'Y',
       CASE WHEN ecm_alpha > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN ecm_alpha > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'B03. ECM deals with an unmapped numeric currency token (INFO, UAT ~377)', '(info)',
       TO_CHAR(ecm_unmapped), 'INFO' FROM agg
UNION ALL
SELECT 'B04. ECM deals carry allocation (OD join intact)', 'Y',
       CASE WHEN ecm_alloc_deals > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN ecm_alloc_deals > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'B05. Ipreo ECM deals landed (10-digit ids; UAT ~19.6k)', 'Y',
       CASE WHEN ecm_ipreo_rows > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN ecm_ipreo_rows > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'B06. Ipreo ECM deals carry LAST_PRICED (date windows need it)', 'Y',
       CASE WHEN ecm_ipreo_priced > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN ecm_ipreo_priced > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'B07. Ipreo ECM deals with orders (INFO — 0 = OD key mismatch)', '(info)',
       TO_CHAR(ecm_ipreo_ordered) || ' of ' || TO_CHAR(ecm_ipreo_rows), 'INFO' FROM agg
UNION ALL
SELECT 'B08. ECM deals with DEAL_CLASS / bonds unit (INFO — batch C; OPUS ~25.8k classed)', '(info)',
       TO_CHAR(ecm_class) || ' classed / ' || TO_CHAR(ecm_bond_unit) || ' bonds of ' || TO_CHAR(rows_), 'INFO' FROM agg
ORDER BY 1;

-- B-DCM. DEAL VIEW, DCM branch — one scan that touches NO order-book column,
-- so Oracle drops the 1.25M-row order aggregate (lever C): seconds, not
-- minutes. B11 below is the only row that needs the order book.
WITH agg AS (
  SELECT /*+ MATERIALIZE NO_PARALLEL */
         COUNT(*) AS rows_,
         COUNT(DISTINCT DEAL_ID) AS keys_,
         COUNT(CASE WHEN REGEXP_LIKE(CURRENCIES,
                     '(^|\| )([A-Za-z]+)( \|.*\| | \| )\2( \||$)') THEN 1 END) AS dcm_dupcur,
         COUNT(CASE WHEN UPPER(DEAL_STATUS) IN ('CANCELLED', 'POSTPONED', 'DELETED', 'ARCHIVED')
                    THEN 1 END) AS dcm_excluded_status,
         COUNT(DCM_DEAL_CLASS) AS dcm_class,
         COUNT(ISSUER_COUNTRY) AS dcm_country
  FROM DGSTREAM.VW_DEAL_SUMMARY
  WHERE PRODUCT = 'DCM'
)
SELECT 'B09. deal grain, DCM (rows = DEAL_ID)' AS check_, 'Y' AS expected_,
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END AS verdict_ FROM agg
UNION ALL
SELECT 'B10. DCM currency list deduped', 'Y',
       CASE WHEN dcm_dupcur = 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_dupcur = 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'B12. no DCM deal carries an excluded status (status exclusion 2026-09-28)', 'Y',
       CASE WHEN dcm_excluded_status = 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_excluded_status = 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'B13. DCM deals (INFO — UAT ~46.3k after the exclusion)', '(info)',
       TO_CHAR(rows_), 'INFO' FROM agg
UNION ALL
SELECT 'B14. DCM deals with DCM_DEAL_CLASS / ISSUER_COUNTRY (INFO — batch C)', '(info)',
       TO_CHAR(dcm_class) || ' class / ' || TO_CHAR(dcm_country) || ' country of ' || TO_CHAR(rows_), 'INFO' FROM agg
ORDER BY 1;

-- B-DCM-2. THE ORDER-BOOK ROW — aggregates every DCM order (the K3 class:
-- minutes on UAT; on QA it runs into the instance PGA limit, INC open). Run
-- it on UAT after a change to the deal view's OC block or the order
-- exclusions; skip it on QA.
SELECT 'B11. DCM deals carry demand and orders (hoisted OC join intact)' AS check_, 'Y' AS expected_,
       CASE WHEN COUNT(CASE WHEN TOTAL_DEMAND > 0 THEN 1 END) > 0
             AND COUNT(CASE WHEN ORDER_COUNT > 0 THEN 1 END) > 0 THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN COUNT(CASE WHEN TOTAL_DEMAND > 0 THEN 1 END) > 0
             AND COUNT(CASE WHEN ORDER_COUNT > 0 THEN 1 END) > 0 THEN 'PASS' ELSE 'FAIL' END AS verdict_
FROM DGSTREAM.VW_DEAL_SUMMARY
WHERE PRODUCT = 'DCM';

-- C. TRANCHE VIEW — one scan, all branches.
WITH agg AS (
  SELECT /*+ MATERIALIZE */
         COUNT(*) AS rows_,
         COUNT(DISTINCT PRODUCT||'~'||DEAL_ID||'~'||TRANCHE_ID) AS keys_,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN 1 END) AS ecm_rows,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN 1 END) AS dcm_rows,
         COUNT(CASE WHEN IDENTIFIER_TYPE <> UPPER(IDENTIFIER_TYPE) THEN 1 END) AS lowercase_idtypes,
         COUNT(CASE WHEN PRODUCT = 'DCM' AND DEAL_SHARING_TYPE = 'SOLO' THEN 1 END) AS dcm_solo,
         COUNT(CASE WHEN PRODUCT = 'ECM' AND REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN 1 END) AS ecm_ipreo_rows,
         COUNT(CASE WHEN PRODUCT = 'ECM' AND REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN TOTAL_FEE END) AS ecm_ipreo_fee,
         COUNT(CASE WHEN PRODUCT = 'ECM' AND REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN PRICE END) AS ecm_ipreo_price,
         COUNT(CASE WHEN PRODUCT = 'DCM' AND UPPER(TRANCHE_STATUS) IN ('CANCELLED', 'POSTPONED', 'DELETED', 'ARCHIVED')
                    THEN 1 END) AS dcm_excluded_tr,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN LAST_CLOSE_BEFORE_OFFER END) AS ecm_last_close,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN PRIMARY_SHARES END) AS ecm_primary,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN TRANCHE_OFFER_AMOUNT END) AS ecm_offer_amt,
         COUNT(CASE WHEN PRODUCT = 'ECM' THEN INITIAL_DEAL_SIZE END) AS ecm_initial,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN IS_CALLABLE END) AS dcm_callable,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN IS_TAP END) AS dcm_tap,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN GOVERNING_LAW END) AS dcm_law,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN EXCHANGE END) AS dcm_exchange,
         COUNT(CASE WHEN PRODUCT = 'DCM' THEN ISSUER_COUNTRY END) AS dcm_country
  FROM DGSTREAM.VW_TRANCHE_SUMMARY
)
SELECT 'C01. tranche grain (rows = PRODUCT+DEAL+TRANCHE)' AS check_, 'Y' AS expected_,
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END AS verdict_ FROM agg
UNION ALL
SELECT 'C02. identifier types UPPER-normalised', 'Y',
       CASE WHEN lowercase_idtypes = 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN lowercase_idtypes = 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'C03. DCM SOLO rule landed (plain Citigroup counted; UAT ~14.2k)', 'Y',
       CASE WHEN dcm_solo > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_solo > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'C04. Ipreo ECM tranches landed (UAT ~20k)', 'Y',
       CASE WHEN ecm_ipreo_rows > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN ecm_ipreo_rows > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'C05. no DCM tranche carries an excluded status (cancelled/postponed/deleted/archived)', 'Y',
       CASE WHEN dcm_excluded_tr = 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_excluded_tr = 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'C06. DCM tranches (INFO — UAT ~73.5k after the exclusion)', '(info)',
       TO_CHAR(dcm_rows), 'INFO' FROM agg
UNION ALL
SELECT 'C07. Ipreo tranches with fee / price (INFO — fee table + product detail joins)', '(info)',
       TO_CHAR(ecm_ipreo_fee) || ' fee / ' || TO_CHAR(ecm_ipreo_price) || ' price of ' || TO_CHAR(ecm_ipreo_rows), 'INFO' FROM agg
UNION ALL
SELECT 'C08. ECM tranches: last close / primary shares / offer amount / initial size (INFO — batch C; raw UAT 27% / 72% / 78% / 80%)', '(info)',
       TO_CHAR(ecm_last_close) || ' / ' || TO_CHAR(ecm_primary) || ' / ' || TO_CHAR(ecm_offer_amt) || ' / ' || TO_CHAR(ecm_initial) || ' of ' || TO_CHAR(ecm_rows), 'INFO' FROM agg
UNION ALL
SELECT 'C09. DCM tranches: callable / tap / governing law / exchange / country (INFO — batch C; raw UAT ~14% / 13% / 13% / 13% / 27%)', '(info)',
       TO_CHAR(dcm_callable) || ' / ' || TO_CHAR(dcm_tap) || ' / ' || TO_CHAR(dcm_law) || ' / ' || TO_CHAR(dcm_exchange) || ' / ' || TO_CHAR(dcm_country) || ' of ' || TO_CHAR(dcm_rows), 'INFO' FROM agg
ORDER BY 1;

-- D-ECM. ORDER VIEW, ECM branches — one scan.
WITH agg AS (
  SELECT /*+ MATERIALIZE NO_PARALLEL */
         COUNT(*) AS rows_,
         COUNT(DISTINCT ORDER_ID) AS keys_,
         COUNT(ORDER_DEMAND_QTY) AS ecm_demand,
         COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN 1 END) AS ecm_ipreo_rows,
         COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$')
                     AND ORDER_STATUS IN ('CANCELLED', 'DELETED', 'PASS') THEN 1 END) AS ecm_ipreo_excluded,
         COUNT(CASE WHEN ORDER_ALLOCATION IS NULL THEN 1 END) AS ecm_alloc_null
  FROM DGSTREAM.VW_ORDER_DETAIL
  WHERE PRODUCT = 'ECM'
)
SELECT 'D01. order grain, ECM (rows = ORDER_ID)' AS check_, 'Y' AS expected_,
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END AS verdict_ FROM agg
UNION ALL
SELECT 'D02. Ipreo ECM orders landed (UAT ~659k)', 'Y',
       CASE WHEN ecm_ipreo_rows > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN ecm_ipreo_rows > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'D03. Ipreo cancelled/deleted/pass orders excluded', 'Y',
       CASE WHEN ecm_ipreo_excluded = 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN ecm_ipreo_excluded = 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'D04. ECM orders with a share-equivalent indication (INFO — IOI rebuild; UAT ~72%)', '(info)',
       TO_CHAR(ecm_demand) || ' of ' || TO_CHAR(rows_), 'INFO' FROM agg
UNION ALL
SELECT 'D05. ECM orders with no allocation recorded (INFO — NULL kept since 2026-09-29)', '(info)',
       TO_CHAR(ecm_alloc_null) || ' of ' || TO_CHAR(rows_), 'INFO' FROM agg
ORDER BY 1;

-- D-DCM. ORDER VIEW, DCM branch — one scan (the large one).
WITH agg AS (
  SELECT /*+ MATERIALIZE NO_PARALLEL */
         COUNT(*) AS rows_,
         COUNT(DISTINCT ORDER_ID) AS keys_,
         SUM(ORDER_ALLOCATION) AS dcm_alloc,
         COUNT(PRODUCT_CLASS) AS dcm_class,
         SUM(CASE WHEN UPPER(ORDER_STATUS) NOT IN ('ACCEPTED', 'BOOKED', 'UPDATED', 'NEW') THEN 1 ELSE 0 END) AS dcm_out_of_scope,
         COUNT(CASE WHEN ORDER_STATUS IS NULL THEN 1 END) AS dcm_null_status,
         COUNT(CASE WHEN ORDER_ALLOCATION IS NULL THEN 1 END) AS dcm_alloc_null
  FROM DGSTREAM.VW_ORDER_DETAIL
  WHERE PRODUCT = 'DCM'
)
SELECT 'D06. order grain, DCM (rows = ORDER_ID)' AS check_, 'Y' AS expected_,
       CASE WHEN rows_ = keys_ THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN rows_ = keys_ THEN 'PASS' ELSE 'FAIL' END AS verdict_ FROM agg
UNION ALL
SELECT 'D07. DCM allocation present', 'Y',
       CASE WHEN dcm_alloc > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_alloc > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'D08. DCM orders carry product_class (ferry)', 'Y',
       CASE WHEN dcm_class > 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_class > 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'D09. DCM order statuses in scope only (accepted/booked/updated/new)', 'Y',
       CASE WHEN dcm_out_of_scope = 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_out_of_scope = 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'D10. no NULL-status DCM orders (the RQ load is gone)', 'Y',
       CASE WHEN dcm_null_status = 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN dcm_null_status = 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
UNION ALL
SELECT 'D11. DCM orders (INFO — UAT ~1.25M after the exclusion)', '(info)',
       TO_CHAR(rows_), 'INFO' FROM agg
UNION ALL
SELECT 'D12. DCM orders with no allocation recorded (INFO — NULL kept since 2026-09-29)', '(info)',
       TO_CHAR(dcm_alloc_null) || ' of ' || TO_CHAR(rows_), 'INFO' FROM agg
ORDER BY 1;

-- E. THE OTHER FIVE VIEWS — grain only, one scan each.
SELECT 'E1. hedge-order grain' AS check_, 'Y' AS expected_,
       CASE WHEN COUNT(*) = COUNT(DISTINCT HEDGE_ORDER_ID) THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN COUNT(*) = COUNT(DISTINCT HEDGE_ORDER_ID) THEN 'PASS' ELSE 'FAIL' END AS verdict_
FROM DGSTREAM.VW_HEDGE_ORDER;

SELECT 'E2. hedge-trade grain' AS check_, 'Y' AS expected_,
       CASE WHEN COUNT(*) = COUNT(DISTINCT HEDGE_TRADE_ID) THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN COUNT(*) = COUNT(DISTINCT HEDGE_TRADE_ID) THEN 'PASS' ELSE 'FAIL' END AS verdict_
FROM DGSTREAM.VW_HEDGE_TRADE;

SELECT 'E3. trade grain (both products)' AS check_, 'Y' AS expected_,
       CASE WHEN COUNT(*) = COUNT(DISTINCT PRODUCT||'~'||TRADE_ID) THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN COUNT(*) = COUNT(DISTINCT PRODUCT||'~'||TRADE_ID) THEN 'PASS' ELSE 'FAIL' END AS verdict_
FROM DGSTREAM.VW_TRADE_DETAIL;

SELECT 'E4. designation grain' AS check_, 'Y' AS expected_,
       CASE WHEN COUNT(*) = COUNT(DISTINCT DESIGNATION_ID) THEN 'Y' ELSE 'N' END AS actual_,
       CASE WHEN COUNT(*) = COUNT(DISTINCT DESIGNATION_ID) THEN 'PASS' ELSE 'FAIL' END AS verdict_
FROM DGSTREAM.VW_DESIGNATION;

SELECT 'E5. trade-syndicate rows (INFO — source empty today; rows = news)' AS check_,
       '(info)' AS expected_, TO_CHAR(COUNT(*)) AS actual_, 'INFO' AS verdict_
FROM DGSTREAM.VW_TRADE_SYNDICATE;

-- ===========================================================================
-- K. TIMING PROBES — run with elapsed time visible; the seconds are the
-- result. Literal ids are the agent's shape (a scalar-subquery id is
-- evaluated after the dedupe window and times 30x slower).
-- ===========================================================================
-- K1. Deal-scoped DCM orders (lever B: the deal id pushes into the window).
SELECT 'K1 deal-scoped DCM orders, literal id' AS probe_, TO_CHAR(COUNT(*)) || ' rows' AS actual_
FROM DGSTREAM.VW_ORDER_DETAIL WHERE PRODUCT = 'DCM' AND DEAL_ID = 'I-260831-113859365632';

-- K2. DCM deal count touching no demand column (lever C: order-book join eliminated).
SELECT 'K2 DCM deal count, no demand cols' AS probe_, TO_CHAR(COUNT(*)) || ' DCM deals' AS actual_
FROM DGSTREAM.VW_DEAL_SUMMARY WHERE PRODUCT = 'DCM';

-- K3. Deal-scoped Ipreo ECM orders (Caris Life Sciences on UAT) — K1's class.
SELECT 'K3 deal-scoped Ipreo ECM orders, literal id' AS probe_,
       TO_CHAR(COUNT(*)) || ' rows / ' || TO_CHAR(ROUND(SUM(ORDER_DEMAND_QTY))) || ' demand' AS actual_
FROM DGSTREAM.VW_ORDER_DETAIL WHERE PRODUCT = 'ECM' AND DEAL_ID = '1448094247';

-- K4. ECM deal count, both ECM branches, no demand column.
SELECT 'K4 ECM deal count, no demand cols' AS probe_, TO_CHAR(COUNT(*)) || ' ECM deals' AS actual_
FROM DGSTREAM.VW_DEAL_SUMMARY WHERE PRODUCT = 'ECM';

-- K5. Full entity-search pass (lever D baseline, measured 40 s before the rewrite).
SELECT 'K5 entity search full pass' AS probe_, TO_CHAR(COUNT(*)) || ' entities' AS actual_
FROM DGSTREAM.VW_ENTITY_SEARCH;
