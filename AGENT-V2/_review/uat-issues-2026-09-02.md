# UAT issues — 2026-09-02 batch (ADK screenshots)

Context that applies to all three: DEV runs the V3 **views** but still the **V2 config**
(the V3 ontology/SKILL/agents.yaml push is pending). Behaviors already fixed in V3
config are marked [retest after config push] rather than re-logged.

## U1 — ECM "indication" (total_demand) NULL for every investor (indication-issue.jpg)

Ask: top investors with allocation + indication (demand) across 5 IPOs.
`total_demand` = SUM(TRY_CAST(order_demand_qty)) over vw_order_detail returned NULL
for all 8 GP-ID investors (JPMorgan, Fidelity, BlackRock London, Loomis, Citadel,
Apollo, Liberty Mutual, Vanguard) while allocations populated normally.

Root-cause hypotheses, in blame order (our artifact first):
1. ECM branch maps ORDER_DEMAND_QTY = OB_ECM_ORDER.DEMAND_QTY (no fallback). If IPO
   pot orders carry their indication only in the IOI table (OB_ECM_ORDER_IOI.
   LIMIT_VALUE — which already feeds ORDER_AMOUNT), DEMAND_QTY is legitimately NULL
   and the VIEW is presenting the wrong source for "indication" on these deals.
2. Type garbage making TRY_CAST return null (TRANCHE_SIZE precedent).

Probes 1–2 in `views/_checks/_uat-probes-2026-09-02.sql` decide: fill-rate of
DEMAND_QTY, alloc-but-no-demand count, non-numeric count, and IOI coverage of the
null-demand orders. If (1) confirms, candidate fix is a view-level fallback
(DEMAND_QTY → IOI LIMIT_VALUE) — semantics defensible (an IOI's limit IS the stated
indication), bundled into the next view handover. Decision after probes.

Side observations, both V2-config behaviors: "(Shares)" appeared in a header, and
two no-GP-ID investors (Ghisallo, 361 Degree) were skipped instead of name-filtered
[retest after config push].

## U2 — "List all deals by The Travelers Companies, Inc." deflected (dcm-deal-name-issue.jpg)

Agent ran discover + ~5 bqs queries, then asked the user to narrow by year. Given U3's
measurements (single view queries at 29–437s), the primary suspect is **timeout, not
name matching** — the agent's "trouble retrieving all deals at once" phrasing fits
queries dying under it. Secondary suspect: legal-name punctuation ("The ... Companies,
Inc.") used verbatim as the match token instead of the distinctive token (V3 SKILL has
token guidance; V2 config was live).
Probe 3 settles what the sources actually store for Travelers; retest after config
push + latency work. Also in the same trace: CUSIP 5C7GNK9W9 not found — probe 4
checks whether it exists at all (V3 has the contains-match casing recipe; V2 did not).

## U3 — OCP log: measured query latency (long-running-query-dcm.jpg)

| Query | Timing |
|---|---|
| deal list (tranche_count > 1), 50 rows | execute 29.13s |
| entity max_activity, 1 row | execute 40.21s |
| deal_count, **0 rows** | **execute 401.20s + enrich 36.67s = total 437.87s** |

Confirmations: entitlement gate GRANTED via **cache** on repeat calls (rewrite works;
API itself 1395ms when called); CyberArk cache HIT ttl=900s (per-query CyberArk cost
is gone). So latency is now ~entirely BQS execute — the full-scan mechanics in
`index-review-2026-09-02.md`, which this log upgrades from theory to measurement.
The 36.67s enrich on a 0-row result is the scoped zero-row probes re-querying the
same slow views — server-side, release-train item (frozen), logged in backlog.

## Retest checklist (after view + config deploys)
- [ ] top-investor allocation+indication ask (U1) — demand populated, no "(Shares)", no-GP-ID investors name-filtered
- [ ] "List all deals by The Travelers Companies, Inc." (U2) — one entity hop + one list
- [ ] CUSIP lookup (U2) — contains-match with casing rule
- [ ] re-pull OCP timings for the same three query shapes (U3)
