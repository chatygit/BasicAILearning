-- ===========================================================================
-- PRE-FIX DIAGNOSTICS — TRIMMED SET
--
-- 21 queries. Everything answerable from the repo has been removed; what
-- remains needs the actual data. Original Q numbers are kept so results map
-- to _diagnostics-results.md.
--
-- ALREADY ANSWERED, DO NOT RE-RUN:
--   Q1  view columns          -> _reference/view-columns.md
--   Q2  base-table columns    -> _reference/base-table-columns.md
--   Q3  remaining base tables -> WITHDRAWN. Covered by V1/reference/columns.txt
--       (old single view) + the join-key table in
--       V1/docs/QA-FINDINGS-FOR-DATA-TEAM.md + the deployed DDL in this folder.
--   Q4,Q5,Q7  match-group structure -> answered by Q2.
--   Q15,Q16   view typing     -> Q1 already proves TRANCHE_SIZE is VARCHAR2(480)
--                                and SECURITIES_MATURITY is VARCHAR2(16000).
--                                Both bugs CONFIRMED; only Q13/Q14 remain.
--   Q22  LISTAGG overflow     -> deprioritised. Q1 shows the list columns are
--                                VARCHAR2(32767) extended, not 4000.
--   Q27,Q30,Q31,Q33 -> moot under the no-new-columns rule.
--
-- Run against Oracle (DGSTREAM) directly, not through Starburst/Trino.
-- Paste results back labelled by Q number. Cost: [cheap] / [heavy].
-- ===========================================================================


-- ===========================================================================
-- BLOCK A — THE DCM ALLOCATION BUG          (blocks the vw_order_detail fix)
--
-- Today: LEFT JOIN OB_ORDER_MATCH_GROUP OMT
--          ON OMT.ROOT_ID = O.ROOT_ID AND OMT.PARENT_ID = O.PARENT_ID
-- keyed on deal+tranche, never the order — so every order on a tranche gets
-- the same FINAL_ALLOC. Q2 showed OB_ORDER.FINAL_ALLOC (NUMBER) exists on the
-- order row itself, so the fix is probably to DELETE this join rather than
-- rewrite it. These three queries decide which source is authoritative.
-- ===========================================================================

-- Q34 [cheap] Do the two FINAL_ALLOC columns agree where they overlap?
-- OB_ORDER_MATCH_GROUP.PRIMARY_ORDER_ID points at an order, so this is a
-- direct comparison. DECIDES: whether OB_ORDER.FINAL_ALLOC alone is sufficient.
SELECT COUNT(*)                                                     AS primary_orders_matched,
       COUNT(CASE WHEN NVL(o.FINAL_ALLOC,-1) =  NVL(m.FINAL_ALLOC,-1)
                  THEN 1 END)                                       AS alloc_equal,
       COUNT(CASE WHEN NVL(o.FINAL_ALLOC,-1) <> NVL(m.FINAL_ALLOC,-1)
                  THEN 1 END)                                       AS alloc_differs,
       COUNT(CASE WHEN o.FINAL_ALLOC IS     NULL
                   AND m.FINAL_ALLOC IS NOT NULL THEN 1 END)        AS only_matchgroup_has,
       COUNT(CASE WHEN o.FINAL_ALLOC IS NOT NULL
                   AND m.FINAL_ALLOC IS     NULL THEN 1 END)        AS only_order_has
FROM   OB_ORDER_MATCH_GROUP m
JOIN   OB_ORDER o ON o.ORDER_ID = m.PRIMARY_ORDER_ID;


-- Q6 [cheap] What IS a match group? Sample the meaningful columns.
-- DECIDES: whether FINAL_ALLOC there is a per-group total (in which case it
-- must never reach an order row) or a per-order value.
SELECT ORDER_GROUP_ID, PRIMARY_ORDER_ID, ROOT_ID, PARENT_ID,
       STATUS, IS_ACTIVE, FINAL_ALLOC, GB_ALLOC,
       LENGTH(REF_SOURCE_SECONDARY_ORDER_LIST) AS secondary_list_len
FROM   OB_ORDER_MATCH_GROUP
WHERE  FINAL_ALLOC IS NOT NULL
FETCH  FIRST 20 ROWS ONLY;


-- Q8 [cheap] Reconcile both allocation sources against tranche size on the
-- five busiest DCM tranches. The correct source should land near TRANCHE_SIZE;
-- a per-tranche value fanned across orders will overshoot by ~order_cnt.
WITH busiest AS (
  SELECT ROOT_ID, PARENT_ID, COUNT(*) AS order_cnt
  FROM   OB_ORDER
  GROUP  BY ROOT_ID, PARENT_ID
  ORDER  BY COUNT(*) DESC
  FETCH  FIRST 5 ROWS ONLY
)
SELECT b.ROOT_ID, b.PARENT_ID, b.order_cnt,
       t.TRANCHE_SIZE,
       o.sum_order_alloc,
       o.orders_with_alloc,
       m.match_group_rows,
       m.sum_matchgroup_alloc
FROM   busiest b
LEFT   JOIN OB_DEAL_TRANCHE t
       ON t.DEAL_ID = b.ROOT_ID AND t.TRANCHE_ID = b.PARENT_ID
LEFT   JOIN (SELECT ROOT_ID, PARENT_ID,
                    SUM(FINAL_ALLOC)   AS sum_order_alloc,
                    COUNT(FINAL_ALLOC) AS orders_with_alloc
             FROM   OB_ORDER GROUP BY ROOT_ID, PARENT_ID) o
       ON o.ROOT_ID = b.ROOT_ID AND o.PARENT_ID = b.PARENT_ID
LEFT   JOIN (SELECT ROOT_ID, PARENT_ID,
                    COUNT(*)         AS match_group_rows,
                    SUM(FINAL_ALLOC) AS sum_matchgroup_alloc
             FROM   OB_ORDER_MATCH_GROUP GROUP BY ROOT_ID, PARENT_ID) m
       ON m.ROOT_ID = b.ROOT_ID AND m.PARENT_ID = b.PARENT_ID;


-- ===========================================================================
-- BLOCK B — GRAIN INTEGRITY
-- If rows_ > grain_ the four-view split did not actually happen and the
-- duplicate-row bugs it was built to kill are back.
-- ===========================================================================

-- Q9 [heavy] The headline check. Run this one above all others.
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


-- Q9b [heavy] If any line above fails, split it by product so we know which
-- branch is at fault. Skip if Q9 is clean.
SELECT PRODUCT, COUNT(*) AS rows_,
       COUNT(DISTINCT DEAL_ID) AS deals_
FROM   DGSTREAM.VW_DEAL_SUMMARY GROUP BY PRODUCT;


-- Q10 [cheap] Is a "deal" one ECM transaction, or several?
-- The deal view keys on DEAL_TRANSACTION_ID but joins on ECM_TRANSACTION_ID.
-- If those are not 1:1, VW_DEAL_SUMMARY cannot hold PRODUCT+DEAL_ID grain.
SELECT COUNT(*)                            AS rows_,
       COUNT(DISTINCT DEAL_TRANSACTION_ID) AS deals_,
       COUNT(DISTINCT ECM_TRANSACTION_ID)  AS txns_
FROM   OPUS_ECM_TRANSACTION;


-- Q11 [cheap] Multiple Execution_Status rows per transaction?
-- This INNER JOIN appears in the deal, tranche AND order views — one bad row
-- multiplies all three at once.
SELECT COUNT(*) AS txns_with_multiple_exec_status
FROM   (SELECT ECM_TRANSACTION_ID
        FROM   OPUS_ECM_TRANSACTION_STATUS
        WHERE  STATUS_TYPE = 'Execution_Status'
        GROUP  BY ECM_TRANSACTION_ID
        HAVING COUNT(*) > 1);


-- Q12 [cheap] Every remaining unguarded join, one result set.
-- Any non-zero = a join that must be pre-aggregated before we ship.
-- Note OB_DEAL_ISSUER is already guarded by GROUP BY/MAX in vw_deal_summary
-- but joined raw in vw_tranche_summary — co-issued bonds duplicate tranches.
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
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID
        HAVING COUNT(*) > 1)
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


-- ===========================================================================
-- BLOCK C — TYPING
-- Q1 CONFIRMED: TRANCHE_SIZE deployed as VARCHAR2(480), SECURITIES_MATURITY as
-- VARCHAR2(16000). So "top N by tranche size" currently sorts lexically —
-- '900' beats '1000000' — and maturity is an unsortable NLS-formatted string.
-- Only one open question: is the ECM source safely convertible?
-- ===========================================================================

-- Q13 [cheap] Does TRANCHE_OFFER_SIZE hold anything non-numeric?
-- DECIDES: whether we can drop the VARCHAR2 cast for a numeric expression.
SELECT COUNT(*)                                                   AS total_non_null,
       COUNT(CASE WHEN NOT REGEXP_LIKE(TO_CHAR(TRANCHE_OFFER_SIZE),
                   '^\s*-?[0-9]+(\.[0-9]+)?\s*$') THEN 1 END)     AS non_numeric_vals
FROM   OPUS_ECM_TRANSACTION_TRANCHE
WHERE  TRANCHE_OFFER_SIZE IS NOT NULL;


-- Q14 [cheap] Show the offenders if Q13 is non-zero — the shape of the bad
-- values decides between a plain cast and TO_NUMBER(... DEFAULT NULL ON
-- CONVERSION ERROR).
SELECT DISTINCT TO_CHAR(TRANCHE_OFFER_SIZE) AS raw_value
FROM   OPUS_ECM_TRANSACTION_TRANCHE
WHERE  TRANCHE_OFFER_SIZE IS NOT NULL
AND    NOT REGEXP_LIKE(TO_CHAR(TRANCHE_OFFER_SIZE), '^\s*-?[0-9]+(\.[0-9]+)?\s*$')
FETCH  FIRST 25 ROWS ONLY;


-- ===========================================================================
-- BLOCK D — DCM STATUS, CONFIDENTIALITY, COUNT RECONCILIATION
-- ===========================================================================

-- Q17 [cheap] *** RUN THIS FIRST IF YOU RUN NOTHING ELSE ***
-- Every ECM branch excludes Confidential/Withdrawn/Terminated. No DCM branch
-- in any view excludes anything. If a confidential state exists here, those
-- deals are reaching users right now — a disclosure issue, not a data-quality
-- one, and it should not wait for the rest of this batch.
SELECT STATUS, COUNT(*) AS rows_, COUNT(DISTINCT DEAL_ID) AS deals_
FROM   OB_DEAL_TRANCHE
GROUP  BY STATUS
ORDER  BY rows_ DESC;


-- Q18 [cheap] Do DCM deals have tranches in mixed statuses?
-- DECIDES: whether vw_deal_summary's MAX(ODT.STATUS) can disagree with
-- vw_tranche_summary's per-tranche ODT.STATUS — today the same deal can report
-- two different statuses depending on which object you ask.
SELECT COUNT(*) AS deals_with_mixed_tranche_status
FROM   (SELECT DEAL_ID FROM OB_DEAL_TRANCHE
        GROUP BY DEAL_ID HAVING COUNT(DISTINCT STATUS) > 1);


-- Q19 [cheap] ECM drops CANCELLED/DELETED/PASS and unowned/non-dominant
-- orders. DCM drops nothing, anywhere. Q2 confirmed OB_ORDER has STATUS,
-- IS_ACTIVE and IS_FIRM_ORDER.
-- DECIDES: which DCM order predicates the views are missing.
SELECT STATUS, IS_ACTIVE, IS_FIRM_ORDER, COUNT(*) AS rows_
FROM   OB_ORDER
GROUP  BY STATUS, IS_ACTIVE, IS_FIRM_ORDER
ORDER  BY rows_ DESC
FETCH  FIRST 30 ROWS ONLY;


-- Q20 [heavy] Size the DCM order-count divergence.
-- vw_deal_summary counts OB_ORDER by ROOT_ID with NO filter; vw_order_detail
-- INNER JOINs OB_DEAL_TRANCHE on (deal, tranche). A deal card saying
-- "120 orders" then pages to fewer rows — breaks the count-honesty contract.
SELECT COUNT(*)                                       AS orders_total,
       COUNT(CASE WHEN t.DEAL_ID IS NULL THEN 1 END)  AS orders_without_tranche,
       COUNT(DISTINCT o.ROOT_ID)                      AS deals_total,
       COUNT(DISTINCT CASE WHEN t.DEAL_ID IS NULL
                           THEN o.ROOT_ID END)        AS deals_affected
FROM   OB_ORDER o
LEFT   JOIN OB_DEAL_TRANCHE t
       ON t.DEAL_ID = o.ROOT_ID AND t.TRANCHE_ID = o.PARENT_ID;


-- ===========================================================================
-- BLOCK E — LIST COLUMNS
-- ===========================================================================

-- Q21 [cheap] DCM CURRENCIES is not deduped. ECM hoists a SELECT DISTINCT into
-- the TC subquery; DCM LISTAGGs raw, so a 3-tranche USD deal renders
-- 'USD | USD | USD' where the same ECM deal renders 'USD'.
SELECT COUNT(*) AS dcm_deals_with_repeated_currency
FROM   (SELECT DEAL_ID FROM OB_DEAL_TRANCHE
        GROUP BY DEAL_ID HAVING COUNT(CURRENCY) > COUNT(DISTINCT CURRENCY));


-- Q23 [cheap] Pipe lists must align BY POSITION (spec 3.1). The DCM identifier
-- subquery orders TYPE and VALUE by T.TYPE but orders DELIVERY_TYPE by
-- T.DELIVERY_TYPE — a different sort, so position N of delivery does not
-- correspond to position N of type/value.
-- DECIDES: re-sort by TYPE, or collapse delivery to a single deduped value.
SELECT COUNT(*)                                          AS tranches,
       SUM(CASE WHEN d_distinct = 1 THEN 1 ELSE 0 END)   AS single_delivery_type,
       SUM(CASE WHEN d_distinct > 1 THEN 1 ELSE 0 END)   AS multi_delivery_type,
       MAX(rows_)                                        AS max_identifiers_per_tranche
FROM   (SELECT DEAL_TRANCHE_ID, COUNT(*) rows_,
               COUNT(DISTINCT DELIVERY_TYPE) d_distinct
        FROM   OB_TRANCHE GROUP BY DEAL_TRANCHE_ID);


-- Q24 [cheap] LISTAGG ties are non-deterministic. ECM identifiers sort by
-- IDENTIFIER_TYPE only, so a tranche with two identifiers of the SAME type can
-- zip type-to-value in the wrong order.
-- DECIDES: whether to add IDENTIFIER_VALUE as a tiebreaker.
SELECT COUNT(*) AS tranches_with_duplicate_identifier_type
FROM   (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, IDENTIFIER_TYPE
        FROM   OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL_IDENTIFIER
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, IDENTIFIER_TYPE
        HAVING COUNT(*) > 1);


-- Q25 [cheap] BND_BANK is MAX(CASE WHEN BND_BROKER='true' ...) so it returns
-- ONE bank. Joint B&D roles would silently lose all but the last alphabetically.
SELECT COUNT(*) AS tranches_with_multiple_bnd_true
FROM   (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
        FROM   OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
        WHERE  BND_BROKER = 'true'
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
        HAVING COUNT(*) > 1);


-- Q26 [cheap] TENORS is TENOR_VALUE || '-' || TENOR_PERIOD. Oracle treats NULL
-- as empty in concatenation, so a half-populated row renders '5-' or '-Y'
-- instead of NULL.
SELECT COUNT(*) AS rows_,
       COUNT(CASE WHEN TENOR_VALUE IS NULL AND TENOR_PERIOD IS NULL
                  THEN 1 END) AS both_null,
       COUNT(CASE WHEN TENOR_VALUE IS NULL AND TENOR_PERIOD IS NOT NULL
                  THEN 1 END) AS value_null_only,
       COUNT(CASE WHEN TENOR_VALUE IS NOT NULL AND TENOR_PERIOD IS NULL
                  THEN 1 END) AS period_null_only
FROM   OB_DEAL_TRANCHE;


-- ===========================================================================
-- BLOCK F — ENTITY VIEW
-- ===========================================================================

-- Q28 [heavy] Size, and the two known defects.
-- rows_ > distinct_ids confirms the declared grain [entity_type, product,
-- entity_id] is wrong — every branch also groups by NAME, so name variants
-- under one id produce several rows.
-- null_names on the DEAL branch = the missing IS NOT NULL guard.
SELECT ENTITY_TYPE, PRODUCT, COUNT(*) AS rows_,
       COUNT(DISTINCT ENTITY_ID) AS distinct_ids,
       COUNT(CASE WHEN ENTITY_NAME IS NULL THEN 1 END) AS null_names
FROM   DGSTREAM.VW_ENTITY_SEARCH
GROUP  BY ENTITY_TYPE, PRODUCT
ORDER  BY 1,2;


-- Q29 [heavy] Wall-clock for a realistic resolution — PLEASE REPORT THE TIMING,
-- not just the rows. This runs before the user's real question on every
-- entity-specific ask, so it is paid twice.
SELECT ENTITY_ID, ENTITY_NAME, ENTITY_ACTIVITY_COUNT, LAST_ACTIVE
FROM   DGSTREAM.VW_ENTITY_SEARCH
WHERE  ENTITY_TYPE = 'INVESTOR'
AND    UPPER(ENTITY_NAME) LIKE '%BLACKROCK%'
ORDER  BY ENTITY_ACTIVITY_COUNT DESC, LAST_ACTIVE DESC, ENTITY_ID
FETCH  FIRST 10 ROWS ONLY;


-- ===========================================================================
-- BLOCK G — ONTOLOGY-ONLY (no view change)
-- ===========================================================================

-- Q32 [cheap] SETTLEMENT_TS is on VW_DEAL_SUMMARY but unmodeled in the
-- ontology, while the agent's refusal text promises "pricing and settlement
-- dates". DECIDES: model it, or change the refusal text to stop promising it.
SELECT COUNT(*) AS ecm_deals, COUNT(SETTLEMENT_TS) AS with_settlement_ts
FROM   DGSTREAM.VW_DEAL_SUMMARY WHERE PRODUCT = 'ECM';


-- ===========================================================================
-- STILL OPEN — DECISIONS, NOT QUERIES
--
-- D1. MATERIALIZED VIEW for entity search: in scope this cycle, or a separate
--     DBA track? Biggest latency win available, but it is infra, not DDL.
--     If out of scope, say so and I will stop recommending it and optimise the
--     plain view instead.
--
-- D3. Is DGSTREAM Oracle 12.2+? Only matters if Q23/Q24 push a list column
--     near its limit. Low priority now that Q1 shows 32767-byte columns.
--
-- D4. Who owns the DCM confidentiality question (Q17)? If confidential DCM
--     deals are visible today that should not wait for this batch.
--
-- D5. Ontology blast radius when the views change — confirm this is complete:
--       ecm_dcm_deal.yaml     model settlement_ts (Q32)
--       ecm_dcm_tranche.yaml  model deal_region, deal_status, execution_status,
--                             settlement_currency, use_of_proceeds — all
--                             ALREADY on the view, just unmodeled; modelling
--                             them deletes a class of two-object questions
--       ecm_dcm_entity.yaml   correct the declared grain (Q28)
--       SKILL.md              retire the B&D pipe-index arithmetic, now that
--                             BND_BANK is a resolved column
--
--     D2 CLOSED: fixes only, no new columns, no removals.
-- ===========================================================================
