# Promote checklist — Capital Markets Agent (AGENT-V2)

Two gates, then a fixed order. Nothing promotes until gate 1 is green.
We have NO PROD access: every PROD-side line is a request to an access holder,
answered by a screenshot or a written confirmation — never a task we tick.

## Gate 1 — mechanical
```bash
cd AGENT-V2 && .venv/bin/python _review/ontology_check.py && .venv/bin/python -m pytest tests/ -q
```
`.venv` is the repo-local interpreter (gitignored); recreate it with
`python3 -m venv .venv && .venv/bin/pip install pytest pydantic pyyaml rapidfuzz`. The gate runs every tests/test_*.py itself and FAILS on a SKIPped case
(RT-1, 2026-09-17) — bare system python without those packages is red by design.
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
   the handover: the S1 source-name validation script (every source column
   referenced by the views in `SELECT … WHERE 1 = 0` statements — regenerate
   from the view files; last full version in git at 2026-09-21, section S1 of
   db-asks.sql) — every statement "no rows selected" on the target environment. Files go over verbatim
   and comment-free; a failed Flyway script aborts every later script.
2. **After the view deploy, before any prompt** — `views/_deploy-check.sql`:
   A0 shows nine LAST_DDL_TIMEs of today; structure rows 17, 1y, 1z, 18 PASS;
   grain rows 7, 8, 9, 10b, 11b, 12b PASS; population rows 15, 15b, 20b, 21,
   21b, and from the Ipreo release 22, 23, 24, 24c; section K timings
   screenshotted (K8 / K9 = the Ipreo branch). Then the S3 Trino check through
   Starburst (SELECT one row of each new column from each changed view +
   SHOW COLUMNS; git 2026-09-21 db-asks S3) — the Oracle-side check cannot see
   a stale connector metadata cache.
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
- [ ] Scale re-census on PROD: S2 (git 2026-09-21 db-asks S2; DEV/UAT counts are
      not expectations).
- [ ] Deploy-check A0 + structure + grain on PROD after every view release,
      then the S3 Trino check through Starburst.
- [ ] ECM issuer names in PROD (screenshot 2026-09-21: five real 2026 IPOs with
      no issuer name): run A0 (which view revision is live) and row 1e (ECM
      deals with issuer name), plus this count — it says whether the party
      master, the intended PROD source, carries names for ECM at all:
      `SELECT COUNT(DISTINCT T.DEAL_TRANSACTION_ID) AS ECM_TXNS_, COUNT(DISTINCT
      CASE WHEN P.PARTY_NAME IS NOT NULL THEN T.DEAL_TRANSACTION_ID END) AS NAMED_,
      COUNT(DISTINCT CASE WHEN P.PARTY_GFCID IS NOT NULL THEN T.DEAL_TRANSACTION_ID
      END) AS WITH_GFCID_, COUNT(DISTINCT CASE WHEN T.ISSUER_GFCID IS NOT NULL THEN
      T.DEAL_TRANSACTION_ID END) AS TXN_GFCID_ FROM DGSTREAM.OPUS_ECM_TRANSACTION T
      LEFT JOIN DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES P ON P.TRANSACTION_ID
      = T.DEAL_TRANSACTION_ID AND P.PARTY_ROLE = 'Primary Client';` — counts only,
      no rows leave PROD.
- [ ] PROD census pack S4 (counts + vocabularies only, no rows; git 2026-09-21
      db-asks S4, 12 statements) — its results replace every UAT-labelled
      number in SKILL/yaml prose.
- [ ] PROD behaviour evidence without DB access: after each release, request a
      week of the OCP query log (timings, error classes, zero-row rate,
      generated SQL) and the ADK traces of PROD sessions — behaviour is
      observable in logs even when data is not.
- [ ] Which PROD mechanism produced "Limit returned as Demand" (wave-2 view
      fallback vs the V2 mislabel of order_amount) — answerable from the
      release record, no DB access needed. The SKILL rule covers the label
      half now; the value half needs the IOI-rebuild view release.
