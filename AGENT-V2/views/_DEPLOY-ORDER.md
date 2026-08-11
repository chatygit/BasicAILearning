# Deploy order — views FIRST, then ontology + SKILL

**The four view files and the four ontology files are a MATCHED PAIR.
Shipping the ontology ahead of the views is worse than shipping neither.**

The rewritten ontology asserts facts that only the rewritten views make true.
Against the currently-deployed (old) views it does not degrade gracefully — it
produces wrong answers and hard errors.

## What breaks if the ontology ships first

| Ontology asserts | Old view actually returns | Failure |
|---|---|---|
| `tranche_size` is "a real NUMBER", filterable with `gt/gte/lt/lte/between` | `VARCHAR2(480)` holding `'11.25E9'`, `'1k'` | **ORA-01722.** A `WHERE tranche_size > 1000000000` forces Oracle to convert the whole column; the `'1k'` row kills the query. This is exactly the V8 failure, now on a user-facing question ("tranches over $1bn"). |
| `tranche_size` orders numerically | text | `ORDER BY tranche_size DESC` sorts lexically — `'900'` beats `'1000000'`. Silently wrong top-N, no error. |
| `securities_maturity` is a DATE | NLS-formatted string | date filters and ordering wrong or erroring |
| `delivery_type` is "a SCALAR now, only three values" | pipe list, one entry per identifier row | agent renders `'RegS \| RegS \| RegS …'` against a documented 3-value set |
| `bnd_bank` may hold SEVERAL banks in a `' \| '` list | single bank (`MAX`) | co-B&D banks silently missing; the agent will not look for them |
| `order_allocation` is populated | 0 for the busiest DCM tranches | allocations reported as zero |
| declared grain holds; **9 dedup rules deleted** from doctrine | old views duplicate (order view ~2x) | **worst one.** The dedup doctrine was removed *because the views guarantee grain*. Against old views the guarantee is false AND the safety net is gone. |

## Correct order

1. Data team runs the four `vw_*.sql` in this folder.
2. Verify grain on the deployed views — `rows_ = grain_` for all four
   (the invariant, not the QA counts).
3. Then promote the ontology + SKILL.
4. Re-run `V1/regression_check.py` and `_review/ontology_check.py`.

## Until step 1 lands

Keep the previous ontology + SKILL in the deployed agent. The versions in this
repo are staged for step 3, not for now.

## Consequence for performance work

Any trace captured before step 1 is measuring the OLD views. The order view
returns roughly 2x the rows it should, so both the query time and the
synthesis time downstream of it are inflated by duplication we have already
fixed. **Re-trace after the views land before tuning `run_bqs_query` or the
synthesis call** — some of that cost is already dealt with.

The two hop savings (preloading the skill, inlining discovery output) are
independent of the views and can be done at any time.
