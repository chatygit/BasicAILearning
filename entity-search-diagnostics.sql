-- =====================================================================
-- Entity-search performance diagnostics — run in SQL Developer, send output
-- Purpose: decide between (A) materialized entity dimension, (B) function-based
-- indexes, (C) query restructuring in config only, or a combination.
-- Swap :NAME below for a real, reasonably common name (e.g. BLACKROCK).
-- =====================================================================
DEFINE NAME    = 'BLACKROCK'
DEFINE PATTERN = '%BLACKROCK%'

-- ---------------------------------------------------------------------
-- 1. CARDINALITY PROFILE — how much scanning is inherent?
--    The ratio rows : distinct-names IS the amplification factor we pay
--    on every single entity search.
-- ---------------------------------------------------------------------
SELECT COUNT(*)                        AS view_rows,
       COUNT(DISTINCT DEAL_ID)         AS deals,
       COUNT(DISTINCT TRANCHE_ID)      AS tranches,
       COUNT(DISTINCT ORDER_ID)        AS orders,
       COUNT(DISTINCT INVESTOR_NAME)   AS investor_names,
       COUNT(DISTINCT GPNUM)           AS investor_ids,
       COUNT(DISTINCT ISSUER_NAME)     AS issuer_names,
       COUNT(DISTINCT DEAL_NAME)       AS deal_names
FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY;

-- ---------------------------------------------------------------------
-- 2. WHAT IS THE VIEW? plain view (re-joins every query) or materialized?
-- ---------------------------------------------------------------------
SELECT object_type FROM all_objects
 WHERE owner = 'DGSTREAM' AND object_name = 'VW_DEAL_ORDER_SUMMARY';

SELECT text FROM all_views
 WHERE owner = 'DGSTREAM' AND view_name = 'VW_DEAL_ORDER_SUMMARY';   -- the join underneath

-- ---------------------------------------------------------------------
-- 3. INDEX INVENTORY on the base tables behind the view
--    (esp. any index on the NAME columns, and any function-based index)
-- ---------------------------------------------------------------------
SELECT i.table_name, i.index_name, i.index_type, i.uniqueness,
       LISTAGG(c.column_name, ', ') WITHIN GROUP (ORDER BY c.column_position) AS cols
  FROM all_indexes i
  JOIN all_ind_columns c
    ON c.index_owner = i.owner AND c.index_name = i.index_name
 WHERE i.table_owner = 'DGSTREAM'
 GROUP BY i.table_name, i.index_name, i.index_type, i.uniqueness
 ORDER BY i.table_name, i.index_name;

SELECT table_name, column_expression          -- function-based index expressions
  FROM all_ind_expressions
 WHERE index_owner = 'DGSTREAM';

-- ---------------------------------------------------------------------
-- 4A. RUNTIME PLAN — the TYPED template we actually ship (investor_name)
--     GATHER_PLAN_STATISTICS gives real vs estimated rows per step.
-- ---------------------------------------------------------------------
SELECT /*+ GATHER_PLAN_STATISTICS entity_typed */ *
FROM (
  SELECT INVESTOR_NAME, GPNUM, DEAL_COUNT, LAST_ACTIVE, CATEGORY, REGION, PRODUCTS,
         is_exact, is_sub,
         MAX(is_exact) OVER () AS any_exact,
         MAX(is_sub)   OVER () AS any_sub
  FROM (
    SELECT INVESTOR_NAME, GPNUM,
           COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT,
           MAX(PRICING_TS)         AS LAST_ACTIVE,
           MAX(INVESTOR_CATEGORY)  AS CATEGORY,
           MAX(INVESTOR_REGION)    AS REGION,
           CASE WHEN COUNT(DISTINCT PRODUCT) = 2 THEN 'ECM+DCM' ELSE MAX(PRODUCT) END AS PRODUCTS,
           MAX(CASE WHEN UPPER(INVESTOR_NAME) = UPPER(&NAME) THEN 1 ELSE 0 END) AS is_exact,
           MAX(CASE WHEN UPPER(INVESTOR_NAME) LIKE UPPER(&PATTERN) THEN 1 ELSE 0 END) AS is_sub
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
    WHERE PRODUCT IN ('ECM', 'DCM')
      AND ( UPPER(INVESTOR_NAME) LIKE UPPER(&PATTERN)
         OR SOUNDEX(UPPER(INVESTOR_NAME)) = SOUNDEX(UPPER(&NAME)) )
    GROUP BY INVESTOR_NAME, GPNUM
  )
)
WHERE is_exact = 1 OR (any_exact = 0 AND is_sub = 1) OR (any_exact = 0 AND any_sub = 0)
ORDER BY is_exact DESC, is_sub DESC, DEAL_COUNT DESC, LAST_ACTIVE DESC
FETCH FIRST 50 ROWS ONLY;

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST +COST +BYTES'));

-- ---------------------------------------------------------------------
-- 4B. RUNTIME PLAN — the UNTYPED default template (6 unsargable predicates
--     across 3 name columns). Expect this to be the worst case.
-- ---------------------------------------------------------------------
SELECT /*+ GATHER_PLAN_STATISTICS entity_default */ DEAL_ID, DEAL_NAME, INVESTOR_NAME, GPNUM, ISSUER_NAME, GFCID
FROM (
  SELECT DISTINCT DEAL_ID, DEAL_NAME, INVESTOR_NAME, GPNUM, ISSUER_NAME, GFCID
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN ('ECM', 'DCM')
     AND ( UPPER(DEAL_NAME)     LIKE UPPER(&PATTERN)
        OR UPPER(INVESTOR_NAME) LIKE UPPER(&PATTERN)
        OR UPPER(ISSUER_NAME)   LIKE UPPER(&PATTERN)
        OR SOUNDEX(UPPER(DEAL_NAME))     = SOUNDEX(UPPER(&NAME))
        OR SOUNDEX(UPPER(INVESTOR_NAME)) = SOUNDEX(UPPER(&NAME))
        OR SOUNDEX(UPPER(ISSUER_NAME))   = SOUNDEX(UPPER(&NAME)) )
)
FETCH FIRST 50 ROWS ONLY;

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST +COST +BYTES'));

-- ---------------------------------------------------------------------
-- 5. CHEAP-PROBE COMPARISON — would an exact-first two-step be dramatically
--    cheaper? (This is the config-only fix; no DB change required.)
--    Compare its A-Time against 4A.
-- ---------------------------------------------------------------------
SELECT /*+ GATHER_PLAN_STATISTICS entity_exact_probe */ INVESTOR_NAME, GPNUM,
       COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT, MAX(PRICING_TS) AS LAST_ACTIVE
  FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
 WHERE PRODUCT IN ('ECM', 'DCM')
   AND UPPER(INVESTOR_NAME) = UPPER(&NAME)
 GROUP BY INVESTOR_NAME, GPNUM
 FETCH FIRST 50 ROWS ONLY;

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST +COST +BYTES'));

-- prefix form: the ONLY name predicate a b-tree/FBI can seek on
SELECT /*+ GATHER_PLAN_STATISTICS entity_prefix_probe */ INVESTOR_NAME, GPNUM,
       COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT
  FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
 WHERE PRODUCT IN ('ECM', 'DCM')
   AND UPPER(INVESTOR_NAME) LIKE UPPER(&NAME) || '%'
 GROUP BY INVESTOR_NAME, GPNUM
 FETCH FIRST 50 ROWS ONLY;

SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST +COST +BYTES'));

-- ---------------------------------------------------------------------
-- 6. WHAT A MATERIALIZED ENTITY DIMENSION WOULD COST
--    Time this. It is the FULL build of the investor dimension; if it runs
--    in seconds, an MV refreshed on a schedule makes every entity search
--    a sub-second lookup against a few-thousand-row table.
-- ---------------------------------------------------------------------
SET TIMING ON
SELECT COUNT(*) FROM (
  SELECT INVESTOR_NAME, GPNUM,
         COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT,
         MAX(PRICING_TS)         AS LAST_ACTIVE,
         MAX(INVESTOR_CATEGORY)  AS CATEGORY,
         MAX(INVESTOR_REGION)    AS REGION,
         CASE WHEN COUNT(DISTINCT PRODUCT) = 2 THEN 'ECM+DCM' ELSE MAX(PRODUCT) END AS PRODUCTS
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN ('ECM','DCM')
   GROUP BY INVESTOR_NAME, GPNUM
);
SET TIMING OFF
