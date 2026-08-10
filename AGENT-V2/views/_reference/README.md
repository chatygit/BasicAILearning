# Schema reference — check here BEFORE asking for catalog info

Standing rule: **never ask the user for column names, data types, nullability,
or join keys.** They are recorded here and in `V1/`. If something is genuinely
missing, say which file you checked and what was absent — do not open with a
request.

## In this folder

| File | Contents |
|---|---|
| [view-columns.md](view-columns.md) | Every column of the four deployed views — `VW_DEAL_SUMMARY` (22), `VW_TRANCHE_SUMMARY` (39), `VW_ORDER_DETAIL` (20), `VW_ENTITY_SEARCH` (8). Types and lengths as deployed. |
| [base-table-columns.md](base-table-columns.md) | Physical `DGSTREAM` tables behind the views. |

## Elsewhere in the repo

| Source | Contents | Note |
|---|---|---|
| `V1/reference/columns.txt` | The 51 columns of the **old single view** (`VW_DEAL_ORDER_SUMMARY`) with types | Pre-split. Useful for "did V1 expose this?", which is the test for whether a column belongs in the new views at all. |
| `V1/docs/QA-FINDINGS-FOR-DATA-TEAM.md` | Join keys and index recommendations per base table (see the table near the end) | Written during the split. |
| `V1/docs/VIEW-SPLIT-PROPOSAL.md` §2 | The proposed DDL for all four views | **Proposal, not deployed.** The deployed DDL lives in `AGENT-V2/views/*.sql`. |
| `AGENT-V2/app/bqs/ontology/*.yaml` | Business-name → physical-column mapping per object | Can drift from the views; the views win. |
| `AGENT-V2/views/_diagnostics-results.md` | Answers to the pre-fix diagnostic queries, plus the scope rules governing view changes | Live document. |

## Scope rule that governs all of this

A column existing in a base table is **not** a reason to expose it on a view.
The four views were scoped to what the V1 view actually used. Do not add
columns; do not remove columns already exposed, even empty placeholders.
