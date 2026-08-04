-- =====================================================================
-- ENTITY-SEARCH PERFORMANCE DIAGNOSTICS  (SQL Developer)
--
-- HOW TO RUN
--   1. Find/replace  BLACKROCK  with a real, reasonably common investor name
--      (keep the quotes and the % signs as they are).
--   2. Run STEP BY STEP, not all at once: select a step's statements and
--      press F5 (Run Script) so timings and full fetches are captured.
--      Ctrl+Enter (Run Statement) fetches only the first 50 rows and will
--      UNDER-report the real cost.
--   3. Copy the Script Output pane after each step and send it over.
--
-- Steps 1 and 6 read the whole view — if the view is large they may take
-- minutes. Run them when the box is quiet, and don't cancel step 6: its
-- runtime IS the answer to "is a materialized dimension viable?".
-- =====================================================================

-- ---------------------------------------------------------------------
-- STEP 0 — session setup + privilege check (fast). Run this first.
-- ---------------------------------------------------------------------
SET DEFINE OFF
SET LONG 200000
SET LONGCHUNKSIZE 200000
SET PAGESIZE 200
SET LINESIZE 300
SET TIMING ON
SET SERVEROUTPUT ON

-- Can we read real execution stats? 1 = yes (use STEP 5), 0 = no (skip it,
-- STEP 4's EXPLAIN PLAN still works for everyone).
SELECT COUNT(*) AS can_use_display_cursor
  FROM all_tab_privs
 WHERE table_name IN ('V_$SQL','V_$SQL_PLAN','V_$SESSION')
   AND grantee IN (USER, 'PUBLIC');

-- ---------------------------------------------------------------------
-- STEP 1 — cardinality profile.  The rows : distinct-names ratio IS the
-- amplification we pay on every entity search.
-- Run 1a first (fast); if 1b is slow, that slowness is itself a finding.
-- ---------------------------------------------------------------------
-- 1a
SELECT COUNT(*) AS view_rows FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY;

-- 1b
SELECT COUNT(DISTINCT DEAL_ID)       AS deals,
       COUNT(DISTINCT TRANCHE_ID)    AS tranches,
       COUNT(DISTINCT ORDER_ID)      AS orders,
       COUNT(DISTINCT INVESTOR_NAME) AS investor_names,
       COUNT(DISTINCT GPNUM)         AS investor_ids,
       COUNT(DISTINCT ISSUER_NAME)   AS issuer_names,
       COUNT(DISTINCT DEAL_NAME)     AS deal_names
  FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY;

-- ---------------------------------------------------------------------
-- STEP 2 — what IS the view? A plain view re-joins its base tables on
-- every search; a materialized view does not.
-- ---------------------------------------------------------------------
SELECT object_type, status, last_ddl_time
  FROM all_objects
 WHERE owner = 'DGSTREAM' AND object_name = 'VW_DEAL_ORDER_SUMMARY';

-- the join underneath (needs the SET LONG above, else it truncates)
SELECT text FROM all_views
 WHERE owner = 'DGSTREAM' AND view_name = 'VW_DEAL_ORDER_SUMMARY';

-- ---------------------------------------------------------------------
-- STEP 3 — index inventory on the base tables, incl. function-based.
-- Tells us whether UPPER(name) can ever be seeked instead of scanned.
-- ---------------------------------------------------------------------
SELECT i.table_name, i.index_name, i.index_type, i.uniqueness,
       LISTAGG(c.column_name, ', ') WITHIN GROUP (ORDER BY c.column_position) AS cols
  FROM all_indexes i
  JOIN all_ind_columns c
    ON c.index_owner = i.owner AND c.index_name = i.index_name
 WHERE i.table_owner = 'DGSTREAM'
 GROUP BY i.table_name, i.index_name, i.index_type, i.uniqueness
 ORDER BY i.table_name, i.index_name;

SELECT table_name, index_name, column_expression
  FROM all_ind_expressions
 WHERE index_owner = 'DGSTREAM';

-- ---------------------------------------------------------------------
-- STEP 4 — TIMINGS + PLAN SHAPES.
-- Each query is wrapped in COUNT(*) so it FULLY executes (no partial
-- fetch) and "Elapsed" in the Script Output is the true cost.
-- EXPLAIN PLAN needs no special privileges.
-- ---------------------------------------------------------------------

-- 4A. the TYPED template we ship (investor_name) -----------------------
SELECT COUNT(*) AS typed_template_rows FROM (
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
             MAX(CASE WHEN UPPER(INVESTOR_NAME) = 'BLACKROCK' THEN 1 ELSE 0 END) AS is_exact,
             MAX(CASE WHEN UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%' THEN 1 ELSE 0 END) AS is_sub
        FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
       WHERE PRODUCT IN ('ECM', 'DCM')
         AND ( UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
            OR SOUNDEX(UPPER(INVESTOR_NAME)) = SOUNDEX('BLACKROCK') )
       GROUP BY INVESTOR_NAME, GPNUM
    )
);

EXPLAIN PLAN SET STATEMENT_ID = 'TYPED' FOR
  SELECT INVESTOR_NAME, GPNUM, COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT, MAX(PRICING_TS) AS LAST_ACTIVE
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN ('ECM', 'DCM')
     AND ( UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
        OR SOUNDEX(UPPER(INVESTOR_NAME)) = SOUNDEX('BLACKROCK') )
   GROUP BY INVESTOR_NAME, GPNUM;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY(NULL, 'TYPED', 'ALL'));

-- 4B. the (now REMOVED) untyped default template — run it anyway: it is the
--     baseline that shows what deleting it saved us.
SELECT COUNT(*) AS default_template_rows FROM (
  SELECT DISTINCT DEAL_ID, DEAL_NAME, INVESTOR_NAME, GPNUM, ISSUER_NAME, GFCID
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN ('ECM', 'DCM')
     AND ( UPPER(DEAL_NAME)     LIKE '%BLACKROCK%'
        OR UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
        OR UPPER(ISSUER_NAME)   LIKE '%BLACKROCK%'
        OR SOUNDEX(UPPER(DEAL_NAME))     = SOUNDEX('BLACKROCK')
        OR SOUNDEX(UPPER(INVESTOR_NAME)) = SOUNDEX('BLACKROCK')
        OR SOUNDEX(UPPER(ISSUER_NAME))   = SOUNDEX('BLACKROCK') )
);

-- 4C. LIKE only — how much of the cost is SOUNDEX?
SELECT COUNT(*) AS like_only_rows FROM (
  SELECT INVESTOR_NAME, GPNUM, COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN ('ECM', 'DCM')
     AND UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
   GROUP BY INVESTOR_NAME, GPNUM
);

-- 4D. EXACT probe — the cheap first tier (config-only fix)
SELECT COUNT(*) AS exact_rows FROM (
  SELECT INVESTOR_NAME, GPNUM, COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN ('ECM', 'DCM')
     AND UPPER(INVESTOR_NAME) = 'BLACKROCK'
   GROUP BY INVESTOR_NAME, GPNUM
);

-- 4E. PREFIX probe — the only name predicate an index can seek
SELECT COUNT(*) AS prefix_rows FROM (
  SELECT INVESTOR_NAME, GPNUM, COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN ('ECM', 'DCM')
     AND UPPER(INVESTOR_NAME) LIKE 'BLACKROCK%'
   GROUP BY INVESTOR_NAME, GPNUM
);

-- 4F. single-product scope (what CHANGE L buys a single-product user)
SELECT COUNT(*) AS ecm_only_rows FROM (
  SELECT INVESTOR_NAME, GPNUM, COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT = 'ECM'
     AND UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
   GROUP BY INVESTOR_NAME, GPNUM
);

-- ---------------------------------------------------------------------
-- STEP 5 — REAL execution stats (only if STEP 0 returned 1).
-- Run this IMMEDIATELY after 4A in the same session.
-- A-Rows vs E-Rows shows where the optimizer guesses wrong;
-- A-Time per step shows whether the cost is scan, SOUNDEX, or aggregation.
-- ---------------------------------------------------------------------
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY_CURSOR(NULL, NULL, 'ALLSTATS LAST +COST +BYTES'));

-- ---------------------------------------------------------------------
-- STEP 6 — would a MATERIALIZED ENTITY DIMENSION work?
-- This builds the ENTIRE investor dimension. Its runtime is the answer:
-- if it completes in seconds-to-a-minute, an MV refreshed on a schedule
-- makes every entity search a sub-second lookup on a few thousand rows.
-- ---------------------------------------------------------------------
SELECT COUNT(*) AS investor_dimension_rows FROM (
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
