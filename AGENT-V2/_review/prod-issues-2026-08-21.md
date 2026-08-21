# PROD issue log — post-freeze QA round (started 2026-08-21)

MCP + views are FROZEN in PROD; every fix in this round must land in
SKILL.md or agents.yaml only. One entry per issue: trace, root cause, fix,
status. Server/view-class causes go to the release-train register in
audit-backlog-2026-08-11.md instead.

## #1 — Pipe lists break markdown tables (currency count "presentation issue")
- **Trace:** "List all the multi-currency deals in the year 2024" — the
  request was RIGHT (currency_count metric, HAVING > 1, ordered desc,
  limit 50, honest "top 50" caption). The TABLE was wrong: `currencies`
  values ("AUD | CAD") were written verbatim into markdown cells, and a
  raw "|" is a markdown COLUMN SEPARATOR — "CAD | EUR" split into two
  cells and pushed the Currency Count value off the row.
- **Root cause:** presentation only — markdown injection by the stored
  separator; the old "one cell, never split" rule didn't cover the
  markdown mechanics.
- **Fix (SKILL §8, gate pin [present]):** pipe lists never render verbatim
  in a table cell; the " | " separator is rewritten to ", " in every cell.
  Pipes only ever appear in non-table prose.
- **Status:** FIXED in SKILL 2026-08-21 — ships with the next agent/skill
  deploy. Re-test the same prompt after it.

## #2 — Deal shows piped currencies, tranches show NULL (grain asymmetry)
- **Symptom:** a deal's `currencies` lists values ("AUD | CAD") while the
  same deal's tranches carry `currency` NULL.
- **Root cause — OUR VIEW ASYMMETRY, confirmed in the shipped SQL:** the
  round-2 GLOBAL id->name currency fallback was added to
  vw_deal_summary's ECM CURRENCIES only; vw_tranche_summary.CURRENCY and
  vw_order_detail.CURRENCY are the bare per-tranche join. The underlying
  data gap (tranches without demand-currency rows) is real, but the deal
  view masks it while the tranche/order views expose it. DCM should be
  symmetric (one source column both grains).
- **Fix now (SKILL §5 currency bullet, gate pin):** NULL at tranche/order
  grain = "not recorded at this grain", never "no currency"; prefer the
  deal-level list when it has values; currency FILTERS at tranche/order
  grain disclose the NULL rows they miss.
- **Release train (audited in _checks/_currency-grain-audit.sql +
  backlog):** mirror the GC global fallback into tranche/order CURRENCY;
  G1/G2 size the symptom in PROD first.
- **Status:** doctrine FIXED in SKILL 2026-08-21; view fix QUEUED for next
  planned release.

## #3 — BlackRock × convertible bonds: answerable ask refused with a menu
- **Trace:** "How much did Blackrock invest in Convertible bonds in year
  2025" → "I cannot answer... not currently supported in a single step",
  then offered (a) BlackRock's 2025 total or (b) convertibles 2025 total —
  neither is the ask (the INTERSECTION is).
- **Root cause:** the ask is investor (order object) × equity_type (deal
  object) — cross-object. The two-step doctrine existed (deal ids → order
  filter) but was an aside, and the §3c no-joins row carried an escape
  hatch ("or say which half you can answer") the model preferred. §3d
  (never ask permission for a mechanic) was ignored.
- **Fix (SKILL, gate-pinned):** the ids two-step is MANDATORY for
  investor × class/status/size/UoP asks — worked recipe added (R1 deal ids
  by equity_type + year, R2 order total_allocation by investor + ids,
  ≤40-id batches summed, deal count disclosed, no date re-filter in R2);
  escape hatch narrowed to "R1 itself inexpressible". Also corrected the
  stale "equity/offering type" pair — offering_type is one-request since
  round 2.
- **Release train:** denormalize EQUITY_TYPE onto vw_order_detail (mirror
  of round-2 offering_type) — kills this ferry class entirely; one column,
  same deduped T join.
- **Status:** doctrine FIXED in SKILL 2026-08-21, ships next agent/skill
  deploy.
