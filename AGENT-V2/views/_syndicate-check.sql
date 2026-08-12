-- ===========================================================================
-- SYNDICATE CHECK — why did "deals with 5+ syndicates in 2026" return zero?
-- 2026-08-12. The engine's SQL was reproduced locally and is CORRECT
-- (CARDINALITY(SPLIT(syndicate_member_name, ' | ')) >= 5 at tranche grain,
-- HAVING on MAX per deal/tranche group). So the zero came from the DATA WINDOW
-- or from a laundered error — these queries tell you which.
--
-- ECM only throughout: DCM exposes just the B&D bank, so it can never reach 5.
-- Counts are pipe tokens on the tranche's list (not deduped across the deal);
-- a LISTAGG-truncated list undercounts but is already far past 5.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- Q1 (THE DECIDER) — where do the 5+ syndicate deals fall in time?
-- Starburst/Trino.
--   * rows only in other years, none in 2026 -> the agent was right for its
--     window; check whether "2026" came from the user or the agent invented it
--   * big NULL priced_year bucket -> syndicate-rich deals with no pricing
--     date; they can never appear in ANY dated ask (skill disclosure gap)
--   * rows IN 2026 -> the agent's first query failed and was laundered into
--     empty rows; pull that run_bqs_query's generated_sql from the MCP log
-- ---------------------------------------------------------------------------
SELECT EXTRACT(YEAR FROM pricing_ts) AS priced_year,
       COUNT(DISTINCT deal_id) AS deals_5plus
FROM   bds_dg_oraas.dgstream.vw_tranche_summary
WHERE  product = 'ECM'
AND    CARDINALITY(SPLIT(syndicate_member_name, ' | ')) >= 5
GROUP  BY EXTRACT(YEAR FROM pricing_ts)
ORDER  BY 1 NULLS FIRST;

-- ---------------------------------------------------------------------------
-- Q1b — same decider, Oracle (SQL Developer). NULL year sorts first.
-- ---------------------------------------------------------------------------
SELECT EXTRACT(YEAR FROM PRICING_TS) AS PRICED_YEAR,
       COUNT(DISTINCT DEAL_ID) AS DEALS_5PLUS
FROM   DGSTREAM.VW_TRANCHE_SUMMARY
WHERE  PRODUCT = 'ECM'
AND    REGEXP_COUNT(SYNDICATE_MEMBER_NAME, '\|') + 1 >= 5
GROUP  BY EXTRACT(YEAR FROM PRICING_TS)
ORDER  BY 1 NULLS FIRST;

-- ---------------------------------------------------------------------------
-- Q2 — the deals themselves (no date filter), Oracle. Largest syndicate on
-- any tranche of the deal; 5+ means "5+ member slots on at least one tranche".
-- ---------------------------------------------------------------------------
SELECT PRODUCT, DEAL_ID, MAX(DEAL_NAME) AS DEAL_NAME,
       MAX(REGEXP_COUNT(SYNDICATE_MEMBER_NAME, '\|') + 1) AS SYNDICATE_MEMBERS
FROM   DGSTREAM.VW_TRANCHE_SUMMARY
WHERE  PRODUCT = 'ECM'
AND    SYNDICATE_MEMBER_NAME IS NOT NULL
GROUP  BY PRODUCT, DEAL_ID
HAVING MAX(REGEXP_COUNT(SYNDICATE_MEMBER_NAME, '\|') + 1) >= 5
ORDER  BY SYNDICATE_MEMBERS DESC;

-- ---------------------------------------------------------------------------
-- Q2b — same, through Starburst on the new catalog.
-- ---------------------------------------------------------------------------
SELECT product, deal_id, MAX(deal_name) AS deal_name,
       MAX(CARDINALITY(SPLIT(syndicate_member_name, ' | '))) AS syndicate_members
FROM   bds_dg_oraas.dgstream.vw_tranche_summary
WHERE  product = 'ECM' AND syndicate_member_name IS NOT NULL
GROUP  BY product, deal_id
HAVING MAX(CARDINALITY(SPLIT(syndicate_member_name, ' | '))) >= 5
ORDER  BY 4 DESC;

-- ---------------------------------------------------------------------------
-- Q3 — the engine's own SQL for the 2026 ask, verbatim (params inlined), for
-- a direct A/B against whatever the MCP log shows the agent actually ran.
-- ---------------------------------------------------------------------------
SELECT "deal_name" AS "deal_name", "deal_id" AS "deal_id",
       "tranche_name" AS "tranche_name", "tranche_id" AS "tranche_id",
       MAX((CASE WHEN "syndicate_member_name" IS NULL OR "syndicate_member_name" = ''
                 THEN 0
                 ELSE CARDINALITY(SPLIT("syndicate_member_name", ' | ')) END)) AS "syndicate_member_count"
FROM   "bds_dg_oraas"."dgstream"."vw_tranche_summary"
WHERE  "product" = 'ECM'
AND    "pricing_ts" >= DATE '2026-01-01'
AND    "pricing_ts" <  DATE '2027-01-01'
GROUP  BY "deal_name", "deal_id", "tranche_name", "tranche_id"
HAVING MAX((CASE WHEN "syndicate_member_name" IS NULL OR "syndicate_member_name" = ''
                 THEN 0
                 ELSE CARDINALITY(SPLIT("syndicate_member_name", ' | ')) END)) >= 5
ORDER  BY "syndicate_member_count" DESC, "tranche_id" ASC
LIMIT  50;
