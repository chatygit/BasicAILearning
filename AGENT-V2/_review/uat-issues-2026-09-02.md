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
queries dying under it.

**CONFIRMED (deal-search-timeout.jpg, 2026-09-02 16:06):** the ADK event log shows
`run_bqs_query` → "MCP tool execution failed: Timed out while waiting for response
to ClientRequest. Waited 300.0 seconds." So the failure layer is the ADK/MCP
**client timeout (300s)**, and it pairs with U3's server-side entry (execute 401s,
total 437s, rows=0): the client abandoned at 300s, the server kept computing ~2
more minutes for an answer nobody received. Two consequences beyond the speed work:
(a) RELEASE-TRAIN — the server must enforce a statement/execution timeout BELOW the
client's 300s (e.g. 240s via Trino session property or driver timeout in
bqs/executor) so a too-heavy query fails fast with a clean, agent-actionable error
instead of a transport timeout, and abandoned work stops burning the warehouse;
(b) do NOT raise the client timeout — 300s already exceeds banker patience; the fix
is making queries fast, not waits long. Secondary suspect: legal-name punctuation ("The ... Companies,
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

## U2 addendum (post-wave, ecs-log.jpg 20:12): Travelers ANSWERS now
deal_count rows=4 in 67.24s (execute 35.69s + enrich 31.55s). The wave killed the
timeout; remaining cost: (1) the issuer LIKE filter computes the NVL over the
unindexed RELATED_PARTIES join — index request #4; (2) UPPER(...) LIKE likely does
not push through Trino to Oracle (function predicate) — full view rows pulled and
filtered Trino-side; (3) enrich 31.55s = the disambiguation probe re-running the
expensive shape once (now warm in the probe cache).

## U4 — Trino JDBC "Rounding necessary" kills money-metric queries (NEW ROOT CAUSE)
The banker ask "top 10 investors by order size, USD, last 12 months" (chat-view/
chat-debug/ecs-log 2026-09-02 20:12-20:15) failed twice at 112-115s execute each:
`Trino JDBC "Rounding necessary" persisted even after type-aware TRY_CAST and
column isolation; returning schema with empty rows`. An Oracle NUMBER value's scale
exceeds the connector's DECIMAL mapping; TRY_CAST cannot help because the fetch
itself throws. THREE-LAYER FIX:
1. VIEWS (ours, whitelist window open): bound the scale at the source — ROUND()
   money columns in the views. Scale census probes in
   views/_checks/_scale-probes-2026-09-02.sql decide which columns and what scale
   (amounts 4dp; prices/fees 6dp; NEVER round FX_RATE).
2. SERVER (release train): NEVER mask a fetch error as an empty result — the agent
   zero-claimed and thrashed (widened 12mo→24mo on its own, re-burning 138s). Return
   a BQSError naming the failure so the agent stops cleanly.
3. CATALOG (Starburst/BDS team, optional belt+braces): oracle.number.default-scale
   + oracle.number.rounding-mode=HALF_UP on the bds_dg_oraas catalog.
Retest after fix: the exact chat ask, expect a populated top-10 in one query.

## Probe results (uat-probe.jpg, 2026-09-02 16:19)
- **U1 VERDICT — hypothesis 1 CONFIRMED, type ruled out**: ECM orders 96,462;
  DEMAND_QTY populated on only 6,212 (6.4%); 30,253 orders have allocation but no
  demand; NON_NUMERIC_DEMAND = 0. IOI covers 23,949 of the 90,250 null-demand
  orders. FIX (GO, next view wave): ORDER_DEMAND_QTY (ECM branch, vw_order_detail)
  and the deal-view OD subquery's TOTAL_DEMAND both become
  NVL(DEMAND_QTY, IOI LIMIT_VALUE) — an IOI's limit IS the stated indication;
  lifts demand coverage ~5x (6,212 → ~30,161 orders). Disclose in view-notes.
- **U2 probe 3 — name variants REAL**: six Travelers spellings in OB_DEAL_ISSUER
  alone ("THE TRAVELERS COMPANIES INC", "Travelers Cos Inc", "Travelers
  Companies", "THE TRAVELERS CO INC", "The Travelers Companies, Inc.",
  "Travelers Insurance Institutional Funding"). Verbatim legal-name LIKE cannot
  win; V3 SKILL distinctive-token rule ('%TRAVELER%') is the answer — config push.
- **Probe 4 (CUSIP 5C7GNK9W9)**: value below the screenshot fold — number still
  needed (decides only whether that CUSIP exists at all).

NEXT VIEW WAVE (single bundled handover, do NOT hand files until assembled):
U1 demand fallback + U4 ROUND scale bounds (waiting on
_scale-probes-2026-09-02.sql results).

## U4 validation (data-check.jpg, 2026-09-03) — MASK PROVEN, data exists
Oracle-direct, same filters as the failed agent ask (USD, pricing 2025-09-03 →
2026-09-04): ECM 24,554 orders / 1,988 investors / ~$26.4B; DCM 10,480 orders /
1,513 investors / 8.6E+13 total. The agent's zero-rows on this exact shape is
conclusively the masked Trino JDBC failure. True top-10 captured (data-check-2)
as the acceptance answer for the post-wave-2 retest — the agent should reproduce
it once the ROUND fix deploys.

**DEV data caveat (QA≠PROD):** the top-10 is led by obvious synthetic rows —
"JPMORGAN CHASE BANK" $50T, "APPLE COMPUTERS (BRAEBURN)" $10T, "GOOGLE",
"Tesla Motors" as investors. A $50 TRILLION order amount is test data. So in
DEV, judge the retest on MATCHING the Oracle-direct list (plumbing correctness),
never on whether the list itself looks sane — the sane list exists only in PROD.

## U4 CORRECTION (2026-09-03): failure PERSISTS after wave-2 deploy
The USD ask still fails post-ROUND (user confirmed the zero-rows trace is
post-deploy). Revised root cause: the connector maps by DECLARED TYPE, not
values — expression-defined view columns publish as unconstrained NUMBER
(no precision/scale), and ROUND() does not change the declaration. Supporting
clue: the isolation log listed total_order_amount among "safe varchar/char
columns" — the metric may reach Trino as VARCHAR (connector fallback for
unmappable NUMBER). Diagnostics issued (_type-metadata-probe-2026-09-03.sql +
a Trino-side DESCRIBE). Fix fork, pending those facts:
(a) CATALOG (preferred — zero view churn, honors the view freeze):
    oracle.number.default-scale + rounding-mode on bds_dg_oraas (BDS team);
(b) LAST-RESORT view wave: CAST money columns to NUMBER(38,4)/(38,6) so
    Oracle publishes real precision/scale — register-queued, NOT applied.
ROUND wave stays valuable regardless (bounded values are what make either
mapping safe).
