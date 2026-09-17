# MCP result-cache design (2026-09-02)

Goal: make repeat and follow-up queries fast by caching BQS results in the MCP
server's process memory (OCP pods have headroom). Complements — does not replace —
the view/index work: a cache turns the *second* ask instant; the views make the
*first* ask tolerable. Server code is PROD-frozen, so this is a release-train item;
design now, ship on the train, flip on via env.

## Domain staleness model (the user-supplied insight this design is built on)

Once a deal is **settled**, its orders and trades are effectively immutable.
**Designations and closeouts keep changing** after settlement. Entity identity
(investor names/GPNUMs, issuer GFCIDs) is essentially static. And everything
arrives via the DataGlobe feed, which has its own latency — cache staleness is
small relative to feed lag the users already live with.

**Confirmed by the user 2026-09-02: bankers NEVER use this agent for live deals.**
That removes the live-bookbuild staleness risk the first draft engineered around —
the queried surface is settled/priced history plus post-settlement workflow
(designations/closeouts). Consequence: long TTLs are safe everywhere EXCEPT the
designation/closeout objects, which stay short because they are the one surface
that moves after settlement.

## Workload-aware design — what the views, the pull patterns, and the prompt corpus dictate

(2026-09-03 revision: the generic SQL-keyed design below is upgraded by what we know
about OUR workload. This section is the build spec's heart.)

**The pipeline shape.** Every banker ask runs the same BQS pipeline: discover
(in-memory, nothing to cache) → **entity resolution** (vw_entity_search) → the
metric query → drill-downs on the SAME ids within the conversation (deal card →
its orders → its tranches → its trades; the 40-id smaller-side ferry). So cache
value concentrates in three places: a GLOBAL long-lived entity tier (the same
BlackRock/Fidelity/JPMorgan resolutions repeat across all users, every day), a
result tier for metric queries, and canonical keys so drill-down/ferry repeats
actually hit instead of fragmenting.

**Tier E — the in-process entity snapshot (solves lever D with NO whitelist
object).** vw_entity_search costs 40s+ to COMPUTE (measured; the user cancelled a
full pass) but its OUTPUT is tiny: tens of thousands of rows × 7 narrow columns —
a few MB. So: load the whole entity table into pod memory, refresh hourly in a
background thread (serve the old snapshot during refresh), and answer entity
requests in-process — the agent's entity queries are simple shapes (contains-match
on entity_name, eq on entity_type/product, order by activity, limit) that a
Python evaluator handles in microseconds over 50k rows. Any request shape the
evaluator can't handle falls through to SQL unchanged. Staleness: a new entity
appears on the next refresh — fine under no-live-deals. This kills the single
worst latency in the product without the Oracle-MV whitelist path; the MV remains
the fallback if refresh cost or pod memory disappoints.

**Canonical keys — we own the builder, so exploit it.** Before hashing, canonicalize
the REQUEST: sort ANDed filters by (field, op), sort IN-list values, upper-case
LIKE values (the generated SQL is UPPER-LIKE-UPPER, so this is semantics-free).
The corpus is full of repeated ferry shapes and drill-downs where incidental
filter/IN-list ordering would otherwise fragment identical questions into distinct
keys. limit/offset/order_by stay in the key (different pages differ).

**Cost-aware eviction — we already measure what every entry cost.** The BQS timing
line gives execute seconds per query for free; store it on the entry and evict by
lowest (cost × recency), GreedyDual-style, never pure LRU. A 112s
top-investors league table must not be evicted to keep fifty 1-second deal cards.

**Historical tier by request inspection (simpler than the settled-deal map).** Any
request whose date filters bound the ENTIRE range ≥30 days in the past is
immutable under no-live-deals → 24h TTL regardless of source — except
designation/trade_syndicate, whose short per-source cap always wins. The filters
themselves prove historicity; no lookup map needed. The deal-id settled map stays
a phase-3 option for id-scoped, undated asks.

**What the prompt corpus says about warmers (phase 3).** The repeated demo/UAT
shapes are enumerable: top investors by allocation/order size (per product/year),
biggest deals by sector/region/year, subscription-ratio leaders, per-issuer deal
lists for the marquee names. A dozen canonical requests refreshed off-peak, plus
the Tier-E snapshot, cover most FIRST-ask latency — the result cache covers every
repeat.

**Never cache:** error responses; the zen path; and masked-empty results from the
"Rounding necessary" fetch fallback — until the release-train unmasking fix
lands, the 60s zero-row cap bounds that damage.

## Where the cache sits

`domain_query_service.run()`, between `assert_read_only(built.sql)` and
`execute(...)` (services/domain_query_service.py:254-262): cache `(columns, rows)`
— the execute output, which is 100% of measured cost. `format_result` (0.00s) and
enrichment stay live; the 0-row probe cache in bqs/suggestions.py already covers
enrichment. Implementation mirrors `_PROBE_CACHE` (suggestions.py:59-91) upgraded:
proper LRU, byte accounting, thread-safe (stateless_http serves threads).

Micro-win in the same change: `fetch_as_of_date(spec, dialect)` is a separate DB
call on EVERY query (domain_query_service.py:271) — memoise 60s.

## Cache key and the entitlement invariant

Key = SHA-256 of `(resolved_source, built.sql, canonical params)` — built AFTER the
request canonicalization above (sorted filters, sorted IN-lists, upper-cased LIKE
values), so semantically identical asks share one key.

**Why this is entitlement-safe:** the gate injects the caller's entitled products as
a `product` filter into the BQS request BEFORE planning (mcpserver.py), so the
built SQL + params embed the scope. Two users with the same product entitlements
produce byte-identical SQL and MAY share an entry — that is exactly the product-level
entitlement model. **Invariant to pin with a test:** two requests differing only in
product scope must produce different keys; if entitlement ever becomes finer than
product-level, the effective scope (or soeid) must join the key. Date anchors are
embedded at build time, so day boundaries roll keys naturally.

Never cached: error responses, the zen_api entity path (external service, its own
entitlements), entries above the size cap.

## TTL policy — three phases

**Phase 1 (ship first): per-source TTLs, config-driven** — a `cache_ttl_seconds`
knob per ontology object (ontology YAML is our config surface), global default via
`ECM_DCM_RESULT_CACHE_TTL_SECONDS` (<=0 disables everything):

| Source | TTL | Why |
|---|---|---|
| capital_markets_entity | 3600s | names/ids static; 40s measured, resolved in nearly every conversation — single biggest win |
| deal, tranche | 3600s | no live-deal usage (confirmed) — the queried surface is settled/priced history |
| order, trade, hedge, hedge_trade | 3600s | same — order/trade books queried only post-settlement, where they are immutable |
| designation, trade_syndicate | 180s | the "these DO change" objects — closeout workflow moves after settlement |
| any 0-row result | 60s override | zero-is-a-claim; an empty answer must not outlive feed catch-up |

(First draft used 600–900s for deal/order/trade against bookbuild staleness; the
no-live-deals confirmation obsoleted that caution. Feed corrections/restatements
remain the only staleness source on those objects — 1h is comfortably inside
what a feed-lagged consumer already tolerates, and phase 2's 24h tier follows
the same logic further.)

**Phase 2 — the workload tiers:** the Tier-E entity snapshot (the biggest single
win), and the request-inspection historical tier (whole date range ≥30 days past
⇒ 24h TTL; designation/trade_syndicate per-source caps always win). Both specified
in the workload section above.

**Phase 3 options, in value order:**
1. Prompt-corpus warmers: the enumerated canonical shapes refreshed off-peak.
2. **Watermark validation**: background probe of `MAX(PUBLISHED_TS)` (or
   DG_UPDATED_TS) per big table every ~60s; unchanged watermark ⇒ entries for that
   table stay valid regardless of TTL — near-perfect freshness AND long retention.
   Requires descending-key indexes on the watermark columns to make MAX() an
   index-only touch — **add to the feed-team index request** if we go here.
3. The deal-id settled map for id-scoped undated asks (extends the historical tier).
4. Cross-pod (Redis/OCP service) only if replica count makes per-pod hit rates
   disappointing — per-pod first; no new infra, no security review.

## Bounds and ops

- Bounds: `ECM_DCM_RESULT_CACHE_MAX_ENTRIES` (default 512) and `..._MAX_BYTES`
  (default 256MB); skip entries >2MB (row caps from the response-budget work make
  these rare). Eviction: expired first, then lowest (measured execute cost ×
  recency) per the workload section — never pure LRU.
- Kill switches: global TTL env <=0; pod restart clears (OCP rollout = flush).
- Observability: extend the gated `BQS timing` log line with `cache=hit|miss age=Ns`
  — the [latency] gate pins that line's format, so the gate pins update IN THE SAME
  CHANGE. Periodic hit/miss/evict counter log.

## Why the hit rate is worth it

- Entity resolution repeats every conversation turn-set → 40s → ~0 from turn 2.
- Follow-up questions re-touch the same deal/investor shapes within minutes.
- Retry storms are free: the BlackRock-style abort-and-retry re-paid every query;
  with the cache a retried recipe replays instantly.
- Multi-user common asks (league tables, "deals priced this week") amortize across
  the desk at product-level scope.

## Test/gate plan

- Unit: hit, expiry, LRU + byte eviction, 0-row short TTL, key-includes-params,
  the entitlement-scope key test (differing product filters ⇒ different keys),
  disabled-by-env bypass.
- Gate: [latency] pin extension for the new log fields; pin that the cache lookup
  sits AFTER `assert_read_only` (read-only guarantee unchanged).
- Regression: add a promote-checklist line — TTL envs reviewed per environment
  (QA≠PROD tuning).

## Rollout

Implement behind env default-ON with conservative TTLs but ship on the release
train; DEV first (watch hit rate + any freshness complaint against the feed lag
baseline), then PROD. Phase 2 rides the following train once the settled-deal map
is proven in DEV.

## Status
- [x] design (this doc)
- [x] staleness tolerance settled: agent never used for live deals (user,
      2026-09-02) — TTL table updated; only the designation cadence (180s)
      might still warrant a team sanity-check
- [x] workload merge (2026-09-03): pipeline tiers, Tier-E entity snapshot
      (lever D without a whitelist object), canonical request keys,
      cost-aware eviction, request-inspection historical tier, corpus warmers
- [ ] implementation (release-train work item)
- [ ] watermark-index request decision (phase 3 #1) — bundle with feed-team asks
