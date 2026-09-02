# DCM latency — source-table index review (2026-09-02)

Trigger: DCM data volume is large and users report slow responses. This review maps every
predicate and join our nine views put on the DGSTREAM source tables, so index gaps can be
diffed against what actually exists. Companion check file: `views/_checks/_index-census.sql`
(4 independent statements — run all, screenshot results to ADK).

## How our views reach the base tables (why this shapes the index list)

Every query arrives as `SELECT ... FROM vw_x WHERE col = :v` (BQS → Starburst pushes the
predicate into Oracle). What Oracle can do with it depends on the view block the column
comes from:

1. **ROW_NUMBER dedupe blocks** (`PARTITION BY <id> ORDER BY ...`): Oracle can push an
   outer predicate into the block **only if it is on a PARTITION BY column**. Our dedupe
   blocks partition by the entity's own id (ORDER_ID, ORDER_TRADE_ID, HEDGE_ORDER_ID...).
   So a filter on DEAL_ID/ROOT_ID **cannot** be pushed inside — Oracle scans the whole
   table and computes the window every time. **An index on ROOT_ID does not help these
   blocks today.** This is the main DCM cost: every deal-scoped order/trade question
   full-scans OB_ORDER / OB_ORDER_TRADE and sorts it.
2. **GROUP BY blocks** (OZ, OC, DN, SYNM, IDN, RAT...): Oracle can push join/filter
   predicates into these (view merging / join predicate pushdown). Here an index on the
   group key **does** pay: single-deal questions become index probes instead of scans.
3. **Whole-book aggregates** (league tables, top investors across all deals): full scans
   are inherent; no index changes that. Stats freshness and scan speed are what matter.

So the plan has two levers: (A) indexes for the pushable paths, (B) a small view change
that converts lever-1 blocks into pushable ones (below).

## Statement-by-statement: what each census check answers

| # | Statement | Answers |
|---|---|---|
| 1 | ALL_INDEXES + ALL_IND_COLUMNS | which of the candidate columns are already indexed (and whether any index is UNUSABLE) |
| 2 | ALL_TABLES stats | true row counts, and whether stats are stale/missing (LAST_ANALYZED old or NULL = bad plans regardless of indexes) |
| 3 | ALL_IND_EXPRESSIONS | decodes any SYS_NC columns from #1 (function-based indexes) |
| 4 | parent-key stability | whether each order/trade id maps to exactly one deal/tranche across duplicate feed rows — the precondition for the view-side fix in lever B |

## Candidate indexes (diff against census #1 before requesting anything)

Priority 1 — DCM hot path (the tables users are hitting when they say "slow"):

| Table | Columns | Serves |
|---|---|---|
| OB_ORDER | (ROOT_ID, PARENT_ID) | deal/tranche-scoped order questions — pays off only with lever B; OC group-by JPPD in vw_deal_summary pays immediately |
| OB_ORDER | (ORDER_ID) | dedupe partition key, OZ join |
| OB_ORDER_SIZE | (ORDER_ID) | OZ/OC demand lookups (joined in two views, per order) |
| OB_ORDER_TRADE | (ORDER_TRADE_ID) | dedupe partition key, trade-id lookups |
| OB_ORDER_TRADE | (ROOT_ID) | deal-scoped trade questions — pays with lever B |
| OB_HEDGE_ORDER | (HEDGE_ORDER_ID) / (ROOT_ID) | same pattern |
| OB_HEDGE_TRADE | (HEDGE_TRADE_ID) / (ROOT_ID) | same pattern |

Priority 2 — DCM dimension joins (smaller tables, joined from every DCM branch):

| Table | Columns |
|---|---|
| OB_DEAL_TRANCHE | (DEAL_ID, TRANCHE_ID); also (ORIGINATION_TRANSACTION_ID) |
| OB_DEAL_ISSUER | (DEAL_TRANCHE_ID); also (GFCID) |
| OB_TRANCHE | (DEAL_TRANCHE_ID) |
| OB_TRANCHE_RATING | (DEAL_TRANCHE_ID) |
| OB_TRANCHE_SYNDICATE_MEMBER | (DEAL_TRANCHE_ID) |
| OPUS_BASE_TRANSACTION_RELATED_PARTIES | (TRANSACTION_ID, PARTY_ROLE, PUBLISHED_TS) |
| OPUS_BASE_TRANSACTION | (TRANSACTION_ID) |
| OB_ORDER_TRADE_SYNDICATE | (ORDER_TRADE_ID, DEALER) — empty today, index is free insurance |

Priority 3 — ECM equivalents (volumes moderate; only if census shows gaps):
OB_ECM_ORDER (DEAL_ID) and (ORDER_ID); OB_ECM_ORDER_IOI (ORDER_ID);
OPUS_ECM_TRANSACTION (ECM_TRANSACTION_ID) and (DEAL_TRANSACTION_ID);
OPUS_ECM_TRANSACTION_STATUS (ECM_TRANSACTION_ID, STATUS_TYPE);
OPUS_ECM_TRANSACTION_TRANCHE (ECM_TRANSACTION_ID); the four tranche child tables
(ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID);
OB_ECM_TRADE_BOOK_INVESTOR_TRADE (INVESTOR_TRADE_ID);
OB_ECM_TRADE_BOOK_DESIGNATION (DESIGNATION_ID).

Notes:
- Likely several of these already exist as PK/unique indexes — that is exactly what
  census #1 settles. Only request the gaps.
- Name filters (investor/deal name contains-match) cannot use b-tree indexes; entity
  resolution already converts names to ids, so ids are the columns worth indexing.
- DGSTREAM is the feed schema — index DDL presumably goes through the feed/DBA team,
  same release train as views.

## Lever B — the view change that makes ROOT_ID indexes usable

Adding the parent keys to the dedupe PARTITION BY (e.g. OB_ORDER:
`PARTITION BY DO.ROOT_ID, DO.PARENT_ID, DO.ORDER_ID` instead of `DO.ORDER_ID`) keeps the
dedupe semantics identical **iff** every duplicate row of an id carries the same parent
keys — census #4 verifies exactly that (expect all zeros). With the partition keys
widened, Oracle can push deal/tranche filters inside the block, and the P1 ROOT_ID
indexes turn deal-scoped questions from full-scan+sort into index probes.

Affected files if adopted: vw_order_detail (both branches), vw_trade_detail,
vw_hedge_order, vw_hedge_trade, vw_designation (DEAL_ID+TRANCHE_ID+DESIGNATION_ID).
This is a re-handover decision — held for the user's call, contingent on census #4
returning zeros.

## Measured confirmation (OCP log, 2026-09-02 — see uat-issues-2026-09-02.md U3)

Server-side BQS timings: deal list 29.13s · entity resolution 40.21s · one deal_count
**401.20s execute (0 rows) + 36.67s enrich**. Entitlement and CyberArk are both
cache-hitting, so execute time is the whole problem. This also surfaces two levers
beyond indexes:

**Lever C — vw_deal_summary DCM branch structure.** The ECM branch joins its order
aggregate (OD) at the top level, where Oracle can eliminate the unreferenced LEFT
JOIN for questions that don't touch demand/counts. The DCM branch nests its order
aggregate (OC = OB_ORDER × OB_ORDER_SIZE, both full-scanned) INSIDE the deal derived
table — so **every** DCM deal question pays the full order-book aggregation even when
it only wants names/status. Restructure candidate: hoist OC to a top-level LEFT JOIN
mirroring the ECM shape. Same re-handover batch as lever B if adopted.

**Lever D — vw_entity_search cost.** It stacks vw_order_detail + vw_deal_summary
(twice), so every entity resolution recomputes both books — measured 40s. Indexes
don't help a stacked aggregate. The structural answer is a materialized view (or a
feed-team summary table) refreshed periodically — that is a NEW whitelist-gated
object, so if wanted it should enter the current whitelist window, not a later one.
User decision.

## Census results (2026-09-02, index-1..4 screenshots)

**Already indexed (no request needed):** OB_ORDER (ROOT_ID, PARENT_ID, ORDER_ID) +
(ORDER_ID) + (GPID) + (NAME); OB_ORDER_SIZE (ORDER_ID); OB_ORDER_TRADE
(ORDER_TRADE_ID); OB_HEDGE_ORDER / OB_HEDGE_TRADE (own id); OB_ORDER_TRADE_SYNDICATE
(ORDER_TRADE_ID); OB_TRANCHE / OB_TRANCHE_RATING / OB_TRANCHE_SYNDICATE_MEMBER /
OB_DEAL_ISSUER (DEAL_TRANCHE_ID-leading); OB_ECM_ORDER (DEAL_ID, ORDER_ID);
OB_ECM_ORDER_IOI (ORDER_ID); OPUS_ECM_TRANSACTION (ECM_TRANSACTION_ID) +
(DEAL_TRANSACTION_ID); STATUS (ECM_TRANSACTION_ID, STATUS_TYPE); TRANCHE and its
child tables (ECM_TRANSACTION_ID-leading); designation/investor-trade families
(rich). FBIs decoded: PRICING_TS desc, UPPER(TYPE) — neither affects us.

**Row counts:** OB_ORDER 5,001,148 · OB_ORDER_SIZE 4,848,439 · OB_ORDER_TRADE
489,901 · OB_HEDGE_ORDER 388,782 · OB_TRANCHE_SYNDICATE_MEMBER 376,636 ·
RELATED_PARTIES 361,377 · OB_HEDGE_TRADE 168,826.

**INDEX REQUEST LIST (the actual gaps, to feed/DBA team):**
1. OB_ORDER_TRADE (ROOT_ID) — 490k rows, deal-scoped trade asks
2. OB_HEDGE_ORDER (ROOT_ID) — 389k
3. OB_HEDGE_TRADE (ROOT_ID) — 169k
4. OPUS_BASE_TRANSACTION_RELATED_PARTIES (TRANSACTION_ID, PARTY_ROLE, PUBLISHED_TS)
   — 361k rows, NO index at all, joined in six view branches
5. OPUS_BASE_TRANSACTION (TRANSACTION_ID) — 140k, key only trails a snapshot index
6. OB_DEAL_TRANCHE (DEAL_ID, TRANCHE_ID) — 74k, existing indexes lead with the
   concatenated DEAL_TRANCHE_ID column instead
7. optional: OB_DEAL_ISSUER (GFCID)

**STATS REQUEST:** gather stats on OB_ORDER (last analyzed 24-JUL) and especially
OB_ORDER_SIZE (**14-APR**, ~5 months stale at 4.8M rows); OB_ORDER_TRADE_SYNDICATE
last analyzed NOV-2024 (empty, harmless).

## Status
- [x] census run (4 statements) — screenshots in ADK 2026-09-02
- [x] diff done → request list above (7 indexes + stats gather)
- [x] stats freshness verdict: OB_ORDER_SIZE badly stale, OB_ORDER 5 weeks
- [x] lever B GO (stmt 4 all zeros) — APPLIED to 4 files, 5 dedupe blocks
- [x] lever C APPLIED (vw_deal_summary DCM OC hoisted to top-level LEFT JOIN)
- [ ] re-hand wave: vw_deal_summary, vw_order_detail, vw_trade_detail,
      vw_hedge_order, vw_hedge_trade; then re-pull OCP timings (same 3 shapes)
- [ ] lever D decision (entity_search materialized view — new whitelist object)
- [ ] index + stats request submitted to feed/DBA team
