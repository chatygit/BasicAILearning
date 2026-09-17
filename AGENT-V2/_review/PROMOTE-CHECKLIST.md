# Promote checklist — Capital Markets Agent (AGENT-V2)

Two gates, then a fixed order. Nothing promotes until gate 1 is green.
We have NO PROD access: every PROD-side line is a request to an access holder,
answered by a screenshot or a written confirmation — never a task we tick.

## Gate 1 — mechanical
```bash
cd AGENT-V2 && python3 _review/ontology_check.py && python3 -m pytest tests/ -q
```
Extend the gate with every fix: a phrase pin, a structural check, or a test.
When it fails there are two honest outcomes — fix the regression, or
consciously retire the assertion in the same commit. Never delete a red check
to get green.

## Gate 2 — behaviour (fresh session per prompt, after a restart)
Run the prioritised prompts in `QA-PROMPTS.md`. Record the answer screenshot,
the session's Total Prompt Tokens, and the ⚡ run_bqs_query args on any error.
A failure becomes a gate-1 pin wherever it can be mechanised.

## Promote order
1. **Views first** — configs name columns only the new views have. Before
   the handover: `views/_checks/db-asks.sql` S1 (source-name validation —
   every statement "no rows selected" on the target environment) and any
   pre-handover asks listed there (section D on UAT). Files go over verbatim
   and comment-free; a failed Flyway script aborts every later script.
2. **After the view deploy, before any prompt** — `views/_deploy-check.sql`:
   A0 shows nine LAST_DDL_TIMEs of today; structure rows 17, 1y, 1z, 18 PASS;
   grain rows 7, 8, 9, 10b, 11b, 12b PASS; population rows 15, 15b, 20b, 21,
   21b; section K timings screenshotted. Then db-asks B through Starburst —
   the Oracle-side check cannot see a stale connector metadata cache.
   Lesson 2026-09-16: a "deployed" batch was partial; "done" is unverified
   until A0 is screenshotted.
3. **Environment** — BQS_ENABLED_SOURCES must list all nine objects
   (fail-closed; an env without it silently hides the object):
   - [ ] BQS_ENABLED_SOURCES=capital_markets_deal,capital_markets_tranche,capital_markets_order,capital_markets_entity,capital_markets_hedge,capital_markets_hedge_trade,capital_markets_trade,capital_markets_designation,capital_markets_trade_syndicate
   - [ ] Verify: discover with no source lists NINE objects.
4. **Server (MCP)** — release train only; ontology yamls ship inside it.
5. **SKILL.md + agents.yaml** — higher environments never read adk/config/*:
   the agent, skills and toolset are created in the Ask Banking onboarding UI,
   so promoting = copying the instructions into that UI by hand.
6. **Restart** — pods and the local ADK load definitions at startup;
   un-restarted runtimes are why "fixed" things appear to regress. Then gate 2.

## PROD freeze (2026-08-21)
Only agents.yaml + SKILL.md are updatable in PROD; server, ontology and views
ride the release train. Any ruling that can be expressed as SKILL doctrine
ships that way first.

## PROD-side items (asks to the access holder)
- [ ] Starburst PROD catalog: oracle.number.default-scale=9 +
      oracle.number.rounding-mode=HALF_UP (ASKS-external.md §3). The view
      CASTs make this optional for cast columns; keep it as the safety net.
      PROD must run the ROUND-bounded view release before relying on it.
- [ ] Scale re-census on PROD: db-asks S2 (DEV/UAT counts are not expectations).
- [ ] Deploy-check A0 + structure + grain on PROD after every view release,
      then db-asks B through Starburst.
- [ ] Re-measure the QA-labelled coverage numbers quoted in SKILL/yaml prose
      (regions, settlement, issuer names, unmapped currencies) and update them.
- [ ] Which PROD mechanism produced "Limit returned as Demand" (wave-2 view
      fallback vs the V2 mislabel of order_amount) — answerable from the
      release record, no DB access needed. The SKILL rule covers the label
      half now; the value half needs the IOI-rebuild view release.
