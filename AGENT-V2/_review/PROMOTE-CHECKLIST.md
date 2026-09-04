# Promote checklist — ECM/DCM text2sql agent

Two gates. The first is mechanical and takes 2 seconds; the second is the part a
machine cannot judge. Nothing promotes until gate 1 is green.

---

## Gate 1 — mechanical (run it, don't skim it)

```bash
python3 regression_check.py          # exit 0 = safe to promote
python3 regression_check.py -v       # show every check
```

Covers, for every config layer:

| Layer | What it proves |
|---|---|
| STRUCTURE | YAML/JSON parse, all rule regexes compile, no duplicate rule names, no empty-matching regex, schema column count |
| SQL CORPUS | every SQL shape that ever broke production is still **rejected — by the right rule** (diagnosis, not just rejection); every corrected shape still passes all rules; all query-library statements pass |
| INVARIANTS | load-bearing doctrine text still present (class-word map, id quoting, window bound, B&D `(true)`, reply anatomy…); retired doctrines still absent (`ORDER_ID … DCM only`, `Solo = ECM only`, `NO upper bound`) |
| CROSS-LAYER | facts that must appear in every layer that needs them (a rule living only in the skill dies on skill-absent turns — that was the NYSE bug) |

**Extend it with every fix — this is the whole point:**

- fixed a bad SQL shape → add it to `BAD_SQL` with the expected rule keyword
- wrote a concrete mapping → add the exact phrase to `INVARIANTS`
- overturned a doctrine → add the old wording to `RETIRED`
- rule must hold everywhere → add it to `CROSS_LAYER`

**When it fails, there are only two honest outcomes:** fix the regression, or
*consciously retire* the assertion (doctrine genuinely changed) — edit the case
and note why in the same commit. Never delete a red check to get green.

---

## Gate 2 — behavioral smoke set (fresh session each, after restart)

The suite cannot judge model behavior. These eleven prompts each pin a class we
fixed; check the fingerprint, not just "looks fine".

| # | Prompt | Fingerprint to verify |
|---|---|---|
| 1 | List all deals in NYSE exchange | broad OR-both LIKE, rows returned |
| 2 | List all Citi B&D deals/tranches in 2024 | BND_BROKER index recipe; **ECM-only user sees no DCM branch** |
| 3 | Security identifiers for deal &lt;multi-tranche&gt; | grouped per TRANCHE_NAME; zipped `CUSIP x · FIGI y` in one cell |
| 4 | Top 10 Energy Common Stock FO deals in Q1 2026 | `UPPER(EQUITY_TYPE) = 'COMMON STOCK'`, not PRODUCT_TYPE |
| 5 | All orders for deal &lt;91-order deal&gt;, then "next 20" ×5 | banners 1–20/91 … 81–91/91, absolute `#`, ends only at 91 |
| 6 | Top 10 deals with two or more tranches in 2026 | headline says **found** count, not "top 10" over 5 rows |
| 7 | Orders with investor region Non USA for deal X | negation predicate; `US` **and** `United States` both handled; NULL-region count stated |
| 8 | Deals priced in the last 12 months for TESLA INC | bounded window — **no 2028 rows** |
| 9 | &lt;listing&gt; → "analyze &lt;row 1&gt;" | **zero** entity_search calls; uses the id from the shown table |
| 10 | → "list those deals with their ticker and use of proceeds" | same rows, same order, same `#`; columns **appended**, not replaced |
| 11 | Any listing | quantitative brief → table (units in headers) → Insights & Trends → numbered follow-ups |

Record pass/fail per prompt with the trace id. A failure here becomes a new
Gate 1 case wherever it can be mechanized.

---

## Promote order

1. **View DDL** first if columns changed (else new-column SQL hits ORA-00904)
2. Configs: `skill-v7.md`, `agents-v6.yml`, `domain-v4.yml`,
   `vw_deal_order_summary-v3.json`, `sql-validation-v2.yml`, `unspported-v2.json`
3. Server changes (`text2sql_surgical_changes-v2.py`) — separate deploy
4. **Restart the app** (bootstrap-once: pods load definitions at startup —
   un-restarted pods are why "fixed" things appear to regress)
5. Gate 2 in fresh sessions

## U4 / numeric-mapping items (added 2026-09-03)
- [ ] PROD Starburst catalog carries oracle.number.default-scale=9 +
      oracle.number.rounding-mode=HALF_UP (mirror of the UAT ask in
      AGENT-V2/_review/bds-catalog-request-2026-09-03.md) BEFORE agent go-live
- [ ] PROD runs the ROUND-bounded view release (wave 2) before relying on the
      lossless-mapping argument
- [ ] Re-run AGENT-V2/views/_checks/_scale-probes-2026-09-02.sql against PROD —
      fresh census; DEV counts are not expectations (QA≠PROD)

## BQS_ENABLED_SOURCES — the nine-object allow-list (added 2026-09-04)
The server default (config.py) still enumerates the FOUR original objects; any
environment (and any LOCAL run) without the override silently hides the other
five — objects load, discovery omits them, the agent honestly refuses hedge/
trade/designation asks (observed 2026-09-04, QA-local). Before/with every
config deploy, the environment MUST set:
- [ ] BQS_ENABLED_SOURCES=capital_markets_deal,capital_markets_tranche,capital_markets_order,capital_markets_entity,capital_markets_hedge,capital_markets_hedge_trade,capital_markets_trade,capital_markets_designation,capital_markets_trade_syndicate
      (or "*" for local testing only — explicit list in deployed envs, fail-closed)
- [ ] Verify: discover with no source — the routing index must list NINE objects.
