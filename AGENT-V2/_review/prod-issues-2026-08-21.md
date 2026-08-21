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

### #3 update — retry ran 40 queries, aborted
The first fix's recipe ferried ids from the WRONG side: "all convertible
2025 deals" is the huge population (paged R1, then ≤40-id R2 batches = an
open-ended loop; 40 calls before the user aborted). Recipe REWRITTEN with
two iron rules, both gate-pinned:
(1) ferry from the SMALLER side — R1 = BlackRock's own per-deal
    allocations (order object, one page), R2 = deal object confirms which
    of THOSE ids are convertible; the total is model arithmetic over rows
    already held, no third query;
(2) HARD BUDGET — max 4 run_bqs_query calls per ask; over budget = give
    the closest supported aggregate + state the precision limit, never a
    loop.
Re-test the same prompt after the next skill deploy.

## #4 — Superlative mass-tie (anticipated by user, not a trace)
- **Scenario:** "max allocated investor" on a deal where ALL 100 orders
  carry the same allocation. limit-3 shows 3 tied rows; the agent cannot
  distinguish "3 tie" from "100 tie", and the old escalation ended in
  "name them all" — absurd at 100.
- **Fix (SKILL superlative block, gate-pinned):** all-3-tie triggers ONE
  having-eq follow-up, then the answer follows the TIE COUNT: ≤5 named as
  co-winners; more → the finding flips to uniformity ("38 investors share
  the maximum allocation — no single top investor"), 2-3 names labelled
  as examples, "at least 50" if truncated, pattern stated without invented
  cause.
- **Status:** doctrine in SKILL 2026-08-21, ships with the next deploy.

## #5 — Deal currencies list is alphabetical, not pricing order
- **Symptom:** deal shows "CAD | USD" though the USD tranche priced first;
  the banker reading is lead-currency-first ("USD | CAD").
- **Root cause:** the deal view's LISTAGG orders WITHIN GROUP BY currency
  (alphabetical) — pricing chronology never enters the join. Frozen.
- **Fix now (SKILL, gate-pinned):** (a) never infer lead/first currency
  from list position, never caption the list "in pricing order"; (b) for a
  SINGLE-deal currency ask, one tranche-object query (currency +
  pricing_ts, asc) recovers the true order — present "USD, CAD (in
  pricing order)"; (c) multi-deal listings keep the stored list with no
  ordering claim.
- **Release train:** re-order the LISTAGG by each currency's first
  pricing date (WITHIN GROUP ORDER BY MIN(PRICING_TS) per currency, both
  products) so the stored string reads lead-first.
- **Status:** doctrine in SKILL 2026-08-21; view fix queued.

## #6 — Away orders excluded (IS_OWNED) → RELEASE 2 OPENED
User directive: include IS_OWNED='false' (away orders) and expose the
distinction. This opened the release-2 view batch, which ALSO carries the
queued items: equity_type on the order view (#3), currency global
fallback on tranche/order (#2), CURRENCIES in pricing order (#5), and
away-inclusive deal-card counts. Staged in the four view files
(comment-free; documented in views/_docs/view-notes.md RELEASE 2
section). Config flips staged in _review/release2-config-staged.md —
apply ONLY post-deploy. Sizing queries: _checks/_order-ownership-check
.sql (run in PROD before deploy). Deploy-check rows 1i/1j added. Gate
gained the UNION branch-alignment check (parsed alias sequences; would
have caught any column-order slip in this batch).

### #6 update — sizing measured (O1-O3, 2026-08-21)
Away inclusion adds 21,836 ECM rows to today's 48,102 (~+45% — every ECM
total moves; release review has the number). O2=0: no multi-dominant
fan-out, dedupe safe. KEY FINDING: 58 matched orders whose dominant row
is AWAY are completely invisible under release 1 — the old filter didn't
just narrow scope, it LOST orders; release 2 restores them. O3: DCM
OB_ORDER has OWNER/ALL_OWNERS (semantics unknown, likely member lists) —
DCM stays NULL; census before mapping. 38 NULL-IS_MATCHED rows fall
through the guard both ways (pre-existing, tiny).
