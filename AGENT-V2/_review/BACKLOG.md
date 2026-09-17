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
PROD item is an ask.

## 1. Config (SKILL / agents.yaml / ontology yamls) — ships freely; PROD freeze = SKILL + agents.yaml only
- [ ] UAT reruns (user runs UAT ONLY from 2026-09-17; local ADK pointed at UAT) after a restart — skills load at startup: 18
      Travelers, 2 largest IPOs, 16 on the two-tranche txn 75043505 (capture
      the ⚡ args), then 24 and 15. Proof the new SKILL is live: the ✓
      load_skill text contains "Extra figures come from ROW-LEVEL columns".
- [ ] 16 / TC1: confirm the top-N is PER TRANCHE (partition_by) from the ⚡ args.
- [ ] 15 matrix: issuer_name + tenors columns missing from the Fidelity answer
      although the ORDERBOOK MATRIX note lists them — check it is applied.
- [ ] Per-tranche listings must carry tranche_name ("three indications" for
      Amundi were three tranches, unlabelled).
- [ ] E9: "hedge orders for deal 75043505" → zero — was the txn id sent as
      deal_id? Needs the ⚡ args. If so: an 8-digit id on DCM is a
      transaction_id (DCM deal ids are 'I-…' strings), whatever word was used.
- [ ] Placeholder-table behaviour (agent narrates a query it never ran, then
      emits '...' rows) — budget-exhaustion doctrine; watch in QA.
- [ ] Company-profile hallucination on unsupported asks — routing, open.
- [ ] COMPRESSION Phase 1 (after the QA list is done; measure 6 prompts
      before/after): SKILL 92k chars → ≤45k (object doctrine → the owning
      yaml; SKILL keeps routing, iron rules, budget, presentation, traps,
      cross-object rules); catalogs tranche 16k → ≤8k tokens, order/deal ~12k
      → ≤7k (telegraphic descriptions, boilerplate once per object, keep value
      lists); agents.yaml routing ~5k → ~2k tokens. Gate pins move with the
      text. Evidence: rule dilution (E8 pinned no-unit-parenthetical rule
      ignored 2/2 with V3 live; metric-in-dimensions 8 slips in two days);
      a two-catalog ask costs 2.7x a one-catalog ask (354k vs 133k session).
- [ ] PROD, under the freeze: ship the SKILL-only "LIMIT IS NOT DEMAND" rule
      now; the value half needs the view release (IOI rebuild).

## 2. Server (release train) — DONE = in repo, undeployed; TODO = not written
- [ ] DONE metric-slot explainer: `_explain_cross_object` checks the requesting
      object's metrics first (E10; tests in tests/test_cross_object_error.py).
- [ ] DONE config.py default BQS_ENABLED_SOURCES = nine sources.
- [ ] TODO MCP result de-dup: mcpserver.py dict-return tools emit BOTH
      content[0].text (full JSON) and structuredContent — ~25% of every call,
      doubles every catalog fetch. Return one form. Faster path = ADK
      before_model callback (ASKS-external.md §1).
- [ ] TODO sql_audit flag ECM_DCM_SQL_AUDIT=summary|full|off, default summary;
      cap suggestion/disambiguation block sizes.
- [ ] TODO execution timeout < 300 s (e.g. 240 s, Trino session property or
      driver) so heavy queries fail fast; never raise the 300 s client timeout.
- [ ] TODO zero-row enrich probes: skip or budget them once execute has
      exceeded a threshold (they re-query slow views for nothing).
- [ ] TODO unmask fetch errors — surface the DB error text.
- [ ] TODO DENSE_RANK for partition_by top-N (ties at the boundary).
- [ ] TODO result cache — spec in cache-design.md; build on "build it".
      Today every "next N" re-runs the same 62 s query.
- [ ] TODO units guard, defence in depth: per-metric requires_single_value
      [product] — the entitlement gate replaces the agent's product filter
      with `in [ECM, DCM]`, so requires_filters can never fire.
- [ ] TODO bad_having_grain guard: reject `having` on a COUNT-DISTINCT metric
      whose column is also in dimensions (0 rows by construction).
- [ ] TODO tool schema: the `dimensions` parameter description says
      "attribute names only — a total_*/largest_*/*_count name is a metric,
      put it in `metric`". Schemas are seen every turn; cheaper than SKILL prose.

## 3. Views (next planned batch — approval-gated; files handed verbatim, comment-free)
- [ ] vw_order_detail: transaction_id pushdown — join ORIGINATION_TRANSACTION_ID
      INSIDE the DCM dedupe subquery and add it to the PARTITION BY
      (functionally dependent on ROOT_ID → identical partitions). Txn-scoped
      order asks run 19-29 s vs 2-6 s deal-scoped. Tranche view too if slow.
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

## 5. Where the rest lives
- Asks to other teams: ASKS-external.md
- PROD-side items, promotion order: PROMOTE-CHECKLIST.md
- SQL checks for the user (open + standing): views/_checks/db-asks.sql
- Prompts + run results: QA-PROMPTS.md
- Closed history: git log of the retired files (audit-backlog-2026-08-11.md,
  uat-dcm-feedback-2026-09-15.md, uat-issues-2026-09-02.md,
  prod-issues-2026-08-21.md, dcm-issues-2026-08-24.md,
  token-review-2026-09-04.md, index-review-2026-09-02.md, SERVER-CONTRACT.md,
  mrm-*.md, views/_docs/_*.md, views/_checks/_*.sql).
