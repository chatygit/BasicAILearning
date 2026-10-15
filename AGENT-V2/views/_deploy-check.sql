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
  SELECT 'A03. VW_ORDER_DETAIL has every repo column' AS check_, '70' AS expected_,
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
         COUNT(CASE WHEN TOTAL_ALLOCATION > 0 THEN 1 END) AS ecm_alloc_deals,
         COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN 1 END) AS ecm_ipreo_rows,
         COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN LAST_PRICED END) AS ecm_ipreo_priced,
         COUNT(CASE WHEN NOT REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN ISSUER_NAME END) AS opus_issuer,
         COUNT(CASE WHEN NOT REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$')
                     AND UPPER(TRIM(ISSUER_NAME)) = UPPER(TRIM(DEAL_NAME)) THEN 1 END) AS opus_issuer_eq_deal
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
-- Defect item 3 (2026-10-07): issuer_name must not be a copy of deal_name.
-- OPUS: party master → orderbook issuer by GFCID → source issuer; a copy on
-- more than half the deals = the source is filling issuer with the deal
-- name. Ipreo: equal BY CONSTRUCTION today (deal name, tranche parenthetical
-- stripped — the mirror has no issuer) until an Ipreo issuer source lands.
SELECT 'B15. OPUS ECM issuer_name is not a copy of deal_name on most deals (item 3)', 'Y',
       CASE WHEN opus_issuer > 0 AND opus_issuer_eq_deal * 2 > opus_issuer THEN 'N' ELSE 'Y' END,
       CASE WHEN opus_issuer > 0 AND opus_issuer_eq_deal * 2 > opus_issuer THEN 'FAIL' ELSE 'PASS' END FROM agg
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
                    THEN 1 END) AS dcm_excluded_status
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
         COUNT(CASE WHEN IDENTIFIER_TYPE <> UPPER(IDENTIFIER_TYPE) THEN 1 END) AS lowercase_idtypes,
         COUNT(CASE WHEN PRODUCT = 'DCM' AND DEAL_SHARING_TYPE = 'SOLO' THEN 1 END) AS dcm_solo,
         COUNT(CASE WHEN PRODUCT = 'ECM' AND REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN 1 END) AS ecm_ipreo_rows,
         COUNT(CASE WHEN PRODUCT = 'DCM' AND UPPER(TRANCHE_STATUS) IN ('CANCELLED', 'POSTPONED', 'DELETED', 'ARCHIVED')
                    THEN 1 END) AS dcm_excluded_tr,
         COUNT(CASE WHEN PRODUCT = 'ECM' AND NOT REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN PRODUCT_TYPE END) AS opus_ptype,
         COUNT(CASE WHEN PRODUCT = 'ECM' AND NOT REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$')
                     AND UPPER(TRIM(PRODUCT_TYPE)) = UPPER(TRIM(EQUITY_TYPE)) THEN 1 END) AS opus_ptype_eq,
         COUNT(CASE WHEN PRODUCT = 'ECM' AND REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN PRODUCT_TYPE END) AS ipreo_ptype,
         COUNT(CASE WHEN PRODUCT = 'ECM' AND REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$')
                     AND UPPER(TRIM(PRODUCT_TYPE)) = UPPER(TRIM(EQUITY_TYPE)) THEN 1 END) AS ipreo_ptype_eq
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
-- Defect item 6 (2026-10-07): product_type must come from the product's
-- securityType, not the deal's equity type. If it is derived from equity
-- type it EQUALS equity_type on every populated row; a real security type
-- diverges on most rows and has a richer vocabulary.
SELECT 'C10. OPUS ECM product_type is not a copy of equity_type (item 6)', 'Y',
       CASE WHEN opus_ptype > 0 AND opus_ptype_eq = opus_ptype THEN 'N' ELSE 'Y' END,
       CASE WHEN opus_ptype > 0 AND opus_ptype_eq = opus_ptype THEN 'FAIL' ELSE 'PASS' END FROM agg
UNION ALL
SELECT 'C11. Ipreo ECM product_type is not a copy of equity_type (item 6)', 'Y',
       CASE WHEN ipreo_ptype > 0 AND ipreo_ptype_eq = ipreo_ptype THEN 'N' ELSE 'Y' END,
       CASE WHEN ipreo_ptype > 0 AND ipreo_ptype_eq = ipreo_ptype THEN 'FAIL' ELSE 'PASS' END FROM agg
ORDER BY 1;

-- D-ECM. ORDER VIEW, ECM branches — one scan.
WITH agg AS (
  SELECT /*+ MATERIALIZE NO_PARALLEL */
         COUNT(*) AS rows_,
         COUNT(DISTINCT ORDER_ID) AS keys_,
         COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN 1 END) AS ecm_ipreo_rows,
         COUNT(CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$')
                     AND ORDER_STATUS IN ('CANCELLED', 'DELETED', 'PASS') THEN 1 END) AS ecm_ipreo_excluded,
         COUNT(CASE WHEN ORDER_AMOUNT <> NVL(LIMIT_VALUE, 0) THEN 1 END) AS ecm_two_limits
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
SELECT 'D16. ECM ORDER_AMOUNT equals LIMIT_VALUE (one limit per order, 2026-10-14)', 'Y',
       CASE WHEN ecm_two_limits = 0 THEN 'Y' ELSE 'N' END,
       CASE WHEN ecm_two_limits = 0 THEN 'PASS' ELSE 'FAIL' END FROM agg
ORDER BY 1;

-- D-DCM. ORDER VIEW, DCM branch — one scan (the large one).
WITH agg AS (
  SELECT /*+ MATERIALIZE NO_PARALLEL */
         COUNT(*) AS rows_,
         COUNT(DISTINCT ORDER_ID) AS keys_,
         SUM(ORDER_ALLOCATION) AS dcm_alloc,
         COUNT(PRODUCT_CLASS) AS dcm_class,
         SUM(CASE WHEN UPPER(ORDER_STATUS) NOT IN ('ACCEPTED', 'BOOKED', 'UPDATED', 'NEW') THEN 1 ELSE 0 END) AS dcm_out_of_scope
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
