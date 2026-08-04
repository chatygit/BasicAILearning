-- =====================================================================
-- ENTITY-SEARCH TUNING  v3 — everything here runs against THE VIEW ONLY.
--
-- Our job is to query VW_DEAL_ORDER_SUMMARY well. We do not own the view,
-- so this script does not touch its base tables; it measures the levers we
-- actually control in domain.yaml:
--     1. dropping SOUNDEX out of the main pass
--     2. scoping PRODUCT to the user's entitlement (prunes a UNION ALL branch)
--     3. how wide the SELECT list is
--     4. exact / prefix / substring matching
--     5. splitting "find names" from "count their deals"
--
-- HOW TO RUN
--   • find/replace  BLACKROCK  with a real, reasonably common investor name
--   • run ONE block at a time with F5 (Run Script) — Ctrl+Enter fetches only
--     50 rows and under-reports cost
--   • send the Elapsed line under each block; the row counts matter less
--   • run V0 twice and use the SECOND timing as your baseline (the first
--     pass warms the buffer cache and would flatter everything after it)
-- =====================================================================
SET DEFINE OFF
SET PAGESIZE 200
SET LINESIZE 300
SET TIMING ON

-- =====================================================================
-- PART 1 — WHICH TEMPLATE SHAPE SHOULD WE SHIP?  (our job)
-- Each block returns the same kind of answer; only the shape differs.
-- =====================================================================

-- V0. BASELINE — exactly what we ship today: LIKE **OR SOUNDEX**, both products.
SELECT COUNT(*) AS v0_today FROM (
  SELECT INVESTOR_NAME, GPNUM,
         COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT,
         MAX(PRICING_TS)         AS LAST_ACTIVE,
         MAX(INVESTOR_CATEGORY)  AS CATEGORY,
         MAX(INVESTOR_REGION)    AS REGION
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN ('ECM','DCM')
     AND ( UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
        OR SOUNDEX(UPPER(INVESTOR_NAME)) = SOUNDEX('BLACKROCK') )
   GROUP BY INVESTOR_NAME, GPNUM
);

-- V1. SAME, minus SOUNDEX  →  how much does SOUNDEX cost us on every search?
SELECT COUNT(*) AS v1_no_soundex FROM (
  SELECT INVESTOR_NAME, GPNUM,
         COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT,
         MAX(PRICING_TS)         AS LAST_ACTIVE,
         MAX(INVESTOR_CATEGORY)  AS CATEGORY,
         MAX(INVESTOR_REGION)    AS REGION
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT IN ('ECM','DCM')
     AND UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
   GROUP BY INVESTOR_NAME, GPNUM
);

-- V2. SINGLE PRODUCT  →  what CHANGE L buys an ECM-only user.
--     The view is a UNION ALL of an ECM branch and a DCM branch, each with a
--     literal PRODUCT, so this should let Oracle skip one branch entirely.
SELECT COUNT(*) AS v2_ecm_only FROM (
  SELECT INVESTOR_NAME, GPNUM,
         COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT,
         MAX(PRICING_TS)         AS LAST_ACTIVE,
         MAX(INVESTOR_CATEGORY)  AS CATEGORY,
         MAX(INVESTOR_REGION)    AS REGION
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT = 'ECM'
     AND UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
   GROUP BY INVESTOR_NAME, GPNUM
);

-- V3. NARROW SELECT — name + id only, no enrichment columns, no aggregates.
--     Tests whether asking for less lets the optimizer do less.
SELECT COUNT(*) AS v3_names_only FROM (
  SELECT DISTINCT INVESTOR_NAME, GPNUM
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT = 'ECM'
     AND UPPER(INVESTOR_NAME) LIKE '%BLACKROCK%'
);

-- V4. EXACT match (the first tier of our gated template)
SELECT COUNT(*) AS v4_exact FROM (
  SELECT DISTINCT INVESTOR_NAME, GPNUM
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT = 'ECM'
     AND UPPER(INVESTOR_NAME) = 'BLACKROCK'
);

-- V5. PREFIX match (cheapest possible name predicate)
SELECT COUNT(*) AS v5_prefix FROM (
  SELECT DISTINCT INVESTOR_NAME, GPNUM
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT = 'ECM'
     AND UPPER(INVESTOR_NAME) LIKE 'BLACKROCK%'
);

-- V6. TWO-STEP shape: step 1 finds the names (V3 above); step 2 enriches ONLY
--     the shortlist. Time this as "step 2" and compare V3 + V6 against V2.
--     Replace the IN-list with a few real names from V3's output.
SELECT COUNT(*) AS v6_enrich_shortlist FROM (
  SELECT INVESTOR_NAME, GPNUM,
         COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT,
         MAX(PRICING_TS)         AS LAST_ACTIVE,
         MAX(INVESTOR_CATEGORY)  AS CATEGORY,
         MAX(INVESTOR_REGION)    AS REGION
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT = 'ECM'
     AND UPPER(INVESTOR_NAME) IN ('BLACKROCK','BLACKROCK INC')   -- <- from V3
   GROUP BY INVESTOR_NAME, GPNUM
);

-- V7. Is the cost the NAME PREDICATE or just the view? A trivially-filtered
--     query with the same shape. If V7 ≈ V2, the view dominates and no
--     predicate tuning of ours will matter much.
SELECT COUNT(*) AS v7_floor FROM (
  SELECT DISTINCT INVESTOR_NAME, GPNUM
    FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY
   WHERE PRODUCT = 'ECM'
     AND GPNUM = '00000000'
);

-- =====================================================================
-- HOW I WILL READ PART 1
--   V0 - V1  = the price of SOUNDEX on every search    → if large, gate it
--   V1 - V2  = the price of not scoping the product    → CHANGE L's value
--   V2 vs V3 = does a narrower SELECT help             → shrink the template
--   V4 / V5  = value of tiering exact/prefix first     → tier as separate queries
--   V3 + V6 vs V2 = is two-step cheaper than one-shot  → split the template
--   V7       ≈ V2 means the VIEW is the floor          → tuning ours is capped,
--                                                        and Part 2 is the story
-- =====================================================================


-- =====================================================================
-- PART 2 — FINDINGS FOR QA TO PASS TO THE DATA TEAM (not our fix)
-- =====================================================================

-- P1. The ECM DEAL_SHARING_TYPE = 'SOLO' definition flags any Citi LEAD ROLE
--     without checking syndicate size (DCM correctly requires one dealer).
--     This quantifies it: how many "SOLO" ECM tranches have several banks?
SELECT COUNT(*)                                            AS citi_led_tranches,
       SUM(CASE WHEN member_count = 1 THEN 1 ELSE 0 END)   AS truly_sole_managed,
       SUM(CASE WHEN member_count > 1 THEN 1 ELSE 0 END)   AS mislabelled_solo,
       ROUND(100 * SUM(CASE WHEN member_count > 1 THEN 1 ELSE 0 END)
             / NULLIF(COUNT(*),0), 1)                      AS pct_wrong
  FROM (
    SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID,
           COUNT(DISTINCT SYNDICATE_MEMBER_NAME) AS member_count,
           MAX(CASE WHEN SYNDICATE_ROLE IN ('Sole Bookrunner','Lead Manager/Bookrunner',
                                            'Global Coordinator and Bookrunner','Global Coordinator')
                     AND SYNDICATE_MEMBER_NAME LIKE '%Citigroup Global%'
                    THEN 1 ELSE 0 END) AS citi_led
      FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
     GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
  )
 WHERE citi_led = 1;

-- P2. Snapshot for the performance conversation: are stats fresh, and does any
--     index exist on the name columns? (Stale stats alone cause bad plans.)
SELECT table_name, num_rows, last_analyzed
  FROM all_tables
 WHERE owner = 'DGSTREAM'
 ORDER BY num_rows DESC NULLS LAST
 FETCH FIRST 20 ROWS ONLY;

SELECT table_name, index_name, column_expression
  FROM all_ind_expressions WHERE index_owner = 'DGSTREAM';

SET TIMING OFF
