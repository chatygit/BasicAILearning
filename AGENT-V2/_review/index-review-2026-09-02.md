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

## Status
- [ ] census run (4 statements) — screenshots to ADK
- [ ] diff candidates vs existing indexes → final index request list
- [ ] stats freshness verdict (census #2)
- [ ] lever B go/no-go (census #4 + user decision on re-handover)
