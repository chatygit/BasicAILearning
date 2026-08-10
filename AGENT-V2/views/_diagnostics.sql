-- ===========================================================================
-- PRE-FIX DIAGNOSTICS for the four DGSTREAM views
--
-- Purpose: settle every open question BEFORE we edit the views, so the whole
-- fix set ships in ONE 2-4 day change cycle instead of three.
--
-- Run against Oracle (DGSTREAM) directly, not through Starburst/Trino.
-- Paste results back grouped by query id (Q1, Q2, ...). Partial is fine —
-- they are ordered so the earliest ones unblock the most.
--
-- Cost markers:  [cheap] catalog / small agg   [heavy] full scan of a fact table
--
-- SECTION 0  catalog — settles types and column existence
-- SECTION 1  DCM allocation bug (highest severity)
-- SECTION 2  grain integrity — does each view hold its declared grain
-- SECTION 3  numeric/date typing
-- SECTION 4  DCM status, confidentiality, count reconciliation
-- SECTION 5  list columns — dedupe, alignment, LISTAGG overflow
-- SECTION 6  entity view
-- SECTION 7  dead / low-value columns worth reclaiming
-- SECTION 8  decisions I need from you (no SQL)
-- ===========================================================================


-- ===========================================================================
-- SECTION 0 — CATALOG
-- ===========================================================================

-- Q1 [cheap] Deployed column types of all four views.
-- DECIDES: whether TRANCHE_SIZE / SECURITIES_MATURITY / DEAL_SIZE / PRICING_TS
-- landed as NUMBER/DATE or silently as VARCHAR2 across the UNION ALL. This one
-- query settles every typing question in SECTION 3 at once.
SELECT table_name, column_id, column_name, data_type,
       data_length, data_precision, data_scale
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM'
AND    table_name IN ('VW_DEAL_SUMMARY','VW_TRANCHE_SUMMARY',
                      'VW_ORDER_DETAIL','VW_ENTITY_SEARCH')
ORDER  BY table_name, column_id;


-- Q2 [cheap] Full column list of the DCM order-side tables.
-- DECIDES: how to fix the DCM allocation join. I need to know whether
-- OB_ORDER_MATCH_GROUP carries an ORDER_ID (or any order-level key), and
-- whether OB_ORDER has a status / ownership flag like ECM's.
SELECT table_name, column_id, column_name, data_type, data_length, nullable
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM'
AND    table_name IN ('OB_ORDER','OB_ORDER_MATCH_GROUP','OB_ORDER_SIZE')
ORDER  BY table_name, column_id;


-- Q3 [cheap] Column list of the remaining base tables.
-- DECIDES: whether DCM has a confidentiality flag, whether OB_DEAL_TRANCHE
-- has an order-count-safe key, what OB_TRANCHE.DELIVERY_TYPE really is.
SELECT table_name, column_id, column_name, data_type, data_length
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM'
AND    table_name IN ('OB_DEAL_TRANCHE','OB_DEAL_ISSUER','OB_TRANCHE',
                      'OPUS_ECM_TRANSACTION','OPUS_ECM_TRANSACTION_TRANCHE',
                      'OPUS_ECM_TRANSACTION_STATUS')
ORDER  BY table_name, column_id;


-- ===========================================================================
-- SECTION 1 — THE DCM ALLOCATION BUG  (vw_order_detail)
--
-- Today: LEFT JOIN OB_ORDER_MATCH_GROUP OMT
--          ON OMT.ROOT_ID = O.ROOT_ID AND OMT.PARENT_ID = O.PARENT_ID
-- That key is deal+tranche, never the order — so every order on a tranche
-- receives the SAME FINAL_ALLOC, and duplicates if OMT has >1 row per pair.
-- ===========================================================================

-- Q4 [cheap] Grain of OB_ORDER_MATCH_GROUP.
-- DECIDES: whether the current join fans orders out, and by how much.
SELECT SUM(rows_)                              AS total_rows,
       COUNT(*)                                AS distinct_deal_tranche,
       ROUND(SUM(rows_) / NULLIF(COUNT(*),0), 2) AS avg_rows_per_tranche,
       MAX(rows_)                              AS worst_case_fanout
FROM   (SELECT ROOT_ID, PARENT_ID, COUNT(*) AS rows_
        FROM   OB_ORDER_MATCH_GROUP
        GROUP  BY ROOT_ID, PARENT_ID);
-- If avg_rows_per_tranche > 1, every DCM order is currently duplicated.


-- Q5 [cheap] Does OB_ORDER_MATCH_GROUP reach an individual order?
-- Run ONLY the column names Q2 shows actually exist — adjust/delete as needed.
-- DECIDES: the replacement join key for ORDER_ALLOCATION.
SELECT ROOT_ID, PARENT_ID, COUNT(*) AS rows_
FROM   OB_ORDER_MATCH_GROUP
GROUP  BY ROOT_ID, PARENT_ID
HAVING COUNT(*) > 1
FETCH  FIRST 10 ROWS ONLY;


-- Q6 [cheap] Sample the table so I can see what a "match group" actually is.
-- DECIDES: whether FINAL_ALLOC is a per-order allocation or a per-tranche
-- total. If it is a per-tranche total, ORDER_ALLOCATION cannot be sourced
-- here at all and we need the real per-order allocation column.
SELECT * FROM OB_ORDER_MATCH_GROUP FETCH FIRST 20 ROWS ONLY;


-- Q7 [cheap] Sample OB_ORDER — is there an allocation column directly on it?
SELECT * FROM OB_ORDER FETCH FIRST 10 ROWS ONLY;


-- Q8 [cheap] Reconcile allocation against tranche size for one busy DCM deal.
-- DECIDES: which source gives a total that lands near the tranche size
-- (the correct one should; a per-tranche value multiplied by order count
-- will overshoot by roughly the order count).
WITH busiest AS (
  SELECT ROOT_ID, PARENT_ID, COUNT(*) AS order_cnt
  FROM   OB_ORDER
  GROUP  BY ROOT_ID, PARENT_ID
  ORDER  BY COUNT(*) DESC
  FETCH  FIRST 5 ROWS ONLY
)
SELECT b.ROOT_ID, b.PARENT_ID, b.order_cnt,
       t.TRANCHE_SIZE,
       m.match_group_rows,
       m.sum_final_alloc
FROM   busiest b
LEFT   JOIN OB_DEAL_TRANCHE t
       ON t.DEAL_ID = b.ROOT_ID AND t.TRANCHE_ID = b.PARENT_ID
LEFT   JOIN (SELECT ROOT_ID, PARENT_ID,
                    COUNT(*)         AS match_group_rows,
                    SUM(FINAL_ALLOC) AS sum_final_alloc
             FROM   OB_ORDER_MATCH_GROUP
             GROUP  BY ROOT_ID, PARENT_ID) m
       ON m.ROOT_ID = b.ROOT_ID AND m.PARENT_ID = b.PARENT_ID;


-- ===========================================================================
-- SECTION 2 — GRAIN INTEGRITY
-- Every object declares a grain. If rows_ > grain_ the split has not happened
-- and the duplicate-row bugs the four-view design was built to kill are back.
-- ===========================================================================

-- Q9 [heavy] The headline check. Run this one even if you run nothing else.
SELECT 'deal'    AS obj, COUNT(*) AS rows_,
       COUNT(DISTINCT PRODUCT||'~'||DEAL_ID) AS grain_
FROM   DGSTREAM.VW_DEAL_SUMMARY
UNION ALL
SELECT 'tranche', COUNT(*),
       COUNT(DISTINCT PRODUCT||'~'||DEAL_ID||'~'||TRANCHE_ID)
FROM   DGSTREAM.VW_TRANCHE_SUMMARY
UNION ALL
SELECT 'order',   COUNT(*),
       COUNT(DISTINCT PRODUCT||'~'||ORDER_ID)
FROM   DGSTREAM.VW_ORDER_DETAIL
UNION ALL
SELECT 'entity',  COUNT(*),
       COUNT(DISTINCT ENTITY_TYPE||'~'||PRODUCT||'~'||ENTITY_ID)
FROM   DGSTREAM.VW_ENTITY_SEARCH;
-- Also split by PRODUCT if any line fails, so we know which branch is at fault.


-- Q10 [cheap] Is a "deal" one ECM transaction, or several?
-- DECIDES: whether VW_DEAL_SUMMARY can hold PRODUCT+DEAL_ID grain at all.
-- The view keys on DEAL_TRANSACTION_ID but joins on ECM_TRANSACTION_ID —
-- if those are not 1:1 the deal object fans out.
SELECT COUNT(*)                              AS rows_,
       COUNT(DISTINCT DEAL_TRANSACTION_ID)   AS deals_,
       COUNT(DISTINCT ECM_TRANSACTION_ID)    AS txns_
FROM   OPUS_ECM_TRANSACTION;


-- Q11 [cheap] Multiple Execution_Status rows per transaction?
-- DECIDES: whether the INNER JOIN to the status table multiplies EVERY row of
-- the deal, tranche AND order views simultaneously.
SELECT COUNT(*) AS txns_with_multiple_exec_status
FROM   (SELECT ECM_TRANSACTION_ID
        FROM   OPUS_ECM_TRANSACTION_STATUS
        WHERE  STATUS_TYPE = 'Execution_Status'
        GROUP  BY ECM_TRANSACTION_ID
        HAVING COUNT(*) > 1);


-- Q12 [cheap] The remaining unguarded joins, all in one result set.
-- DECIDES: which LEFT JOINs need wrapping in a pre-aggregated subquery.
-- Note OB_DEAL_ISSUER is already guarded by GROUP BY/MAX in vw_deal_summary
-- but joined raw in vw_tranche_summary — co-issued bonds would duplicate.
SELECT 'OPUS_BASE_TRANSACTION per TRANSACTION_ID' AS check_, COUNT(*) AS offenders
FROM   (SELECT TRANSACTION_ID FROM OPUS_BASE_TRANSACTION
        GROUP BY TRANSACTION_ID HAVING COUNT(*) > 1)
UNION ALL
SELECT 'TRANCHE_PRODUCT_DETAIL per tranche', COUNT(*)
FROM   (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
        FROM   OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID HAVING COUNT(*) > 1)
UNION ALL
SELECT 'TRANCHE_DEMAND_CURRENCY per tranche+ccy', COUNT(*)
FROM   (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID
        FROM   OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID HAVING COUNT(*) > 1)
UNION ALL
SELECT 'OB_ECM_ORDER_IOI per ORDER_ID', COUNT(*)
FROM   (SELECT ORDER_ID FROM OB_ECM_ORDER_IOI
        GROUP BY ORDER_ID HAVING COUNT(*) > 1)
UNION ALL
SELECT 'OB_ECM_ORDER per ORDER_ID', COUNT(*)
FROM   (SELECT ORDER_ID FROM OB_ECM_ORDER
        GROUP BY ORDER_ID HAVING COUNT(*) > 1)
UNION ALL
SELECT 'OB_ORDER_SIZE per ORDER_ID', COUNT(*)
FROM   (SELECT ORDER_ID FROM OB_ORDER_SIZE
        GROUP BY ORDER_ID HAVING COUNT(*) > 1)
UNION ALL
SELECT 'OB_ORDER per ORDER_ID', COUNT(*)
FROM   (SELECT ORDER_ID FROM OB_ORDER
        GROUP BY ORDER_ID HAVING COUNT(*) > 1)
UNION ALL
SELECT 'OB_DEAL_ISSUER per DEAL_TRANCHE_ID', COUNT(*)
FROM   (SELECT DEAL_TRANCHE_ID FROM OB_DEAL_ISSUER
        GROUP BY DEAL_TRANCHE_ID HAVING COUNT(*) > 1)
UNION ALL
SELECT 'OB_DEAL_TRANCHE per DEAL_ID+TRANCHE_ID', COUNT(*)
FROM   (SELECT DEAL_ID, TRANCHE_ID FROM OB_DEAL_TRANCHE
        GROUP BY DEAL_ID, TRANCHE_ID HAVING COUNT(*) > 1);
-- Any non-zero row = a join that must be pre-aggregated before we ship.


-- ===========================================================================
-- SECTION 3 — TYPING
-- ===========================================================================

-- Q13 [cheap] Why was TRANCHE_OFFER_SIZE cast to VARCHAR2(120)?
-- ECM does NVL(CAST(TT.TRANCHE_OFFER_SIZE AS VARCHAR2(120)), 0); DCM does
-- NVL(ODT.TRANCHE_SIZE, 0). If the union resolved to character then
-- "top N by tranche size" sorts lexically ('900' beats '1000000').
-- DECIDES: can we TO_NUMBER both sides, or does ECM hold non-numeric text?
SELECT COUNT(*)                                                   AS total_non_null,
       COUNT(CASE WHEN NOT REGEXP_LIKE(TO_CHAR(TRANCHE_OFFER_SIZE),
                   '^\s*-?[0-9]+(\.[0-9]+)?\s*$') THEN 1 END)     AS non_numeric_vals
FROM   OPUS_ECM_TRANSACTION_TRANCHE
WHERE  TRANCHE_OFFER_SIZE IS NOT NULL;


-- Q14 [cheap] Show me the offenders if Q13 is non-zero.
-- DECIDES: whether a TO_NUMBER(... DEFAULT NULL ON CONVERSION ERROR) is safe.
SELECT DISTINCT TO_CHAR(TRANCHE_OFFER_SIZE) AS raw_value
FROM   OPUS_ECM_TRANSACTION_TRANCHE
WHERE  TRANCHE_OFFER_SIZE IS NOT NULL
AND    NOT REGEXP_LIKE(TO_CHAR(TRANCHE_OFFER_SIZE), '^\s*-?[0-9]+(\.[0-9]+)?\s*$')
FETCH  FIRST 25 ROWS ONLY;


-- Q15 [cheap] Same question for the ECM deal size.
SELECT COUNT(*)                                                   AS total_non_null,
       COUNT(CASE WHEN NOT REGEXP_LIKE(TO_CHAR(DEAL_SIZE),
                   '^\s*-?[0-9]+(\.[0-9]+)?\s*$') THEN 1 END)     AS non_numeric_vals
FROM   OPUS_ECM_TRANSACTION
WHERE  DEAL_SIZE IS NOT NULL;


-- Q16 [cheap] SECURITIES_MATURITY: ECM is CAST(NULL AS VARCHAR2(4000)),
-- DCM is ODT.MATURITY_DATE. If Q1 shows the view column as VARCHAR2 then
-- maturity is an NLS-formatted string — unsortable, unfilterable as a date.
-- DECIDES: change the ECM placeholder to CAST(NULL AS DATE).
SELECT COUNT(*) AS rows_, COUNT(MATURITY_DATE) AS non_null_maturity,
       MIN(MATURITY_DATE) AS earliest, MAX(MATURITY_DATE) AS latest
FROM   OB_DEAL_TRANCHE;


-- ===========================================================================
-- SECTION 4 — DCM STATUS, CONFIDENTIALITY, COUNT RECONCILIATION
-- ===========================================================================

-- Q17 [cheap] Every ECM branch excludes Confidential/Withdrawn/Terminated.
-- No DCM branch in any view excludes anything.
-- DECIDES: whether confidential DCM deals are reaching users right now.
-- THIS IS THE ONE TO CHECK FIRST if you only check one thing in this section.
SELECT STATUS, COUNT(*) AS rows_, COUNT(DISTINCT DEAL_ID) AS deals_
FROM   OB_DEAL_TRANCHE
GROUP  BY STATUS
ORDER  BY rows_ DESC;


-- Q18 [cheap] Do DCM deals have tranches in mixed statuses?
-- DECIDES: whether vw_deal_summary's MAX(ODT.STATUS) can disagree with
-- vw_tranche_summary's per-tranche ODT.STATUS for the same deal — today the
-- same deal can report two different statuses depending on which object you ask.
SELECT COUNT(*) AS deals_with_mixed_tranche_status
FROM   (SELECT DEAL_ID FROM OB_DEAL_TRANCHE
        GROUP BY DEAL_ID HAVING COUNT(DISTINCT STATUS) > 1);


-- Q19 [cheap] Does OB_ORDER need the equivalent of ECM's order filters?
-- ECM drops CANCELLED/DELETED/PASS and unowned/non-dominant orders. DCM drops
-- nothing anywhere. Replace <STATUS_COL> with whatever Q2 reveals; if OB_ORDER
-- has no status column at all, just say so and skip.
-- SELECT <STATUS_COL>, COUNT(*) FROM OB_ORDER GROUP BY <STATUS_COL> ORDER BY 2 DESC;


-- Q20 [heavy] Size the DCM order-count divergence.
-- vw_deal_summary counts OB_ORDER grouped by ROOT_ID with NO filter;
-- vw_order_detail INNER JOINs OB_DEAL_TRANCHE on (deal, tranche), dropping
-- orders with no matching tranche. A deal card saying "120 orders" then pages
-- to fewer rows — that breaks the count-honesty contract.
-- DECIDES: whether the deal-view subquery must adopt the order-view predicates.
SELECT COUNT(*)                                             AS orders_total,
       COUNT(CASE WHEN t.DEAL_ID IS NULL THEN 1 END)        AS orders_without_tranche,
       COUNT(DISTINCT o.ROOT_ID)                            AS deals_total,
       COUNT(DISTINCT CASE WHEN t.DEAL_ID IS NULL
                           THEN o.ROOT_ID END)              AS deals_affected
FROM   OB_ORDER o
LEFT   JOIN OB_DEAL_TRANCHE t
       ON t.DEAL_ID = o.ROOT_ID AND t.TRANCHE_ID = o.PARENT_ID;


-- ===========================================================================
-- SECTION 5 — LIST COLUMNS
-- ===========================================================================

-- Q21 [cheap] DCM CURRENCIES is not deduped.
-- ECM hoists a SELECT DISTINCT into the TC subquery; DCM LISTAGGs raw, so a
-- 3-tranche USD deal renders 'USD | USD | USD' where the same ECM deal
-- renders 'USD'. DECIDES: how much output is already wrong.
SELECT COUNT(*) AS dcm_deals_with_repeated_currency
FROM   (SELECT DEAL_ID FROM OB_DEAL_TRANCHE
        GROUP BY DEAL_ID HAVING COUNT(CURRENCY) > COUNT(DISTINCT CURRENCY));


-- Q22 [cheap] LISTAGG returns VARCHAR2(4000). Overflow raises ORA-01489 and
-- kills the whole query — it would surface as a random failure on big deals.
-- DECIDES: whether we need ON OVERFLOW TRUNCATE (Oracle 12.2+) before shipping.
SELECT 'ecm syndicate member names' AS list_, MAX(len) AS max_chars FROM (
  SELECT SUM(NVL(LENGTH(SYNDICATE_MEMBER_NAME),0) + 3) len
  FROM OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
  GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID)
UNION ALL
SELECT 'ecm syndicate roles', MAX(len) FROM (
  SELECT SUM(NVL(LENGTH(SYNDICATE_ROLE),0) + 3) len
  FROM OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
  GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID)
UNION ALL
SELECT 'ecm identifier values', MAX(len) FROM (
  SELECT SUM(NVL(LENGTH(IDENTIFIER_VALUE),0) + 3) len
  FROM OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL_IDENTIFIER
  GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID)
UNION ALL
SELECT 'dcm identifier values', MAX(len) FROM (
  SELECT SUM(NVL(LENGTH(VALUE),0) + 3) len
  FROM OB_TRANCHE GROUP BY DEAL_TRANCHE_ID)
UNION ALL
SELECT 'dcm issuer ratings', MAX(len) FROM (
  SELECT SUM(NVL(LENGTH(AGENCY||' - '||VALUE||'('||OUTLOOK||')'),0) + 2) len
  FROM OB_TRANCHE_RATING GROUP BY DEAL_TRANCHE_ID)
UNION ALL
SELECT 'ecm deal currencies', MAX(len) FROM (
  SELECT SUM(NVL(LENGTH(TRANCHE_CURRENCY_ID),0) + 3) len
  FROM (SELECT DISTINCT ECM_TRANSACTION_ID, TRANCHE_CURRENCY_ID
        FROM OPUS_ECM_TRANSACTION_TRANCHE)
  GROUP BY ECM_TRANSACTION_ID);
-- Anything approaching 4000 is a live production failure waiting on one deal.


-- Q23 [cheap] Pipe lists must align BY POSITION (spec 3.1).
-- The DCM identifier subquery orders TYPE and VALUE by T.TYPE but orders
-- DELIVERY_TYPE by T.DELIVERY_TYPE — a different sort, so position N of
-- delivery does not correspond to position N of type/value.
-- DECIDES: whether DELIVERY_TYPE is per-identifier (must re-sort by TYPE)
-- or per-tranche (should be deduped to a single value instead of a list).
SELECT COUNT(*)                                                        AS tranches,
       SUM(CASE WHEN d_distinct = 1 THEN 1 ELSE 0 END)                 AS single_delivery_type,
       SUM(CASE WHEN d_distinct > 1 THEN 1 ELSE 0 END)                 AS multi_delivery_type,
       MAX(rows_)                                                      AS max_identifiers_per_tranche
FROM   (SELECT DEAL_TRANCHE_ID, COUNT(*) rows_,
               COUNT(DISTINCT DELIVERY_TYPE) d_distinct
        FROM   OB_TRANCHE GROUP BY DEAL_TRANCHE_ID);


-- Q24 [cheap] LISTAGG ties are non-deterministic.
-- ECM identifiers sort by IDENTIFIER_TYPE only, so a tranche with two
-- identifiers of the SAME type can zip type-to-value in the wrong order.
-- DECIDES: whether we add IDENTIFIER_VALUE as a tiebreaker.
SELECT COUNT(*) AS tranches_with_duplicate_identifier_type
FROM   (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, IDENTIFIER_TYPE
        FROM   OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL_IDENTIFIER
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, IDENTIFIER_TYPE
        HAVING COUNT(*) > 1);


-- Q25 [cheap] BND_BANK uses MAX(CASE WHEN BND_BROKER='true' ...) so it returns
-- ONE bank. Joint B&D roles would silently lose all but the last alphabetically.
-- DECIDES: whether BND_BANK should be a pipe list rather than a scalar.
SELECT COUNT(*) AS tranches_with_multiple_bnd_true
FROM   (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
        FROM   OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
        WHERE  BND_BROKER = 'true'
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
        HAVING COUNT(*) > 1);


-- Q26 [cheap] TENORS is ODT.TENOR_VALUE || '-' || ODT.TENOR_PERIOD.
-- Oracle treats NULL as empty in concatenation, so a half-populated row
-- renders '5-' or '-Y' instead of NULL.
-- DECIDES: whether the expression needs a CASE guard.
SELECT COUNT(*) AS rows_,
       COUNT(CASE WHEN TENOR_VALUE IS NULL AND TENOR_PERIOD IS NULL
                  THEN 1 END) AS both_null,
       COUNT(CASE WHEN TENOR_VALUE IS NULL AND TENOR_PERIOD IS NOT NULL
                  THEN 1 END) AS value_null_only,
       COUNT(CASE WHEN TENOR_VALUE IS NOT NULL AND TENOR_PERIOD IS NULL
                  THEN 1 END) AS period_null_only
FROM   OB_DEAL_TRANCHE;
-- value_null_only + period_null_only = rows rendering as '-Y' or '5-'.


-- Q27 [cheap] ISSUER_RATINGS builds AGENCY || ' - ' || VALUE || '(' || OUTLOOK || ')'.
-- A null OUTLOOK renders "Moody's - Aa2()".
SELECT COUNT(*) AS rows_, COUNT(OUTLOOK) AS non_null_outlook
FROM   OB_TRANCHE_RATING;


-- ===========================================================================
-- SECTION 6 — ENTITY VIEW
-- ===========================================================================

-- Q28 [heavy] How big is the entity set, and how slow is a resolution?
-- The proposal called for a MATERIALIZED view + index on UPPER(ENTITY_NAME);
-- what shipped is a plain view over VW_ORDER_DETAIL and VW_DEAL_SUMMARY, so
-- every name lookup re-executes both. Time this one.
SELECT ENTITY_TYPE, PRODUCT, COUNT(*) AS rows_,
       COUNT(DISTINCT ENTITY_ID) AS distinct_ids,
       COUNT(CASE WHEN ENTITY_NAME IS NULL THEN 1 END) AS null_names
FROM   DGSTREAM.VW_ENTITY_SEARCH
GROUP  BY ENTITY_TYPE, PRODUCT
ORDER  BY 1,2;
-- rows_ > distinct_ids confirms the declared grain [entity_type, product,
-- entity_id] is wrong (every branch also groups by NAME, so name variants
-- under one id produce several rows).
-- null_names on the DEAL branch = the missing IS NOT NULL guard.


-- Q29 [heavy] Wall-clock for a realistic resolution. Please report the timing.
SELECT ENTITY_ID, ENTITY_NAME, ENTITY_ACTIVITY_COUNT, LAST_ACTIVE
FROM   DGSTREAM.VW_ENTITY_SEARCH
WHERE  ENTITY_TYPE = 'INVESTOR'
AND    UPPER(ENTITY_NAME) LIKE '%BLACKROCK%'
ORDER  BY ENTITY_ACTIVITY_COUNT DESC, LAST_ACTIVE DESC, ENTITY_ID
FETCH  FIRST 10 ROWS ONLY;


-- ===========================================================================
-- SECTION 7 — RECLAIMING DEAD COLUMNS
-- ===========================================================================

-- Q30 [cheap] EXECUTION_STATUS is S.STATUS_TYPE, but the join already pins
-- STATUS_TYPE = 'Execution_Status'. So the column is the literal string on
-- every ECM row and NULL on every DCM row — a dead column the ontology models
-- and the agent can filter on.
-- DECIDES: whether another STATUS_TYPE holds something worth exposing instead,
-- which would turn a dead column into a real one at zero extra join cost.
SELECT STATUS_TYPE, COUNT(*) AS rows_,
       COUNT(DISTINCT STATUS_VALUE) AS distinct_values
FROM   OPUS_ECM_TRANSACTION_STATUS
GROUP  BY STATUS_TYPE
ORDER  BY rows_ DESC;


-- Q31 [cheap] If Q30 shows other status types, show their values.
SELECT STATUS_TYPE, STATUS_VALUE, COUNT(*) AS rows_
FROM   OPUS_ECM_TRANSACTION_STATUS
GROUP  BY STATUS_TYPE, STATUS_VALUE
ORDER  BY STATUS_TYPE, rows_ DESC;


-- Q32 [cheap] SETTLEMENT_TS is on VW_DEAL_SUMMARY but unmodeled in the
-- ontology, while the agent's refusal text promises "pricing and settlement
-- dates". DECIDES: is it populated enough to be worth exposing?
SELECT COUNT(*) AS ecm_deals, COUNT(SETTLEMENT_TS) AS with_settlement_ts
FROM   DGSTREAM.VW_DEAL_SUMMARY WHERE PRODUCT = 'ECM';


-- Q33 [cheap] DEAL_REGION is NULL on DCM by construction in vw_deal_summary
-- (CAST(NULL AS VARCHAR2(400))) but vw_tranche_summary sources ODT.REGION for
-- DCM. So DCM region exists on the tranche object and not the deal object.
-- DECIDES: can vw_deal_summary carry MAX(ODT.REGION) and stop the asymmetry?
SELECT COUNT(*) AS rows_, COUNT(REGION) AS non_null_region,
       COUNT(DISTINCT REGION) AS distinct_regions
FROM   OB_DEAL_TRANCHE;


-- ===========================================================================
-- SECTION 8 — DECISIONS I NEED FROM YOU (no SQL)
-- ===========================================================================
--
-- D1. MATERIALIZED VIEW for entity search — is that on the table in this
--     change cycle, or is DBA/refresh-schedule approval a separate track?
--     It is the single biggest latency win available, but it is infra, not DDL.
--     If it is out of scope, say so and I will optimise the plain view instead
--     and stop recommending it.
--
-- D2. Can we ADD columns to the views, or is this cycle fixes-only?
--     Adding is additive and non-breaking, and three cheap ones pay for
--     themselves:
--       - MATCH_RANK on VW_ENTITY_SEARCH (0 exact / 1 prefix / 2 contains) —
--         restores single-query tiered resolution, removes a whole hop class.
--       - DEAL_REGION on the DCM deal branch (see Q33).
--       - a real EXECUTION_STATUS if Q30/Q31 show one exists.
--
-- D3. Is DGSTREAM Oracle 12.2+? LISTAGG ... ON OVERFLOW TRUNCATE needs 12.2,
--     and it is the clean fix for Q22 if any list is near 4000 chars.
--
-- D4. Who owns the DCM confidentiality question (Q17)? If confidential DCM
--     deals are currently visible that is a disclosure issue, not a data-
--     quality one, and it should not wait on the rest of this batch.
--
-- D5. Ontology coupling — when the views change I will update in the same PR:
--       ecm_dcm_deal.yaml      + settlement_ts, deal_region (DCM)
--       ecm_dcm_tranche.yaml   + deal_region, deal_status, execution_status,
--                                settlement_currency, use_of_proceeds
--                                (all already ON the view, just unmodeled —
--                                 this deletes a class of two-object questions)
--       ecm_dcm_entity.yaml    grain fix, + match_rank if D2 allows
--       SKILL.md               retire the B&D pipe-index arithmetic (the
--                                resolved BND_BANK column made it obsolete)
--     Confirm that is the right blast radius, or tell me what else is coupled.
--
-- ===========================================================================
