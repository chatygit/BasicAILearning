# Post-deploy verification — view batches 2+3 (2026-08-19)

Two layers, in order. Layer 1 proves the VIEWS are right; layer 2 proves
the AGENT can reach them. Do not skip to layer 2 — an agent failure is
uninterpretable until the views are known-good.

## Layer 1 — SQL (run views/_deploy-check.sql in the target env)

Four independent statements — run as a script (F5). Section A is
structural and ALWAYS reports (it can't hit a missing column); B/C/D read
one view each, so an outdated view errors only its own section. (The
2026-08-19 DEV run proved the need: the order view lacked BILLED_BY and
the old single-query form returned nothing at all.) Read it like this:

| Row | Expect | Meaning if wrong |
|---|---|---|
| 1  | PASS | base view row-count sanity |
| 1b | PASS | order view carries BILLED_BY + OFFERING_TYPE (round 2) |
| 1c | PASS | tranche view carries EQUITY_TYPE (round 2) |
| 1d | INFO ~90% ECM / ~74% DCM | billed_by population |
| 1e | INFO ~6,892 | ECM deals with issuer name — ZERO means the OB_DEAL_ISSUER join regressed |
| 1f | INFO ~8,260 | DCM deals with region (batch 3) — ZERO means the rollup didn't land |
| 1g | INFO ~30,749 | DCM deals with settlement_ts (batch 3) |
| 1h | INFO ~5% | ECM tranches with a region (batch-3 NVL fallback) — 0-3 rows means fallback missing |
| 2  | PASS | TRANCHE_SIZE is NUMBER on both views |
| 3  | PASS | maturity stays VARCHAR2 (the ORA-01790 lesson) |
| 4  | PASS / 4b INFO ~0 | currency name fallback; unmapped tokens gone |

CAVEAT — the INFO expectations were measured in UAT data. If DEV holds a
different data load, the PASS/FAIL rows still bind (they are structural:
columns exist, types are right, joins produce >0), but INFO numbers can
legitimately drift. Judge INFO rows as "zero vs non-zero in the right
ballpark", not exact matches.

## Layer 2 — config, then agent smoke

FIRST: confirm the updated configs (ontology YAMLs + SKILL + agents.yaml
— rounds 2+3) are deployed to the MCP/agent app in the SAME environment.
Views without configs = columns the agent cannot reach; configs without
views = errors. Both halves are in the repo, pushed.

Then run these asks against the agent — each exercises one shipped fix:

1. "Who is the issuer of <any ECM deal from a listing>?"
   → a NAME, not "—" (issuer three-layer fix; 1e must be >0 first).
2. "List 5 recent convertible deals"
   → equity_type filter, sub-types listed alongside, ONE table.
3. "Top 10 long-only investors in IPOs by allocation"
   → ONE request (offering_type on order) — no deal-id ferry, no
   40-id error.
4. "Which orders were billed by Citi on <deal>?"
   → billed_by works at order grain (round 2).
5. "Show EMEA deals from last year"
   → answers WITH the sparse-coverage disclosure ("only deals that
   carry a region"), values NAM/EMEA/APAC.
6. "Which deals settle this week?"
   → settlement_ts range filter on the deal object — the old refusal
   is DEAD; partial-coverage disclosure expected.
7. "What currencies is <deal> priced in?"
   → currency NAMES (USD/CAD), never numeric tokens; unmapped =
   "not recorded".
8. Ask any question twice in a row verbatim
   → same answer twice, no product flip.
9. "Give me the biggest deal in each sector in 2025"
   → top-N-per-group in ONE request (partition_by).
10. "List Fidelity's indications and allocations across all deals"
    → the CAO case: disambiguation with numbered narrowing, one table
    per product, honest "Showing 1-50... More exist." caption.

Failures here with a green Layer 1: capture the MCP log line (the ask is
logged with each query now) and the debug trace — that combination
locates the fault in minutes.
