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
- [ ] PO units — CLOSED 2026-09-21 (PO table: Common stocks / Equity Units /
      Warrants = Shares; Convertible Bond / Convertible Preferred / Exchangeable
      Notes = Bonds). In config: row unit = demand_unit, PO mapping as the
      fallback and for deal size (par for the bonds group). Retest QA 33/34/35.
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
- [ ] DONE (in repo 2026-09-24, undeployed) SRV-7 product narrowing: a both-
      products scope + a single-product field (equity_type, offering_type,
      investor_category_key, tenors…) is scoped to that product in the planner
      (product filter rewritten to eq; plan.narrowed_product / narrowed_by) and
      the response carries `product_note`; explicit single-product scopes and
      ECM-only + DCM-only mixes still raise product_not_applicable. Closes the
      class-2 retry loop (UAT run 5 prompt 37: 5 queries → 1). Tests: four cases
      in test_planner_contract.py; gate [product] pins. Verify on the next
      server push with prompt 37 (expect ONE run_bqs_query).
- [ ] RELEASE EVIDENCE (UAT run 5, 2026-09-24, prompt 41 'Fees on the Visa
      IPO'): the DEPLOYED tranche catalog (09-18 build) still declares 'fees /
      gross spread / underwriting fee' an unsupported intent, so our agent ran
      six queries, gave up, and the ROOT agent handed the question to
      enterprise_web_search (answer from the 2008 prospectus — right numbers,
      wrong source; our tranche row holds the same 1.232). The repo's
      rewritten pricing_economics intent (2026-09-24) is the fix and needs the
      server push; until then the promoted SKILL says fees exist and the server
      says they do not — the SKILL/yaml split the 2026-09-17 analysis warned
      about. Ask the platform whether a data sub-agent's 'not available' should
      ever route to web search (MRM: an answer sourced outside the governed
      data, presented as the agent's).
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
- [ ] CAT-7 DONE in repo 2026-09-24 (release train): deal.yaml issuer_name now
      'ECM PARTIAL — party master, then orderbook issuer by GFCID; blank = not
      recorded; the deal name usually carries the company'; entity.yaml's three
      V14 / 'order carries NO issuer_name' passages rewritten.
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
- [ ] SIZE_UNIT on the deal/tranche ECM branches (PO mapping 2026-09-21):
      CASE equity_type — Common Stock / Equity Units / Warrants / ADR / GDR /
      Equity / IPO / NULL → 'shares'; Convertible Bonds / Convertible Preferred /
      Exchangable Notes → 'bonds' (deal size = par); DCM = 'currency'. Also a
      DEMAND_UNIT fallback on the order view where the stored unit is NULL.
      Additive; rides the Ipreo batch if the census allows, else the next.
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
- [ ] IPREO — SECOND ECM SOURCE: BUILT 2026-09-21 (third UNION ALL branch,
      PRODUCT 'ECM', in vw_deal_summary 164-275 / vw_order_detail 177-330 /
      vw_tranche_summary 219-389; view-notes addendum 9; deploy-check rows
      22/23/24 + K8/K9; contract test 3-branch aware; tranche price +
      settlement_ts widened to both products; investor_region notes ISO-3).
      VERIFIED ON QA 2026-09-24 (all four Visa cards after the final redeploy:
      whole-share conversions, per-share fees, Citigroup (CITIUSA), offer-date
      pricing). Remaining: handover to the view team with the index/stats ask,
      agent run 5 (QA-PROMPTS 37-41), and the ASKS-external questions. History:
      DEPLOYED TO QA 2026-09-22 (names compiled → N3 closed). Smoke N4: deal
      19,583 / tranche 19,973 / order 658,680 Ipreo rows; grain holds on both
      products (deal ECM 39,165, DCM 21,190; order ECM 728,793, DCM 5,826,467);
      enrichment landed (tranche name 100 %, region 60 %, type 49 %, demand
      77 %, billed-by 5 %, currency 11 %); exclusion leak 0; entity search shows
      Ipreo issuers as id-less rows; party master / base txn know 0 Ipreo ids
      (NULL stubs final). Deal cards (N5-1, 61 s): Visa 1447528575 (406M shares,
      2,425 orders, 8.6x), Kraft Foods 1447488812, Qualtrics 1447834357 — real
      historical IPOs, every column filled EXCEPT LAST_PRICED (NULL on all
      three). N6 (same day) measured the source: mirror tranche PRICING_TS is
      0 of 19,973 (SETTLEMENT_TS 10,173, TRADE_DATE 10,536, selling fee
      10,464); IPREO_ISSUE PRICING_DT only 556 of 19,583 (2017–2025), OFFER_DT
      10,253, SETTLEMENT_DT 10,030 → FIXED IN REPO 2026-09-22 (round 2):
      FIRST/LAST_PRICED and tranche/order PRICING_TS = NVL chain PRICING_TS →
      PRICING_DT → OFFER_DT → TRADE_DATE (~55 % of Ipreo deals dated; the rest
      stay undated — disclose); SETTLEMENT_TS falls back to SETTLEMENT_DT;
      deploy-check 22c FAILs if Ipreo deals have no LAST_PRICED. Also round 2:
      Visa's currency orders show IOI_QTY = money / 44.00 (the offer price) →
      already a share-equivalent, so ORDER_DEMAND_QTY / TOTAL_DEMAND now
      include IOI_UNIT 'CURRENCY' and DEMAND_AS_SUBMITTED takes the raw money
      amount (IPREO_ORDERIOI.IOI_AMT, correlated scalar on ORD_ID) — N7-2
      confirms (N7-2a errored on my IOI_AMT_TYPE guess; N8-1 re-asks without
      it). ROUND 3 (N7, 2026-09-22): ALLOCATION RESOLVED — PRIVATE_ALLOC in the
      mirror = the raw IPREO_ORDER.INST_ALLOC_QTY = INST_ALLOC_SIZE (all three
      sum to 1,009,616,809 on Visa; INST_ALLOCATION_QTY / retention are NULL
      throughout), i.e. the view carries the source's own figure; Visa (2.5x
      the deal, eight accounts at exactly 19,000,000) is a source anomaly —
      Qualtrics 1.11x and Kraft 0.72x are plausible; N8-4 counts how many
      deals are Visa-like, for the data owner. FEES WIRED (repo): N7-5 proved
      IPREO_TRANCHE.DEFAULT_PRD_ID (22,159 / 22,159 filled, 12,266 map to
      exactly one IPREO_PRODUCTFEE row, none to several) → TOTAL_FEE ←
      NVL(GROSS_SPREAD_AMT, UW + MGMT + SELL), UNDERWRITING_FEE, MANAGEMENT_FEES,
      SELLING_CONCESSION_FEE ← NVL(mirror, PF); PRICE ← NVL(FINAL_PRICE,
      IPREO_PRODUCT.OFFER_PX by PRD_ID); deal BASE_PRICE ← NVL(FINAL_PRICE,
      OFFER_PX by ISS_ID); deploy-check 23c. Unit: PER SHARE (Visa's mirror
      SELLING_CONCESSION_FEE 0.5544 on a 44.00 price = the real 45 % of the
      1.232 spread) — the OPUS columns carry the same mirror-mapped semantics;
      the catalog's old "deal fee = SUM this per deal" was fixed 2026-09-24
      (CAT item). IOI_UNIT vocabulary: SHARES 614,082 · CURRENCY 41,418 ·
      PERCENT 12,313 · FACE 1,669 (no BOND — convertibles indicate in FACE);
      N8-1 samples PERCENT / FACE to decide whether IOI_QTY is a share-
      equivalent there too. SYNDICATE MEMBERS ON IPREO ARE BROKER CODES
      (ABNROTH | BARCAP | CITIUSA | … 35 on Visa) → the Citi SOLO regex misses
      CITIUSA; N8-3 censuses the CITI* codes and roles, then the Ipreo DST
      block gets a code list. TRANCHE_SIZE on Visa = 446,600,000 = deal
      406,000,000 + shoe 40,600,000 (ACTIVE size includes the over-allotment;
      N8-2 tests the rule before subtracting). Tranche names are market labels
      on BOTH sources ('UNITED STATES' on OPUS 25255410 too). TIMINGS (QA):
      Visa order card 38.6 s vs OPUS 25255410 order card 30.1 s → the Ipreo
      branch adds ~8.5 s; the OPUS ECM order branch itself costs 30 s (PCM /
      OBT / currency windows — the V1/V2 latency items + ICEBERG-PLAN Phase 0
      are the fix, not an Ipreo rewrite); Visa tranche card 47.4 s (OPUS
      tranche card not in the set); ECM deal listing 61 s. Redeploy the three
      files, then deploy-check B/C/D (22c, 23c, 24) and N8. Not re-asking for
      the Trino row — PROMOTE-CHECKLIST step 2 (S3) covers it. ROUND 4 (N8,
      2026-09-22): CURRENCY confirmed (mirror IOI_QTY = raw IOI_AMT / OFFER_PX:
      34,000,000 / 25 = 1,360,000) and FACE too (face / par = bond count:
      50,000,000 / 1,000 = 50,000 on a 750,000-bond convertible) → FACE added
      to the demand gate and to the raw-amount "as submitted" (repo); PERCENT
      still unknown (N9-1). Tranche size: ACTIVE = DEAL on 5,711, ACTIVE −
      SHOE = DEAL on 4,293, other 563 — the shoe is included when exercised;
      base-size column hunt in N9-2 before changing TRANCHE_SIZE. Citi codes
      censused: CITIUSA 6,199 · CITIUS1 119 · CITIUKE 66 · CITIBRAS 53 ·
      CITICAN 45 · CITIASIA 25 · CITIAUS 7 · CITI1 5 · CITISEC 3 · CITIINVS 2 ·
      CITI3 1; NOT Citi: CITIZENS 77, CITICCML 5 → Ipreo branch (repo): member
      token 'Citigroup (CODE)' for ^CITI minus ^(CITIZ|CITICC), same test in
      the SOLO block (the OPUS regex then matches the label unchanged);
      SSBINC / SBS / MSSB (Salomon Smith Barney era) = PO question (ASKS §4).
      Role vocabulary (28): Co-Manager 26,814 · Underwriter 12,095 · Joint
      Bookrunner 12,074 · Selling Group 10,500 · Lead Manager/Bookrunner 6,240
      · Joint Bookrunner - Passive 2,867 · Passive Bookrunner 2,504 · Joint
      Lead Manager 1,375 · Senior Co-Manager 851 · … · Sole Bookrunner 136
      (catalog syndicate_role note). Allocation census: 94 of 5,462 deals
      > 1.2x size, 4,386 plausible, 982 < 0.5x → data-owner ask (ASKS §5);
      the column stays. ROUND 5 (N9, 2026-09-22): PERCENT indications carry
      IOI_QTY = 0 and nothing raw → stay out of the gate; Ipreo demand /
      as-submitted now NULLIF 0 (a zero indication is "not recorded"). The
      base tranche size column is TRN_UW_SIZE_QTY (underwritten; Visa
      406,000,000 vs ACTIVE 446,600,000 — the OCR misread was TRN_UN) →
      TRANCHE_SIZE = NVL(TRN_UW_SIZE_QTY, ACTIVE) (repo). Visa's raw tranche:
      TRN_NM_CD 'USA' (a tranche_region candidate), TRN_OWNER_NM 'Citigroup
      Virtual Subsidiary' (the feed is Citi's own Ipreo book view),
      OVERALLOTMENT_QTY 40,600,000. Anomalies (N9-3 top ten): CONVERTIBLES are
      allocated in FACE MONEY while size + demand are in bonds (Liberty
      Interactive 675,000 / 750,000,000; Pluralsight 550,000 / 633,500,000;
      Vonage 300,000 / 345,000,000 ≈ size × 1,000 par × 1.15) — if every
      convertible did this the view would divide by par — CENSUSED: it does
      not (Convertible Bonds 587 of 645 within 1.2x, 4 above 500x; Pluralsight
      stores face money under a SHARES unit) → no rule, anomalies to the data
      owner; ADR/GDR-style
      deals (Telmex 415x, NTT 182x, Telecom Italia 104x, Beijing Yanhua
      53x, Petrobras 4-5x) look allocated in a different unit than the size
      → data-owner list (ASKS §5). The user asked to stop pre-deploy asks
      (2026-09-22): from here, checks run AFTER a deploy only. PRE-DEPLOY REVIEW 2026-09-22 (four lenses): no CREATE or wrong-data
      defect; Citi code test tightened to a positive list (a CITIC* code
      could have passed the exclusion form); as-submitted NULLIF 0 on the
      raw-amount arm; docs corrected (10,802 drop cause; UW/MGMT fees are
      fee-table only). Optional later: RI LEFT JOIN instead of the scalar;
      RT joined on O.TRANCHE_ID directly. QA 2026-09-23: ORA-04036 on every
      view query (single-deal too) while base-table sorts ran → the wide
      SELECT ET.* transaction dedupe keyed only by ECM_TRANSACTION_ID was the
      hog → rewritten (repo, gate 1702/0): explicit columns + PARTITION BY
      DEAL_TRANSACTION_ID, ECM_TRANSACTION_ID on all six ECM T blocks.
      Redeploy, then db-asks N12 (guard + Visa cards). Also worth doing when
      the next batch opens: EO.* / TTR.* dedupes narrowed the same way
      (order 70k/677k rows, tranche 50k/20k). (2) Dropped:
      the RO direct-join idea (V7) — worth ≤ 8 s on a 30 s base; Iceberg
      instead. (3) Handover + index/stats ask
      (ASKS-external §2). (4) Enrichment now proven at source (QA): fees on
      11,956 of 19,583 issues (IPREO_PRODUCTFEE: selling concession 11,095, UW
      9,544, mgmt 9,468, gross spread 259 — but N5-4 shows GROSS_SPREAD_AMT
      filled on every sampled row, so the 259 is a COUNT artefact to re-check);
      UNIT SETTLED by N5-4: PER SHARE / PER BOND in the offer currency, and
      GROSS_SPREAD_AMT = U_W + MGMT + SELLING_CONC exactly (Alkami 27.5 = 5.5 +
      5.5 + 16.5 on a 1,000 bond = 2.75 %; KKR 1.125 on 50.00 = 2.25 %; ADT
      0.08 on 7.70; Rithm 0.20 on 10.00 = 2 %; the classic 20/20/60 split) →
      map TOTAL_FEE ← GROSS_SPREAD_AMT, UNDERWRITING_FEE ← U_W_FEE_AMT,
      MANAGEMENT_FEES ← MGMT_FEE_AMT, SELLING_CONCESSION_FEE ← SELLING_CONC_FEE_AMT,
      GROSS_SPREAD_PER_FEE ← ROUND(100 * GROSS_SPREAD_AMT / OFFER_PX, 4), keyed
      IPREO_TRANCHE.DEFAULT_PRD_ID = PRD_ID — ONLY after N6-6 shows the OPUS
      columns are per-share too (if OPUS is total money the columns cannot be
      shared; the catalog now scopes per-share to 10-digit-id ECM deals). Also from N5-4:
      IPREO_ISSUE.ISSUE_SIZE_AMT is the MONEY size (300,000,000 on 300k bonds ×
      1,000; 1.5bn on 30M × 50) → DEAL_SIZE_MM candidate with DEAL_SIZE_CURRENCY
      = CCY_CD (mostly NULL — disclose, never assume USD); OFFER_PX (11,206 of
      22,194 products) → PRICE / BASE_PRICE fallback when FINAL_PRICE is NULL;
      PAR_VALUE 13,539 (1,000 / 50 / 0) confirms the convertible-vs-share unit
      split. File price / range ~0 → reoffer stays NULL. (5) Catalog + SKILL DONE in repo 2026-09-24 (catalogs ride the train,
      SKILL ships freely; gate 1702/0; QA-PROMPTS 37-41 added for run 5):
      investor_category gains the Ipreo vocabulary (Hedge Fund 187k,
      Investment Adviser 81k, None 39k = unclassified, Bank & Trusts, Pension
      Fund, Research Firm, Corporation, Private Equity, Insurance Company,
      Venture Capital; NULL 50 %) — "long only" asks on ECM must consider
      Investment Adviser; currency on Ipreo rows is ~11 % filled (source
      ISSUE.CCY_CD / PRD_CCY_CD both ~2–3 %) → a currency filter silently
      drops Ipreo deals, disclose; tranche status on Ipreo = NULL / 'new' only
      (stays NULL). Disclose: 10,802 Ipreo orders are dropped because their deal has no
      surviving mirror transaction row (tranche-less orders are KEPT with
      NULL tranche attributes — review 2026-09-22 corrected the earlier
      'inner join on the tranche' wording).
- [ ] ECM ISSUER_NAME blank in PROD (first PROD datapoint 2026-09-21: five real
      2026 IPOs, deal name filled, issuer '—'; the same prompt on IST fills).
      NOT a regression — the OPUS ECM expression NVL(PCM.PARTY_NAME,
      NVL(OIN.ISSUER_NAME_BY_GFCID, T.ISSUER_NAME_FROM_SOURCE)) is byte-identical
      from the 08-21 freeze to HEAD in all three views (only 78b3c4c..c8e002f,
      never deployed, dropped PCM); the source column is dead, so a name exists
      only if the party master has a named Primary Client row or OB_DEAL_ISSUER
      knows T.ISSUER_GFCID. Two view edits for the next batch, both gate-tested
      on a copy (1702/0, 118 tests): (a) join OIN on NVL(PCM.PARTY_GFCID,
      T.ISSUER_GFCID) — today the projected GFCID can come from the party master
      while the name lookup never uses it (UAT party master = GFCIDs with NULL
      names); (b) last-resort fallback to SYNDICATE_DEAL_NAME with the Ipreo
      '(… Tranche)' strip — ECM deal names are issuer names (the five PROD rows,
      the Ipreo sample); UAT tester names would leak only where all three real
      tiers are empty. Entity view: name-only issuers become id-less rows
      (already a known class, entity_id is_not_null). Before building: PROD
      A0 + row 1e + the party-master count (PROMOTE-CHECKLIST PROD-side).
- [ ] STATUS EXCLUSION (Vinit 2026-09-21) — censused UAT (db-asks K, closed):
      TRANCHES: DCM only (ECM tranche status is NULL on 50,510/50,518) — exclude
      UPPER(STATUS) IN (ARCHIVED 975, CANCELLED 335, POSTPONED 54, DELETED 3;
      'discarded' is not a stored value): 972 DCM deals disappear, 264 shrink,
      46,071 untouched. ECM deal level: add Postponed (12) to the existing
      Confidential/Withdrawn/Terminated exclusion. ORDERS: ECM already right
      (NEW/UPDATED/REINSTATED stay; DELETED/CANCELLED/PASS go). DCM: exclude
      DELETED 28,871 + CANCELLED 4,137 + the 10,966 orders on excluded tranches;
      BLOCKED on the workflow codes: db-asks L (2026-09-21) shows they are ONE
      legacy load — SOURCE_SYSTEM 'RQ', published 10-11 Jan 2022, 3.75M orders
      (75 % of the DCM book); B 1.62M / 1.24M allocated (booked?), XB 1.90M /
      130 allocated (cancelled?), D 96k / 0 (deleted?), NULL 120k / no size;
      live ONEBOOK rows use plain words. Vinit decides the RQ mapping
      (ASKS-external §6). Build: NULL-safe UPPER() filter
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
- [ ] Contract test: assert per-branch that every NULL stub's CAST type equals the type the other branches project for that alias (the Ipreo branch copied the DCM stub types by hand — a mismatch is ORA-01790 at deploy, invisible today)

## 6. Where the rest lives
- The Iceberg migration plan (tabled 2026-09-22): ICEBERG-PLAN.md — after
  Phase 1, every §3 view item becomes core/serve SQL there, not an Oracle handover
- Asks to other teams: ASKS-external.md
- PROD-side items, promotion order: PROMOTE-CHECKLIST.md
- SQL checks for the user (OPEN asks only): views/_checks/db-asks.sql — standing
  scripts S1-S4 live in git history (2026-09-21) and PROMOTE-CHECKLIST.md
- Prompts + run results: QA-PROMPTS.md
- The analysis report itself (byte budgets, pin lists, per-item proofs):
  scratchpad analysis-2026-09-17.md (ephemeral) — conclusions in memory.
- Closed history: git log of the retired files (audit-backlog-2026-08-11.md,
  uat-dcm-feedback-2026-09-15.md, uat-issues-2026-09-02.md,
  prod-issues-2026-08-21.md, dcm-issues-2026-08-24.md,
  token-review-2026-09-04.md, index-review-2026-09-02.md, SERVER-CONTRACT.md,
  mrm-*.md, views/_docs/_*.md, views/_checks/_*.sql).
