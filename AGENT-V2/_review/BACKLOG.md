# BACKLOG — Capital Markets Agent (AGENT-V2)

The ONE register. Open items only, grouped by the layer that can ship them.
When an item closes, delete it — git history keeps the story. Decisions and
lessons go to memory, not here. SQL checks for the user go to
`views/_checks/db-asks.sql`; asks to other teams to `ASKS-external.md`;
promotion steps to `PROMOTE-CHECKLIST.md`; prompts and run results to
`QA-PROMPTS.md`.

Layer ladder (view-change discipline): config → server → catalog → views.
Views are approval-gated and ship only in planned batches. OPUS_BASE tables
are allowed but FROZEN (no new dependencies). We have NO PROD access — every
PROD item is an ask. Finding ids (SKILL-n, CAT-n, V-n, SRV-n, RT-n, XL-n)
refer to the 2026-09-17 workflow analysis (memory: analysis-2026-09-17).

## 0. Sequence (analysis 2026-09-17)
- Phase 0 — DONE 2026-09-17 except the UAT baselines: gate fails on SKIPped
  tests, size ratchet, slot-aware [names], corpus test with golden SQL, catalog↔view
  contract test (16 products drifts fixed in the same commit), two broken catalog
  examples fixed (dir: → direction:). Still to do: K1–K7 on UAT (db-asks G).
- Phase 1 — config: the nine cross-layer fixes DONE 2026-09-17; compression
  PASS 1 DONE 2026-09-17 (SKILL 93,427 → 63,402 bytes, every gate pin kept,
  1680 checks green). Pass 2 (→ ≤45k) waits for the six-prompt before/after
  (QA-PROMPTS token baseline) — candidates: §2 two-step prose, §3 routing
  rows, §6 table rows, §11 style bullets, the class-word map. PROD push rule:
  the compressed SKILL is UAT-only until the yaml/server train ships to PROD
  (deleted §7b lists exist only in the catalogs); a PROD-only SKILL push before
  that = git HEAD SKILL + the nine small fixes, not the compressed file.
- Phase 2 — server + ontology release train: SRV-1 → SRV-4 → SRV-3 → CAT-3 →
  SRV-2 → SRV-5 → SRV-6; CAT-1 → CAT-2 → CAT-4/XL-1/2/3 → CAT-5 → CAT-6 →
  SKILL-2 catalog fixes → XL-4 (with RT-3 xfails un-marked) → entity stem rule.
- Phase 3 — view batches: A = V1 (+V4 fallback) + V2 + RT-4; B = V3, V6, V5.
  K7 regression = no handover.

## 1. Config (SKILL / agents.yaml / QA-PROMPTS) — ships freely; PROD freeze = SKILL + agents.yaml only
- [ ] UAT run 5 after the NEXT SERVER PUSH (the matrix examples + disambiguation
      hint ride it): 36 (TC1, ⚡ args again), 34 (REGULAR orders — must carry
      indication/allocation/unit/Security), 24, 35, 33 (a convertible deal).
      Then 15/3/20 once more for the token line.
- [ ] Server nudge (release train, not yet written): when a request has a
      demand/allocation metric + ONE deal_id/transaction_id eq filter + no
      tranche_name/deal_id dimension + limit ≤ 25, attach a response hint
      "single-deal top-N: use the per-tranche matrix (partition_by
      [deal_id, tranche_name], both figures)". Prose failed 4x; the catalog
      example is the fix most likely to hold, the hint is the backstop.
- [ ] 15 matrix: issuer_name + tenors columns missing from the Fidelity answer
      although the ORDERBOOK MATRIX note lists them — check it is applied.
- [ ] Per-tranche listings must carry tranche_name ("three indications" for
      Amundi were three tranches, unlabelled).
- [ ] E9: "hedge orders for deal 75043505" → zero — was the txn id sent as
      deal_id? Needs the ⚡ args. If so: an 8-digit id on DCM is a
      transaction_id (DCM deal ids are 'I-…' strings), whatever word was used.
- [ ] Placeholder-table behaviour (agent narrates a query it never ran, then
      emits '...' rows) — budget-exhaustion doctrine; watch on UAT.
- [ ] Company-profile hallucination on unsupported asks — routing, open.
- [ ] PO units feedback — DONE in config, census J done (UAT 2026-09-21):
      order-figure unit = the row's demand_unit (BOND on convertibles, SHARES on
      common, currency/percent bids labelled as such); convertible DEAL SIZE is a
      par amount, never comparable to the book; counts exact; mixed tables carry
      Security + unit. Retest QA 33/34. Open for the PO: is "bonds" also the
      label they want for Convertible Preferred (stored bids are mostly BOND)?
- [ ] PROD, under the freeze: ship the SKILL-only "LIMIT IS NOT DEMAND" rule
      now; the value half needs the view release (IOI rebuild).
- [ ] Interim guards until the train: SKILL 284 (VALUE FIRST) and 641 (DCM members) byte-exact — the only layer overriding the stale order/tranche catalog notes in PROD (gate 524, 1988) — SKILL-2
SKILL compression, pass 2 (63,402 → ≤45,000 bytes) after the token measurement:
- [ ] Pass 2 candidates: §2 two-step prose (~4.3k → 2.5k), §3 routing rows, §6 table rows (~7.5k → 4.8k), §11 bullets (~5.9k → 4.5k), class-word map (~2.4k → 1.8k); every deletion checked with the pin-range helper (scratchpad pinmap.py) and the gate after each section
- [ ] agents.yaml ratchet 20,618 → 8,000 in step with the §11/§0b survival-kit decision — gate §14 680-694 requires the overlap (RT-6)
- [ ] Measure: six-prompt before/after (QA-PROMPTS 1, 2, 3, 15, 16, 18 — one promptTokenCount each) at the end of the compression

## 2. Server (release train; ontology yamls ship inside it) — DONE = in repo, undeployed
- [ ] DONE metric-slot explainer: `_explain_cross_object` checks the requesting
      object's metrics first (E10; tests in tests/test_cross_object_error.py).
- [ ] DONE config.py default BQS_ENABLED_SOURCES = nine sources.
- [ ] DONE (in repo, undeployed) suggestions.py disambiguation hint no longer instructs a NUMBERED-list menu — it asks for the combined figure + per-entity breakdown in the same turn (UAT 2026-09-18: prompts 3, 15, 20 each burned 3 extra turns on the menu). Ships with the next server push; the SKILL/agents rule covers it meanwhile.
- [ ] SRV-1 MCP result de-dup: `output_schema=None` + one compact TextContent, compact `tool_serializer`; lazy imports or extended test stubs — every result reaches the model twice (~16k tokens per tranche fetch) (test_entitlement_gate.py 15 cases; gate 1538/1210 on the wrapper; importorskip Client test; PROMOTE-CHECKLIST FastMCP/ADK check; exclusive with ASKS-external §1b)
- [ ] SRV-4 tool schema via `Annotated[..., Field(description=...)]` with the metric-slot rule on dimensions/filters; docstrings < 1,500/800 chars; `question` signature untouched; tools.yaml:48 nine — −800 tokens/call, class-1 defence at the argument (gate 1111, 1210 moved, new textual pins; QA 2, 24)
- [ ] SRV-3 `ECM_DCM_SQL_AUDIT` default off, one-line paging keeping "rows N-M", delete `scored`; SKILL 895 drops generated_sql only — 300-550 tokens/result (test_response_paging.py :144 rewritten; gate 1239/1243-1246/2496 moved)
- [ ] CAT-3 discovery(): drop `_generic_how_to_use()` and response_features suggestions/disambiguation; prune by `products:` ∩ `entitled` only when entitled non-empty — −3k chars/fetch; the only route to tranche ≤8k without cutting vocabulary (gate 527-528/2271 → SKILL, 1595/1624 kept; test_discovery_carries_entitled_products + 3 pruning tests; QA 1, 11, 14, 15, 16)
- [ ] SRV-2 zero-row enrich: exec_seconds threaded; `BQS_ENRICH_PROBE_BUDGET_SECONDS`=10, `BQS_MAX_SUGGESTION_PROBES`=2, entity_name guesses first; no block for curated same-value filters — k serial 19-29 s probes after the answer is known (tests/test_suggestion_budget.py; gate 1268-1282; SKILL 861-863 keeps "the *slow* path"; QA 31)
- [ ] SRV-5 Trino `query_max_execution_time` from query_timeout_seconds (240 s big three, 120 s others); INERT comments out; gate floor ≥120 — the only bound today is the 300 s client abort the agent retries (stub-connector test; EXCEEDED_TIME_LIMIT → query_timeout; QA 32; confirm POC connector kwarg first)
- [ ] SRV-6 `_entitlement_gate` returns (denial, entitled), called once; delete Oracle/Postgres executor branch, zen path, template tool/resource/prompt; as_of_date emitted as null; cache-design.md:90 corrected — ~600 dead lines (scoping tests tuple-shaped; single-call counting stub; gate 1012-1022 scoped to run_bqs_query body; confirm POC consumers)
- [ ] CAT-1 catalog one-home-per-fact: doctrine on filters, dimension one-liners, how_to_use restatements deleted; relocate `censused QA+UAT 2026-09-04` — 15-20k chars off the big three, one fewer dilution vector (gate TRAPS 392-403, 384, 429-442, 1974; test_yaml_schema_hygiene; QA 2, 8, 9; literal-set diff empty)
- [ ] CAT-2 provenance clauses → YAML comments; six pins re-pinned date-free; rendered-text citation check — 8-10k chars; no UAT counts / PO txn id in the payload (gate 1831/1847/1852/1857/1938/1973; QA 15, 16, 25; discover size measured)
- [ ] CAT-4 + XL-1/2/3 stale refusals: delete `syndicate_on_dcm`, `cancelled_deleted_orders`; `pricing_economics` → `spread_to_benchmark`; `hedge_securities_count` → hedge-listing redirect; entity "ALWAYS NULL for INVESTOR + DCM" softened; tranche 99-100/811/688/241-243/971-973/1037-1038 corrected; stale comment blocks out — four wrong-refusal classes on exposed fields (gate 237/459/461/610 + negatives; test_planner_contract; QA 3, 5b, 5c, 7, 26, 27, 28, 30)
- [ ] CAT-5 boilerplate once per object (date rule, TEXT ids + 40-cap, ferry line, product filter "Set it when the product is known") — 2-2.5k chars; closes the "ALWAYS set product" cause of class 2 (gate [time] 419 extended to date-bearing objects, 421, [yaml] 96-115; QA 1, 15, 5b, 17, 25)
- [ ] CAT-6 how_to_use reorder + tranche never-guess sentence — MATRIX/TOP-N sit 6.7-8.2k chars into the rendered list (gate 1803-1808 extended to TRANCHE; 1819-1827/1847-1848/470-471 presence; QA 2, 7, 15, 16, 18)
- [ ] SKILL-2a/b/d + SKILL-4 catalog side: order.yaml 156-163 value-first; 143-144 partition_by `[deal_id, tranche_name]` with deal_id in the MATRIX projection; tranche 690-691 anchored Citi forms keeping `%CITIGROUP%` — catalog beats SKILL by the SKILL's own precedence note (gate 524, 1919-1920, 1848, 1825-1827, 2148-2149 + negatives; planner bad_partition test; QA 14, 16, 23)
- [ ] SKILL-6 gate: description starts with its `products:` token; fix the seven exceptions — the leading token is the agent's only applicability hint (new textual check; QA 11)
- [ ] SKILL-3 catalog side: entity.yaml gains the SpaceX stem + "re-asked question gets a NEW strategy" rules; comment 15-18 updated with V3 — only entity doctrine not yet in the yaml (gate 1791-1792 stay on SKILL; QA 10, 17)
- [ ] TODO unmask fetch errors — surface the DB error text.
- [ ] TODO DENSE_RANK for partition_by top-N (ties at the boundary).
- [ ] TODO result cache — spec in cache-design.md; build on "build it".
      Today every "next N" re-runs the same 62 s query.
- [ ] TODO units guard, defence in depth: per-metric requires_single_value
      [product] — the entitlement gate replaces the agent's product filter
      with `in [ECM, DCM]`, so requires_filters can never fire.
- [ ] TODO bad_having_grain guard: reject `having` on a COUNT-DISTINCT metric
      whose column is also in dimensions (0 rows by construction).

## 3. Views (approval-gated batches; files handed verbatim, comment-free)
Batch A:
- [ ] V1 (baseline UAT 2026-09-18: K6 17.0 s, K7 25.1 s; deal-scoped K1b 0.6 s — already fine, V1 is for the non-key filters only) vw_order_detail DCM/ECM dedupe → correlated min-ROWID NOT EXISTS (hedge/trade blocks excluded — their survivor is latest PUBLISHED_TS); supersedes the txn-id PARTITION BY item — non-key predicates (investor name/id, dates, currency, txn id) cannot push into the window (rows 9, 6, 1d, 1j, 21, 21b; ORA_HASH identity per product; K6 before/after; K7 unscoped-aggregate go/no-go; QA 15, 16, 17, 18; NULL-guard pins, [opusbase] 3)
- [ ] V4 fallback if V1 is rejected: txn-id pushdown joins the EXISTING deduped ODT block inside the DCM window with DT.ORIGINATION_TRANSACTION_ID in PARTITION BY (never the raw table); no hedge extension — 19-29 s vs 2-6 s (row 9; K9 vs K1; QA 16, 25, 17, E9; TRANSACTION_ID last projection)
- [ ] V2 (baseline: K2 28.7 s for a DCM deal COUNT — lever C did not make it cheap) PCM x6 / ODI x3 → `MAX(col) KEEP (DENSE_RANK FIRST ORDER BY PUBLISHED_TS DESC, ROWID)` GROUP BY join key — window views are never join-eliminable; every aggregate pays a 361k-row scan+sort (rows 7, 8, 9, 1e, 1o, 1w; K2 recorded; K8 DBMS_XPLAN deal AND tranche; QA 10, 19; [opusbase] 3/3/3)
- [ ] RT-4 deploy-check section A → nine column-count rows (expected_ = file projection, asserted by RT-3); rows 22 (txn→deals, INFO) / 23 (bookless by product, INFO) in section B agg; PROMOTE-CHECKLIST step 2 rewritten — a partial deploy becomes a FAIL naming the view (A0 + nine rows + 17/2/3/18; grain 7-13b unchanged; gate 498/2184 untouched)
Batch B:
- [ ] V3 (baseline: K4 146.7 s full pass) vw_entity_search INVESTOR branch from OB_ORDER/OB_ECM_ORDER with the order view's population predicates; `CAST(MAX(TT.PRICING_TS) AS TIMESTAMP(3))` on ECM — re-derives the 5M-row order view for six columns (K11 census incl. SUM(ENTITY_ACTIVITY_COUNT) identical; K4 before/after; QA 3, 10, 17; [opusbase] 0)
- [ ] V6 DEAL_SHARING_TYPE folded into the syndicate member block per product — two scans of a 377k-row table for one ask (rows 8, 1q, 18, 20 recorded before, 20b, ad-hoc ECM SOLO count; `_CITI_RX` count 3; QA 23)
- [ ] V5 ECM deal branch in the lever-C shape (D = T⋈S grouped; deal-keyed blocks top-level; 41 aliases) — uniform shape + cheaper entity branches, not a latency claim (rows 7, 1e, 1o, 1w, 4, 4b, 15b, 15c; K10 vs K2; multi-transaction issuer hash probe; QA 2, 4, 11; T PARTITION BY unchanged pending census)
- [ ] Standing check S3 gains a Starburst EXPLAIN of `WHERE product = 'DCM'` on vw_deal_summary — CHAR(3) literal pushdown unverified (type change if it fails; own decision)
- [ ] DEAL_CLASS on the deal/tranche/order ECM branches (OPUS_ECM_TRANSACTION.
      PRODUCT_EQUITY_CLASS_VALUE — censused UAT 2026-09-18): the EXECUTION
      FORMAT / VEHICLE axis, not a unit axis. Values: Fully Marketed, Marketed,
      Accelerated Bookbuild, Bought Deal, Overnight, Blocktrade, Dutch Auction,
      Registered Direct, PIPE (two spellings), Rights, SPAC, REIT, MLP, BDC,
      Closed End Fund, Registered, Unregistered, Retail, NULL. Unlocks "block
      trades / bought deals / ABBs / SPAC IPOs / REIT follow-ons" as ONE filter.
      Additive (OPUS_ECM allowed); DCM NULL; expose as dimension + like filter
      (merge the two PIPE spellings). Until exposed the catalogs say "not
      available yet" for these, never "not stored".
- [ ] SIZE_UNIT on the deal/tranche ECM branches: CASE on equity_type → 'shares'
      (common, ADR/GDR, units, warrants) / 'par' (Convertible Bonds, Exchangable
      Notes, Convertible Preferred) — the source SIZE_UNIT is empty on 99.9 % of
      deals (J2), so the class is the only signal; DCM = 'currency'. Additive.
      (Order-level unit needs no view change: demand_unit already carries it.)
- [ ] DCM DEAL_PRODUCT_TYPE_LIST (OB_DEAL_TRANCHE) on the deal view as
      dcm_deal_class — far better populated than DEAL_PRODUCT (26k Investment
      Grade, 7k High Grade, 3k High Yield, EM, ABS, LevFin …) and a deal-level
      class beside tranche product_class; comma list. Additive.
- [ ] PRICING & SENTIMENT batch — censused UAT 2026-09-18 (H + I), ranked:
      (1) ADDITIVE on vw_order_detail, DCM branch, from OB_ORDER_SIZE's latest
      row per order: order_price_basis (TYPE: reOffer 99 % / benchmark /
      midSwap / minYield / maxPrice / floatingRate — ~55k limit rows),
      limit_spread (SPREAD_DEMAND), limit_yield (MIN_YIELD), limit_price
      (PRICE_DEMAND), size_change (AMT_CHANGE, filled on 917,788 rows),
      order_ts (CREATED_TS, ~100 %) → price sensitivity AND book momentum
      ("how the book built after guidance") for DCM. ECM NULL stubs.
      (2) ADDITIVE on the deal/tranche views, ECM: last_close_before_offer /
      _launch (27 % / 34 %), initial_deal_amount (80 %) → discount-to-close,
      upsizing.
      (3) NEW grain vw_tranche_pricing (OB_TRANCHE_PRICING: IPT → Guidance →
      Revised Guidance → Launch per tranche; types PRICE/SPREAD/YIELD/COUPON/
      benchmark/minYield) — stage rows exist on ~11k UAT tranches but VALUE on
      only ~300; build ONLY after the PROD count (db-asks S4.11) shows values.
      (4) NEW grain vw_order_ioi (ECM: one row per order × limit point; 28 % of
      orders limited, 6 % multi-point) or additive limit_type / points /
      qty_at_lowest_limit on the order view.
      Dead ends: PRICE_GUIDANCE (0.7 % filled), ECM IOI timestamps (39 rows),
      LIMIT_DISCOUNT_POT (a boolean). All approval-gated; OPUS_BASE untouched.
- [ ] STATUS EXCLUSION (Vinit 2026-09-21) — censused UAT (db-asks K, closed):
      TRANCHES: DCM only (ECM tranche status is NULL on 50,510/50,518) — exclude
      UPPER(STATUS) IN (ARCHIVED 975, CANCELLED 335, POSTPONED 54, DELETED 3;
      'discarded' is not a stored value): 972 DCM deals disappear, 264 shrink,
      46,071 untouched. ECM deal level: add Postponed (12) to the existing
      Confidential/Withdrawn/Terminated exclusion. ORDERS: ECM already right
      (NEW/UPDATED/REINSTATED stay; DELETED/CANCELLED/PASS go). DCM: exclude
      DELETED 28,871 + CANCELLED 4,137 + the 10,966 orders on excluded tranches;
      BLOCKED on the workflow codes (XB 1.9M, B 1.6M, NEW, UPDATED, NULL 120k,
      D 96k, R, FR, PN, A, F, XR) — D may be deleted, XB/XR may be cancelled;
      db-asks L + a feed-owner question decide. Build: NULL-safe UPPER() filter
      inside the deduped ODT block (deal/tranche/order views); order filter in
      the order view AND the deal view's OC block (+ NOT EXISTS vs excluded
      tranches); deploy-check B/C/D snapshot before/after + "excluded statuses
      present = 0" row; doctrine: widen "excluded by construction", retire the
      row-exclusion note, flip QA 28. PO: confirm Postponed.
- [ ] vw_tranche_summary: ORDER_COUNT / INVESTOR_COUNT roll-ups (additive), so
      tranche-level rankings can filter bookless shells like the deal object.
      (UAT 2026-09-17: 19,804 of 21,009 ECM Citi-solo tranches in 2024 sit on
      bookless deals — nothing at tranche grain can say so today.)
- [ ] Rename vw_trade_syndicate → vw_trade_designation (before whitelist; it
      is per-dealer designation amounts; source EMPTY today).
- [ ] DCM FROM/TO_ACCOUNT_* ferry onto the trade view (offered, undecided).
- [ ] Tranche-family coverage census for a planned release: OB_TRANCHE_PRICING
      (15 cols), _CALL_SCHEDULE (16), _GUARANTOR (+_RATING), _SELLING_RESTRICTION
      (9), _COMPARABLE_SECURITY (22), _REFERENCE (27), _ISSUER (16),
      _HEDGE_SECURITY (22), _DOCUMENT, _COMMENT; ~170 unprojected
      OB_DEAL_TRANCHE columns. Census against the prompt corpus first.
- [ ] IOI rebuild: UAT confirm PASSED 2026-09-17 (SHARES 3,694/3,694, BOND
      267/267; 48/48 multi-point curves match MAX; coverage 8.9 % → 72.3 %).
      Remaining: desk sign-off that ECM deal totals cover the share-denominated
      book only, disclosed.
- [ ] Upstream data-team ticket (not ours): ECM deal region is a source gap —
      5% of ECM transactions carry a region on any base-transaction version.

## 4. NEW ENHANCEMENTS — PO UAT DCM feedback, batch 2026-09-15 ("don't re-ask")
Standard matrix (reqs 1-7), constraint columns (C/E1), TC1-TC4, E2-E7 are all
implemented (config + views). Only what is still open is listed.
| Jira | Item | Status |
|---|---|---|
| C176173F-35768 | Fidelity matrix (columns / sort / zero rows kept) | config DONE; QA 15 lacks issuer + tenors columns → §1 |
| C176173F-35774 | constraint columns echoed (USD, 12 months, pricing date desc) | config DONE; verify on prompt 19 |
| C176173F-35781 | Citi solo deals, all Citi entities | view DONE, verified UAT (14,250 vs 4,025 all-time); tell PO the deal priced 18-Sep, not 14-Sep |
| C176173F-35773 | top 5 investors in txn 75043505, per tranche | FAILED UAT 2026-09-17 on the latest config (flat Investor · GP Id · Product · Demand). ROOT CAUSE ours: doctrine named non-existent fields (investor_gp_id, pricing_ts → investor_id, pricing_date) and the SKILL row prescribed the aggregate shape. Fixed + [names] gate; RETEST on txn 75076736 after the next push |
| C176173F-35776 | CUSIP 63307A3T0 geography split | E2 DONE (three tranches is real: two UAT test entries + the NACN book); E5 CLOSED 2026-09-17 — UAT split reconciles to the 26.75M book, no unrecorded-region bucket |
| C176173F-35777 | top 5 by allocation across all IG deals 2024 | view (product_class ferried) + config DONE; QA 22 PASS |
| C176173F-35783 | allowed order types per tranche | view + config DONE (Y/N flags; txn 75043505 = Y/Y/N both tranches); verify prompt 25 |
| TC2 | "Did BlueFin trading indicate…" | SKILL routing fixed 2026-09-16; BlueFin absent from QA → retest on UAT |
| TC3 / TC4 | Travelers by name; 5-year tranche demand | product recipe fixed 2026-09-17; tenors ferried → rerun 18 |
| PROD ticket | Limit returned as Demand / Indication | AC1-AC2 fixed in views + ontology (not in PROD); AC3 SKILL rule shippable now; AC6 QA sign-off = prompts 2 + 24 + deploy-check rows 21/21b |

MRM: DCM 85 % (minimum 80 %), ECM 94 %; the PO holds the DCM submission until
our push lands — coordinate timing (a mid-cycle change invalidates the sample).

## 5. Tests (tests/ + gate edits) — none of the 12 recent failure classes had a pre-deploy catch
- [ ] RT-5 remainder: extend the [names] scan to yaml how_to_use/usage_notes prose and validate routed rows against THAT object's keys (the slot-aware metric-in-dimensions half shipped 2026-09-17)
- [ ] Server tests that pin new behaviour before it ships: tests/test_suggestion_budget.py, stub-connector timeout test, single-entitlement-call test, discovery pruning trio, XL-4 planner cases, importorskip FastMCP client test (each named in §2) — SRV-1/2/5/6, CAT-3, XL-4
- [ ] SKILL-6 leading-token check; CAT-2 no-provenance check; XL-*/CAT-4 negative pins — phrase-named failures (gate)

## 6. Where the rest lives
- Asks to other teams: ASKS-external.md
- PROD-side items, promotion order: PROMOTE-CHECKLIST.md
- SQL checks for the user (open + standing): views/_checks/db-asks.sql
- Prompts + run results: QA-PROMPTS.md
- The analysis report itself (byte budgets, pin lists, per-item proofs):
  scratchpad analysis-2026-09-17.md (ephemeral) — conclusions in memory.
- Closed history: git log of the retired files (audit-backlog-2026-08-11.md,
  uat-dcm-feedback-2026-09-15.md, uat-issues-2026-09-02.md,
  prod-issues-2026-08-21.md, dcm-issues-2026-08-24.md,
  token-review-2026-09-04.md, index-review-2026-09-02.md, SERVER-CONTRACT.md,
  mrm-*.md, views/_docs/_*.md, views/_checks/_*.sql).
