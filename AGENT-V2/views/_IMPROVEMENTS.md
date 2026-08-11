# View improvements — ranked, costed proposals

Companion to [`_diagnostics-results.md`](_diagnostics-results.md). That file says
what the data **is**; this one says what should change **next**, and what should
not. Nothing here is applied — the four views in this folder are validated and
every one of them holds its declared grain (Round 4). **A view change re-opens a
2–4 day cycle**, so each item below has to argue for that cycle on the evidence.

Ranking metric, as briefed:
`(agent hops removed + latency saved) / implementation risk`.

## Headline — the class-A work already shipped; the cycle items are P3 and P5

⚠️ **CORRECTED 2026-08-10 (adversarial review).** This file was drafted against a
pre-rewrite snapshot of `app/bqs/ontology/*.yaml` and `SKILL.md`. Those files were
rewritten in the same window, and **most of the config-side proposals below are
already implemented in them.** Verified against the current files:

| Was proposed as | Actual state now | Where |
|---|---|---|
| **P1** — declare the four deal roll-ups as filters | **ALREADY DONE**, with the exact operator sets P1 asks for | `capital_markets_deal.yaml` L462 / L474 / L484 / L492 |
| **P2** — model the four deal attributes on the tranche object | **ALREADY DONE**, dimension *and* filter, both products | `capital_markets_tranche.yaml` dims L229–232, filters L349 / L360 / L405 / L329 |
| **P2b** — `bnd_bank` operator set | **ALREADY DONE** — `[like, is_null, is_not_null]`, and correctly on BOTH products | `capital_markets_tranche.yaml` L489–502 |
| **R1** — record `MATCH_RANK` as declined | **ALREADY DONE** | `capital_markets_entity.yaml` L187–196 |
| **R2(c)** — enumerate the Q17 status literals | **ALREADY DONE**, and the bad `'Open'/'OPEN'` claim is already refuted | `capital_markets_deal.yaml` L374–384, `capital_markets_tranche.yaml` L365–377 |
| **R7** — refuse settlement-date asks | **ALREADY DONE** | `SKILL.md` L137, L454 |

**What actually survives.** One class-A idea (**P1's `'% | %'` idiom** — still
unimplemented; the ontology still routes multi-currency through
`having currency_count gt 1`), the two class-B asks (**P3** materialise the
entity view, **P4** the join-key indexes), the one new column (**P5**
`TRANCHE_SIZE` on `VW_ORDER_DETAIL`), and the class-C riders **P6/P7/P8**. The
best remaining change is **P3**, and the one new column that earns an exception
to scope rule 1 is **`TRANCHE_SIZE` on `VW_ORDER_DETAIL`**.

## Evidence sources — every claim traces to one of these

| Tag | Source | Status |
|---|---|---|
| **MEASURED** | `_diagnostics-results.md` (Q…, V…) | QA existence proof; counts are QA-only |
| **VIEW** | the deployed `vw_*.sql` in this folder, cited by line | physical truth |
| **BUILDER** | `app/bqs/sql_builder.py`, `app/bqs/dialects/trino.py`, `app/bqs/ontology/*.yaml` | our own code, readable now |
| **VIEW line numbers** | cited against the `vw_*.sql` in this folder | ✅ re-verified 2026-08-10, all correct |
| **ONTOLOGY / SKILL line numbers** | cited against `capital_markets_*.yaml`, `SKILL.md`, `sql_builder.py` | ⚠️ **captured pre-rewrite and were ALL stale.** Corrected inline where a claim rests on them; re-check before quoting any of them |
| **TRACE** | the V2 latency traces (2026-08-07 136s run, 2026-08-09 50s run) | agent-stack timing, **not** a claim about the data |
| **V1-DOC** | `V1/docs/QA-FINDINGS-FOR-DATA-TEAM.md` | already sent to the data team; re-asking is cheap |
| **OPEN** | unresolved — one query or one business answer away | never encoded as a rule until answered |

## Scope rules inherited from `_diagnostics-results.md` §"Scope rules"

1. **Do not add columns.** Withdrawn under this rule already: `MATCH_RANK`,
   `DEAL_REGION` on the DCM deal branch, any "real" `EXECUTION_STATUS`.
   One exception is argued below (**P5**) and is flagged as an exception.
2. **Do not remove columns already exposed** — including the 100%-NULL
   `SETTLEMENT_TS` (Q32) and the constant `EXECUTION_STATUS`.
3. **A view change is a 2–4 day cycle**, so everything ships in one pass and
   every ontology file changes in the same PR.
4. Prefer fixes that *remove* SQL over fixes that add it.
5. **Row-exclusion policy is a later batch.** No proposal below adds a status
   filter to any view. Two items (**P6**) change which rows a view emits for
   *structural* reasons (NULL keys, grain) — both are called out explicitly and
   need a sign-off, not an assumption.

---

## The cost model — four classes, and why the ranking looks like this

Ranking is dominated by the denominator. These are not the same kind of change:

| Class | What it touches | Cycle cost | Revalidation |
|---|---|---|---|
| **A — config** | `app/bqs/ontology/*.yaml`, `SKILL.md`, dialect/builder Python | hours, our own repo | ontology gate + regression suite |
| **B — DBA object** | indexes, statistics, a materialised view. **No view text changes.** | data-team ticket, no view cycle | none of the four views move |
| **C — view body** | an expression or a join inside a `vw_*.sql`, no column added | **2–4 days**, one pass | re-run V1/V4/V22/V26/V27 + the Q9 grain check |
| **D — new column** | a column the views do not currently expose | **2–4 days + a scope-rule exception** | as C, plus every ontology file |

A class-A item with the same benefit as a class-C item wins by a wide margin,
and that is exactly what P1 and P2 are.

---

## The ranking

| # | Proposal | Class | Hops removed | Latency | Risk | Verdict |
|---|---|---|---|---|---|---|
| **P1** | The `'% \| %'` multi-currency idiom (the four roll-up filters are already declared) | A | 0 — the filters exist | converts a non-pushable `HAVING` into a pushable `WHERE` | ~0 | ✅ **DO NOW — idiom only** |
| **P2** | Model the four deal attributes already on `VW_TRANCHE_SUMMARY` | A | — | — | — | ✅ **ALREADY DONE — verify only** |
| **P3** | Materialise `VW_ENTITY_SEARCH` + function-based index on `UPPER(ENTITY_NAME)` | B | 0 | **9.4s → sub-second on the pre-question hop** | low | ✅ **ASK NOW — top remaining item** |
| **P4** | Confirm/create the child-table join indexes and refresh optimizer stats | B | 0 | unmeasured, plausibly large | ~0 | ✅ **ASK NOW** |
| **P5** | Denormalise `TRANCHE_SIZE` onto `VW_ORDER_DETAIL` | **D** | **1 on every coverage ask** | ~10s per coverage ask | low | ✅ **EARNS THE EXCEPTION** |
| **P6** | Entity grain fix + the missing `IS NOT NULL` guards | C | 0 | shrinks the object ~3.5× | medium | ✅ **RIDE P3** |
| **P7** | Deal-card count honesty (`ORDER_COUNT` / `TRANCHE_COUNT`) | C | defends an existing zero-hop capability | — | low | ✅ **RIDE ANY CYCLE** |
| **P8** | Narrow the four `SELECT *`-through-a-window dedupes | C | 0 | unmeasured; Oracle may already prune | ~0 | ⚠️ **RIDER ONLY** |
| R1 | `MATCH_RANK` on the entity view | D | — | — | — | ❌ **REJECT — not expressible as a column** |
| R2 | A normalised UPPER status column | D | 0 | 0 | high | ❌ **REJECT — redirect to config** |
| R3 | Drop the `ROW_NUMBER` dedupes | C | 0 | unmeasured | **high** | ❌ **REJECT — they are the grain insurance** |
| R4 | Oracle Text (`CONTEXT`) index for contains-search | B | — | — | — | ❌ **REJECT — unreachable through Trino** |
| R5 | `DISTINCT` on the ECM syndicate `LISTAGG` | C | — | — | — | ❌ **REJECT — breaks position alignment** |
| R6 | A precomputed `CURRENCY_COUNT` column | D | — | — | — | ❌ **REJECT — superseded by P1** |
| R7 | Drop `SETTLEMENT_TS` / `EXECUTION_STATUS` | C | — | — | — | ❌ **REJECT — scope rule 2** |
| R8 | Materialise the deal / tranche / order views | B | — | — | — | ❌ **REJECT — no measured pain, 5.86M rows** |
| D1–D7 | Seven items blocked on one query each | — | — | — | — | ⏳ **DEFERRED — queries written below** |

---
---

# TIER 0 — already precomputed, currently unreachable

These cost no view cycle. They are here, in a views document, because the thing
being wasted is **work the views already did**.

## P1 — The multi-currency `'% | %'` idiom  ✅ DO NOW (the rest of P1 already shipped)

`VW_DEAL_SUMMARY` computes `TRANCHE_COUNT`(17), `ORDER_COUNT`(21),
`INVESTOR_COUNT`(22) and `CURRENCIES`(20) — four columns of pre-aggregation
whose entire purpose is to keep deal questions single-object (Q1 column list;
view L55–60, L147–152).

⚠️ **The original claim here — "`capital_markets_deal.yaml` declares all four as
dimensions and none of them as filters" — is FALSE against the current file.**
All four are declared filters, with the operator sets this section goes on to
recommend: `tranche_count` L462, `order_count` L474, `investor_count` L484,
`currencies` L492 (`[like, is_null, is_not_null]`, contains-match only). Each one
carries its NULL-vs-0 caveat and the Q20 divergence caveat. **Nothing in the
table below is a live gap; it is retained as the rationale for what shipped.**

| The ask | The column that answers it | Status |
|---|---|---|
| "deals with more than one tranche" | `TRANCHE_COUNT` | ✅ filter declared — no hop |
| "deals with more than 100 orders" | `ORDER_COUNT` | ✅ filter declared — no hop |
| "deals with more than N investors" | `INVESTOR_COUNT` | ✅ filter declared — no hop |
| "deals that priced in USD" | `CURRENCIES` | ✅ `like '%USD%'` declared, with the D1 caveat |
| "multi-currency deals" | `CURRENCIES` | ❌ **still a `HAVING` on a computed expression — the one live item, below** |

### The multi-currency idiom — the lazy solution, and it only became valid now

`currency_count` is `list_count: true` (BUILDER, `capital_markets_deal.yaml` L215–226),
which the Trino dialect compiles to
`CARDINALITY(SPLIT(col, ' | '))` (BUILDER, `dialects/trino.py` L58–63). The
worked example in the same file thresholds it with
`having: [{metric: currency_count, op: gt, value: 1}]` (L618–628), and the
`how_to_use` note at L121–124 instructs exactly that shape. **`SPLIT` and
`CARDINALITY` cannot push down to Oracle through the federation link, so the
whole matched set crosses the wire before the threshold is applied** (TRACE —
this is the shape of the 136s "List all the multi-currency deals in the year
2024" run).

A pipe in `CURRENCIES` means more than one currency. That is a plain `LIKE`:

BEFORE — the threshold is a `HAVING` on a computed expression, non-pushable:

```yaml
metric: currency_count
dimensions: [deal_id, deal_name, currencies]
filters:
  - {field: product,      op: eq,  value: DCM}
  - {field: last_priced,  op: gte, value: "2024-01-01"}
  - {field: last_priced,  op: lt,  value: "2025-01-01"}
having: [{metric: currency_count, op: gt, value: 1}]
```

AFTER — the threshold becomes a pushable `WHERE`; the count still displays:

```yaml
metric: currency_count
dimensions: [deal_id, deal_name, currencies]
filters:
  - {field: product,      op: eq,  value: DCM}
  - {field: last_priced,  op: gte, value: "2024-01-01"}
  - {field: last_priced,  op: lt,  value: "2025-01-01"}
  - {field: currencies,   op: like, value: "% | %"}
```

**This idiom is only correct because of the rewrite.** Before it, Q21 measured
**6,940 DCM deals rendering `USD | USD | USD`** — a pipe meant nothing. V2
confirms zero such deals now, so a pipe genuinely means two distinct
currencies. Do not let anyone "simplify" the DISTINCT out of the currency
subqueries (view L106, L196) — this filter depends on it.

Two safety notes, both checked: the `ON OVERFLOW TRUNCATE '...' WITH COUNT`
marker is appended *after* a delimiter, so a truncated list still reads as
multi-currency (no false negative); and case-insensitive wrapping does not touch
pipes. The idiom is also **unaffected by open question D1** (whether ECM renders
currency ids or names) — a pipe is a pipe either way.

### What to declare — ✅ all four already declared, verified 2026-08-10

| Filter | Operators declared | Note |
|---|---|---|
| `tranche_count` | `gt gte lt lte between eq is_null is_not_null` | numeric, both products (L462) |
| `order_count` | same | numeric; **carries the Q20 caveat — see P7** (L474) |
| `investor_count` | same | numeric; same caveat (L484) |
| `currencies` | `like is_null is_not_null` | **pipe list — no `eq`/`in`/`ne`/`not_in`.** `eq` against a list silently misses every multi-value row (L492) |

The only thing left to write is the `'% | %'` idiom itself: replace the
`having currency_count gt 1` shape in `capital_markets_deal.yaml`'s `how_to_use`
(L121–124), the `currency_count` metric description (L219–226) and the worked
example (L618–628) with the filter form above.

**Verify by:** the "multi-currency deals in 2024" ask completes in one
`run_bqs_query` against `capital_markets_deal` and the `generated_sql` contains **no
`HAVING` clause**. `CARDINALITY(SPLIT(...))` will still appear in the SELECT
list — `currency_count` remains the projected metric, by design, so "no
`CARDINALITY` anywhere" is the wrong test and this proposal would fail it.

## P2 — The four deal attributes on the tranche view  ✅ ALREADY DONE — verify only

⚠️ **This section's premise — "`capital_markets_tranche.yaml` declares them as neither
dimension nor filter" — is FALSE against the current file.** All four are
declared as both. Retained as the physical-truth record for whoever re-checks.

| Column | ECM source | DCM source | Ontology state now |
|---|---|---|---|
| `DEAL_REGION` (8) | `OBT.DEAL_REGION` (view L65) | **`ODT.REGION`** (view L223) | ✅ dim L230, filter L349 — *"Wired on both products on this object"* |
| `USE_OF_PROCEEDS` (21) | `T.USE_OF_PROCEEDS` (L82) | `ODT.USE_OF_PROCEEDS` (L240) | ✅ dim L231, filter L405 |
| `SETTLEMENT_CURRENCY` (24) | `T.SETTLEMENT_CURRENCY_NAME` (L85) | `ODT.SETTLEMENT_CURRENCY` (L243) | ✅ dim L232, filter L329 |
| `DEAL_STATUS` (26) | `S.STATUS_VALUE` (L87) | `ODT.STATUS` (L245) | ✅ dim L229, filter L360 — *"populated on BOTH products — do not hop to the deal object for it"* |

**The `DEAL_STATUS` "instructed hop" no longer exists, and the quote was
misattributed.** *"NULL on every ECM row; for ECM status use deal_status"* now
sits on **`tranche_status`** (`capital_markets_tranche.yaml` L264, filter L379) — where
it is **correct**: `TRANCHE_STATUS` really is `CAST(NULL …)` on ECM (view L86)
while `DEAL_STATUS` is populated (view L87). The criticism of `SKILL.md` §2 was
also wrong: L102 lists `deal_status` among the deal attributes denormalised onto
the **tranche** object only, and makes no claim about the order object.
(`VW_ORDER_DETAIL` is 20 columns, verified, and has no status — that part holds.)

**`DEAL_REGION` — one caveat the ontology states and this file did not.** ECM
population is confirmed; **DCM population of `ODT.REGION` is UNMEASURED.** The
view selecting a column proves it is *sourced*, not that it is *populated*;
`capital_markets_tranche.yaml` L349–359 says so explicitly and gives the fallback. Do not
upgrade "false on the tranche object" into a claim about data. The value list
`NAM/EMEA/APAC` is V1-confirmed. Note the DCM tranche branch carries *both*
`ODT.REGION AS DEAL_REGION` and `ODT.TRANCHE_REGION AS TRANCHE_REGION` — two
different source columns, and spec §3.2 item 9 makes the distinction
load-bearing.

**Do not model `EXECUTION_STATUS` (27).** It is `MAX(S.STATUS_TYPE)` from a
subquery filtered `WHERE STATUS_TYPE = 'Execution_Status'` (view L131–134), so
it is that literal constant on every ECM row and NULL on every DCM row. Keep the
column (rule 2); declare it *declined*, not silently absent. ✅ already done —
`capital_markets_deal.yaml` L250 calls it a *"DEAD COLUMN"* and says "do not project it".

**Verify by:** "EMEA tranches with a 10-year tenor" and "priced tranches of
green bonds" each complete in one request on `capital_markets_tranche` — and the EMEA one
returns non-zero rows on DCM, which is the unmeasured half.

## P2b — Config-side riders in the same PR (no view change)

Small, all class A, all traceable, none of them worth their own section:

- **`numeric: true` forces a cast that is now redundant.** `_agg_expr` wraps
  SUM/AVG/MIN/MAX in the dialect's `numeric_cast` when the metric declares
  `numeric: true` (BUILDER, `sql_builder.py` **L33–43**), and the Trino dialect
  renders that as `TRY_CAST(col AS DOUBLE)` with the comment *"Governed numeric
  measures are stored as VARCHAR in the view"* (`dialects/trino.py` **L52–56** —
  the comment is there, not in `sql_builder.py`). That comment is stale:
  `DEAL_SIZE`, `ORDER_AMOUNT`, `ORDER_DEMAND_QTY` and `ORDER_ALLOCATION` are
  `NUMBER` (Q1), and `TRANCHE_SIZE` becomes one **when this rewrite deploys**
  (V25) — sequence the two, because against the *currently deployed*
  `VARCHAR2(480)` the cast is still load-bearing. A cast around an
  already-numeric column is at best free and at worst blocks aggregate pushdown.
  **Measure with the existing `build=/execute=` phase timers before changing
  it** — do not assume.
- **"Citi non-B&D" needs a `computed_filter`, not a column.** The ontology
  already says so — `capital_markets_tranche.yaml` **L89–90** (*"the clean form is a
  governed `computed_filter` with `negate`, and this source declares none"*) and
  the GAP note at **L900–907**; `SKILL.md` L70–71 records that all four objects
  declare none. It is Python + YAML, not DDL. No view proposal here.
- **`bnd_bank`: ✅ already correct, and "`like` only on ECM" would have been a
  bug.** The operator set is per-*field*, not per-product — there is no way to
  offer an operator on one product only. `capital_markets_tranche.yaml` L489–502 already
  declares `[like, is_null, is_not_null]` for both products, which is right:
  `like` is needed on **DCM too**, because Citi is five subsidiaries
  (`%CITIGROUP GLOBAL MARKETS%` — `SKILL.md` §7) and equality would miss them.
  The ECM rationale still holds — ECM is a `LISTAGG` of every flagged member
  (view L171–172; Q25: **850** tranches have more than one) against DCM's scalar
  `ODT.BD_BANK` (view L255) — and the pipe list is the *correct* behaviour,
  replacing a `MAX()` that silently dropped co-B&D banks.

---
---

# TIER 1 — zero-DDL asks to the data team (no view cycle)

## P3 — Materialise `VW_ENTITY_SEARCH`, index `UPPER(ENTITY_NAME)`  ✅ ASK NOW

**This is the largest measured latency number in the whole diagnostics file, on
the one path that runs before the user's question.**

| Evidence | Number |
|---|---|
| Q29 — a single BlackRock name lookup | **9.4 s** |
| Q28 — a `GROUP BY` over the view | **79.4 s** |
| `capital_markets_entity.yaml` L87 — declared `query_timeout_seconds` | **30 s — but INERT.** L80–86 states it plainly: the executor applies a timeout for Postgres and Oracle only, not this dialect, and *"the measured 79.4s aggregate (Q28) was not killed by anything."* Do not cite it as a bound |
| Q28/Q9 — total rows in the object | **177,972** |
| TRACE 2026-08-09 — a whole `run_bqs_query` on the order object | 6.2 s |

The lookup that precedes the real question costs **more than the real question
does**. And `VW_ENTITY_SEARCH` is a **plain view over the other two views** — it
selects `FROM DGSTREAM.VW_ORDER_DETAIL` (view L11) and
`FROM DGSTREAM.VW_DEAL_SUMMARY` (L29, L47). Not materialised, not indexed. Every
resolution re-derives the full order view, including the `ROW_NUMBER` dedupe
over `OB_ORDER` (5.86M rows in QA). Round-4 open risk #1 names exactly this.

Spec §4 asked the question directly — *"If the entity object is materialised
with an index on the upper-cased name, say so — it changes the resolution
strategy from 'scan' to 'seek' and is worth a lot."* **The answer is no**, and
nothing in the ontology says so.

### Why this is cheap

- **178k rows.** The whole object is smaller than one deal's PROD order book.
- **Zero change to any `vw_*.sql` in this folder.** The four validated views do
  not move; their grain proofs (V1/V4/V22/V26/V27) stand untouched.
- **The ontology string does not change.** `base_view:
  dataglobe_oraas.dgstream.vw_entity_search` stays byte-identical if the MV
  takes the name.
- **The ask is already written and already sent.** V1-DOC, "Longer-term option:
  a purpose-built entity-search object" — *"A materialised view over that
  shortlist … would be a few thousand rows and would make these lookups
  sub-second on both products."*
- **Complete refresh on a schedule, not fast refresh.** The branches contain
  window functions and `LISTAGG`s upstream, so fast refresh is not available.
  Build cost is bounded by Q28's 79.4 s — under two minutes in QA. Entity lists
  tolerate staleness of hours (V1-DOC).

### The index caveat, stated plainly

A b-tree on `UPPER(ENTITY_NAME)` serves `= 'BLACKROCK'` and
`LIKE 'BLACKROCK%'` — **not** `LIKE '%BLACKROCK%'`, which is exactly what the
ranking contract emits (`capital_markets_entity.yaml` L49–55). V1-DOC states this
caveat and V1-DOC's addendum widens it: our builder wraps **both sides** in
`UPPER()` for `eq`, `ne`, `like`, `in` and `not_in` alike (BUILDER,
`sql_builder.py` `_filter_predicate` docstring).

So be honest about the split:

- **Materialisation is the win.** After it, the contains-scan runs over 178k
  narrow rows instead of re-deriving a 5.86M-row order view.
- **The index is the bonus**, for the `eq` path (a full legal name, or an id)
  and for prefix matching if we ever add it. V1-DOC's measurement supports it:
  a sargable `GPNUM = '00000000'` cost 1.2 s against 2.9 s for a name scan on
  the same branch — the optimizer *can* seek, it just has nothing to seek on.
- **Refresh optimizer statistics on the MV** as part of the job.

**Verify by:** re-run Q29 (BlackRock lookup) and Q28 (`GROUP BY` over the
object). Target: Q29 well under 1 s, Q28 under 30 s — a target we choose, **not**
a timeout that will enforce it (see the table). Until Q28 fits, the ontology must
keep requiring `entity_type` + `entity_name` on every metric, which is what
currently stands between a resolution and the 79.4 s unfiltered scan.

**One thing to fix in the ontology alongside this ask.**
`capital_markets_entity.yaml` L194–196 asserts that *"Same rule withdrew MATERIALISING
this view; the 9.4s / 79.4s costs are structural."* That is wrong on its own
terms: scope rule 1 is *"do not add columns"*, and materialising an object adds
no column, changes no `vw_*.sql`, and leaves the `base_view` string
byte-identical. The costs are structural **only while the object stays a plain
view**. Correct the note when the ask goes out.

## P4 — Confirm the join-key indexes and refresh statistics  ✅ ASK NOW

Zero risk, no view cycle, already written up in V1-DOC "Index candidates" and
never answered. Re-ask, with the rewrite's evidence attached:

| Table | Column(s) | Serves | Evidence |
|---|---|---|---|
| `OB_ORDER` | `ORDER_ID` | the `ROW_NUMBER` dedupe (view `vw_order_detail` L144) | Round-4 open risk #1 — without it every order query sorts 5.86M rows to remove **6** duplicates (Q12) |
| `OB_ECM_ORDER` | `ORDER_ID` | same dedupe, ECM (L57) | Q12: 101 duplicates |
| `OB_TRANCHE` | `DEAL_TRANCHE_ID` | DCM identifier + delivery-type `LISTAGG` (L293) | Q23 |
| `OB_TRANCHE_RATING` | `DEAL_TRANCHE_ID` | `ISSUER_RATINGS` `LISTAGG` (L304) | V1-DOC Finding 1 |
| `OB_TRANCHE_SYNDICATE_MEMBER` | `DEAL_TRANCHE_ID` | DCM `DEAL_SHARING_TYPE` (L317) | V1-DOC |
| `OB_DEAL_ISSUER` | `DEAL_TRANCHE_ID` | issuer joins, both views | Q12: 156 duplicates |
| `OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE` | `(ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID)` | four aligned `LISTAGG`s + the SOLO test (L173, L205) | V1-DOC |
| `OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL_IDENTIFIER` | same pair | ECM identifier `LISTAGG` (L188) | V1-DOC |

**The concatenated keys are seekable from the inner side.** Five joins use
`X.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID`. The concatenation
sits on the **outer** side, so a plain index on the child table's
`DEAL_TRANCHE_ID` is usable — no function-based index needed. (V1-DOC Finding 3
also asks the data team to align the datatypes so the ECM side's
`TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) = O.TRANCHE_ID` (view L105) stops
blocking index access. That is a source change with a long lead time; ask, do
not wait.)

Add: **check whether optimizer statistics are current** on these tables. Stale
stats produce bad plans independently of indexing (V1-DOC).

---
---

# TIER 2 — items that earn a view cycle

## P5 — Denormalise `TRANCHE_SIZE` onto `VW_ORDER_DETAIL`  ✅ EARNS THE EXCEPTION

**This is the one new column proposed here, and it is proposed against scope
rule 1 deliberately.** The argument:

**1. The ask is already on the record.** `capital_markets_order.yaml` L128–133, verbatim:

> *"COVERAGE / oversubscription = demand ÷ SIZE. Demand is here; SIZE IS NOT ON
> THIS OBJECT — it lives on capital_markets_tranche (total_tranche_size, now a real
> NUMBER). Answering costs two requests plus your own division; say the ratio
> and both inputs. (Denormalising TRANCHE_SIZE down onto this view would make
> it single-object and is legal at this grain — raised with the view owner, not
> yet available.)"*

**2. Coverage is a headline banker metric, not an edge case.** `SKILL.md` §11
puts it in the desk-phrasing list — *"the book was 3.2x covered"* (L538) — and
§6 L213–214 calls it *"the one common ask that costs two requests."*

**3. It requires ZERO new joins.** Both branches already reach the tranche row:

| Branch | The inline view already in the `FROM` | What to add |
|---|---|---|
| ECM | `TT` — `OPUS_ECM_TRANSACTION_TRANCHE`, deduped, LEFT JOINed (`vw_order_detail` L92–105) | `TTR.TRANCHE_OFFER_SIZE` into the inner projection, wrapped in the **identical** regex `CASE` from `vw_tranche_summary` L68–72 |
| DCM | `ODT` — `OB_DEAL_TRANCHE`, deduped, INNER JOINed (L149–159) | `DT.TRANCHE_SIZE`, wrapped in the identical `CASE` from `vw_tranche_summary` L226–230 |

No new table, no new join predicate, no new fan-out surface. The grain proofs
(V22 ECM 48,302 = 48,302; V4 DCM 5,826,084 = 5,826,084) are unaffected because
both joins already exist and are already deduped.

**4. The ratio is unit-safe at this grain, on both products.** ECM
`ORDER_DEMAND_QTY` is shares and `TRANCHE_OFFER_SIZE` is shares; DCM
`ORDER_DEMAND_QTY` is `OZ.AMT` notional and `TRANCHE_SIZE` is notional, in one
currency within one tranche. Q8 is the existence proof: `SUM(FINAL_ALLOC)`
reconciles to `TRANCHE_SIZE` exactly on one of the five busiest DCM tranches
and at 98.6% / 99.5% on two others. **That reconciliation is precisely what this
column makes queryable.**

**5. It only became worth doing now.** Before the rewrite `TRANCHE_SIZE` was
`VARCHAR2(480)` and a numeric comparison raised ORA-01722 (V8, V12). A text
size denormalised onto 5.87M order rows would have been useless.

### Spec compliance

Spec §2.2: *"Denormalise downward, never carry a finer grain upward."* A tranche
attribute on the order object is the sanctioned direction — the same direction
as `DEAL_NAME`, `TRANCHE_NAME`, `PRICING_TS` and `CURRENCY`, which the order
view already carries.

### The worked example — one request where there are two today

```yaml
- question: Coverage on each tranche of a DCM deal
  request:
    source: capital_markets_order
    metric: total_demand
    dimensions: [tranche_id, tranche_name, tranche_size, currency]
    filters:
      - {field: product, op: eq,  value: DCM}
      - {field: deal_id, op: eq,  value: "1500009396"}
    order: [{field: total_demand, direction: desc}, {field: tranche_id, direction: asc}]
    limit: 25
```

`total_demand ÷ tranche_size` per row, computed by the model over ≤25 rows.
Today this is two `run_bqs_query` calls — TRACE puts one MCP round-trip at 6.2 s
plus ~4.6 s of inter-turn model time, so roughly **10 s saved per coverage
ask**.

### The footgun that must ship with it

**`tranche_size` on the order object is a DIMENSION, never a metric.** A
`SUM(tranche_size)` over orders multiplies the size by the order count — PROD
deals carry ~2,000 orders (Round 4), so the error is ~2,000×. The ontology must
declare it with no aggregation and the filter set `gt gte lt lte between eq`
(threshold "orders on tranches over $1bn"), and `SKILL.md` §6 must route
"tranche size" to `capital_markets_tranche.total_tranche_size` as it does today.

Second caveat, inherited: the ECM join is a `LEFT JOIN` on
`TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) = O.TRANCHE_ID` (view L105), so an ECM
order that misses the tranche spine gets `NULL` size — the same rows that
already get NULL `TRANCHE_NAME`, `PRICING_TS` and `CURRENCY`. Declare
`is_null`/`is_not_null` on the filter and disclose the excluded count — the
same disclosure discipline `capital_markets_order.yaml` L320–334 already applies to
`investor_region` (*"a NOT-region predicate silently drops those rows — count
them with is_null and disclose the number"*).

**Verify by:** acceptance ask — "how covered was each tranche of deal X" —
completes in one `run_bqs_query`, and the per-tranche demand ÷ size on a DCM
deal from Q8 reproduces Q8's reconciliation.

## P6 — Entity grain fix + the missing NULL guards  ✅ RIDE P3

Ships in the same cycle as P3 (you materialise a query; materialise the fixed
one). Independently revertible if the sign-off in (c) does not come.

**(a) One id yields many rows, because every branch also groups by name** —
`O.INVESTOR_NAME` (view L15), `D.ISSUER_NAME` (L33). Measured (Q28):

| Branch | rows | distinct ids | inflation |
|---|---|---|---|
| INVESTOR / DCM | 124,668 | 9,871 | **12.6×** |
| ISSUER / DCM | 6,907 | 671 | 10.3× |
| INVESTOR / ECM | 2,982 | 1,157 | 2.6× |
| DEAL / DCM | 21,068 | 21,068 | **1.0× — at grain** |
| DEAL / ECM | 22,347 | 18,399 | *closed by the deal-view rewrite* (V1: 18,399 = 18,399) |

⚠️ **Two corrections to the original framing of this item.** First, *"the
declared grain is not held, on any branch"* was false twice over: the table above
shows the DEAL branch holds at 1.0× on DCM and is closed on ECM by the deal-view
rewrite, and the DEAL branch needs **no `GROUP BY`** because `VW_DEAL_SUMMARY` is
already one row per `(product, deal_id)` — its absence is not evidence of a
violation. Second, the grain quoted (`[entity_type, product, entity_id]`) is not
what `capital_markets_entity.yaml` declares: **L79 declares `[entity_type, product,
entity_name, entity_id]`**, with a note (L76–78) that name is part of the key
precisely because entity_id alone is not unique and both columns are nullable. On
that declaration **the view holds its grain**. So this is a *usefulness* defect,
not a grain-contract breach — argue it on the two harms below, which are real
either way, and do not claim a broken invariant that the gate will not reproduce.

Two ontology promises still break: the `limit 10` contract can return one entity
ten times (Q29 — id `00918` under both `BlackRock` and `BLACKROCK`, id `41364`
under two `Blackrock Financial Mgmt` spellings); and the activity ranking that is
the object's entire purpose is **split across 12.6 name variants**, so a large
investor with inconsistent spellings ranks below a smaller consistent one.

Fix: group by `(ENTITY_TYPE, PRODUCT, ENTITY_ID)` and pick a display name —
`MAX(name)` is consistent with how every other scalar in these views collapses.
This is a **grain-declaration change too**: `capital_markets_entity.yaml` L79 must drop
`entity_name` from the grain in the same PR, or the ontology and the view will
disagree in the other direction.

**(b) The DEAL branch has no `IS NOT NULL` guard.** The INVESTOR branch has
`WHERE O.INVESTOR_NAME IS NOT NULL` (view L12), the ISSUER branch has
`WHERE D.ISSUER_NAME IS NOT NULL` (L30), the DEAL branch has no `WHERE` clause.
Q28: **343 NULL entity names** on DEAL/ECM **and 1 on DEAL/DCM** — both branches
of the same `SELECT`, so one line fixes both and makes all three consistent.

**(c) ⚠️ NULL `ENTITY_ID` needs a sign-off before (a) ships.** Q29: `ENTITY_ID`
was NULL on **2 of 10** BlackRock candidates (`BlackRock London`,
`BlackRock (Singapore) Limited`). Grouping by `ENTITY_ID` collapses **every**
NULL-id row for a product into one row with an arbitrary `MAX(name)` — actively
worse than today. Two options, and the choice is the user's:

1. **Drop NULL-id rows** (`WHERE ENTITY_ID IS NOT NULL`). Consistent with the
   ontology's own position — L22–23 *"Always return entity_id (a candidate
   without an id is useless)"*, L58 *"Every candidate carries 'entity_id' —
   return it"*, L108 *"ALWAYS project it"*. This is a **row-count change**; it is the same
   *kind* of guard as the two `IS NOT NULL` clauses already in the view, not a
   business-status exclusion, but it is still a row-exclusion and rule 5 says
   ask.
2. **Keep them ungrouped** (group by `NVL(ENTITY_ID, ENTITY_NAME)`), which
   preserves them as unpickable candidates.

Do not pick one silently.

**What this does NOT fix, and must be restated rather than hidden:** spec §4's
*"exact match first, then contains, and the tiers must be gated"* is
unimplementable in the current design — see **R1**.

**Verify by:** re-run Q28. Every branch must report `rows = distinct_ids`, and
`null_names` must be 0 everywhere.

## P7 — Deal-card count honesty  ✅ RIDE ANY CYCLE

The precomputed counts on the deal card and the objects that page them count
**different populations**. This directly violates `SKILL.md` §11 *"Breakdown
buckets must sum to the stated total"* and spec §5 "Count honesty".

**`ORDER_COUNT` / `INVESTOR_COUNT`, DCM.** The subquery is
`SELECT O.ROOT_ID, COUNT(DISTINCT O.ORDER_ID) … FROM OB_ORDER GROUP BY ROOT_ID`
(view L182–186) — **completely unfiltered, and keyed on the deal only**.
`VW_ORDER_DETAIL` INNER JOINs `OB_DEAL_TRANCHE` on `(ROOT_ID, PARENT_ID)`
(L160–161). Q20: **37,517 DCM orders have no matching `(DEAL_ID, TRANCHE_ID)`
row, spanning 586 deals.** Diagnostics names the consequence: *"the deal card
and the paged order list disagree on 586 deals."*

**`ORDER_COUNT` / `INVESTOR_COUNT`, ECM.** The `OD` subquery (view L115–125)
applies the three order predicates but is keyed on `DEAL_ID` alone, without the
`OPUS_ECM_TRANSACTION` join that `VW_ORDER_DETAIL` applies (L73–85). ⚠️ **Do not
say the `Execution_Status` exclusion is missing** — `OD` is `LEFT JOIN`ed onto
`T`, which is already `INNER JOIN`ed to the status subquery `S` (view L72–81),
so the exclusion *is* applied at deal level. What is missing is
**per-transaction** granularity: on a multi-transaction ECM deal (Q10: 43,718
transactions across 41,779 deals) the deal survives on one transaction while
`OD` counts the orders of all of them. Same class of divergence as DCM, **but
unmeasured — do not size it before running the query.**

**`TRANCHE_COUNT`.** The `TR` subquery counts
`COUNT(DISTINCT TT.ECM_TRANSACTION_ID || '~' || TT.ECM_TRANSACTION_TRANCHE_ID)`
with no `Execution_Status` exclusion (view L88–99), keyed on *transaction*+
tranche; `VW_TRANCHE_SUMMARY` dedupes to `(DEAL_TRANSACTION_ID, TRANCHE_ID)` and
INNER JOINs the status filter. Measured gap: **V1 reports `total_tranches =
34,599`; V26 reports the ECM tranche view holds 33,010 rows. 1,589 tranches are
counted on the deal card and do not exist on the tranche object.**

Fix: make each roll-up count exactly the rows its sibling object will return —
the DCM `OC` subquery joins the deduped `OB_DEAL_TRANCHE` on
`(ROOT_ID, PARENT_ID)`; the ECM `OD` and `TR` subqueries pick up the same
`Execution_Status` inner join and transaction spine the sibling views use. This
**adds** SQL, which rule 4 disprefers.

**The disclosure alternative is already shipped — this is now a fix-or-leave
decision, not fix-or-disclose.** `SKILL.md` L215–219 carries it with both
measured numbers (*"37,517 DCM orders across 586 deals, and ~1,589 ECM tranches,
counted on the card but absent from the paged object"*), and
`capital_markets_deal.yaml` repeats it on the `tranche_count` filter (L462–473, naming
34,599 vs 33,010) and the `order_count` filter (L474–481). So the numbers are
already labelled rather than silently wrong. Take the view fix only if a cycle is
already open for P5 or P6; otherwise leave it, and change nothing in the
ontology.

**Verify by:** for a sample of the 586 Q20 deals, the deal card's `ORDER_COUNT`
equals `row_count` from a paged `capital_markets_order` listing of the same deal. And
re-run V1 vs V26: `total_tranches` on the deal view must equal the tranche view's
row count for the same scope.

## P8 — Narrow the four `SELECT *`-through-a-window dedupes  ⚠️ RIDER ONLY

Four dedupes pull every column of a base table through a window function:

| Site | Line | Columns actually used downstream |
|---|---|---|
| `vw_order_detail`, `OB_ECM_ORDER` | L56 `SELECT EO.*` | 18 |
| `vw_deal_summary`, `OPUS_ECM_TRANSACTION` | L64 `SELECT ET.*` | ~12 |
| `vw_tranche_summary`, `OPUS_ECM_TRANSACTION_TRANCHE` | L104 `SELECT TTR.*` | ~7 |
| `vw_tranche_summary`, `OB_DEAL_TRANCHE` | L269 `SELECT DTR.*` | ~25 |

`OB_ORDER` (the biggest table, 5.86M rows) already projects only its six needed
columns (`vw_order_detail` L142–143) — the pattern to copy.

**Honesty: Oracle very likely prunes unused projections through an inline view
already**, so this may buy nothing. It is zero-semantic-change and zero-risk, so
it is worth doing *if a cycle is already open for P5/P6/P7* — and is not worth
opening one for. **Measure before and after with the `execute=` phase timer;
do not claim a win without it.**

---
---

# TIER 3 — rejected, with the reasoning

## R1 — `MATCH_RANK` on the entity view  ❌ REJECT — not expressible as a column

`capital_markets_entity.yaml` **L187–196** carried this as a standing request when this
file was drafted. ✅ **It no longer does** — the current text opens
*"MATCH_RANK: DECLINED, do not re-request"* and records scope rule 1 as the
reason. The decline is done; only the *reason* is worth upgrading.

**There is a stronger reason, and it should replace the scope reason in the
ontology, because scope rules can be revisited and this cannot:**

> **Match rank is a function of the SEARCH TERM. A view column is not.**
> "Exact" means *equal to what the user typed*. `VW_ENTITY_SEARCH` has no access
> to what the user typed, so no stored value can express it. V1 did not have a
> `MATCH_RANK` column either — it had `is_exact`/`is_sub` **expressions computed
> per query**, which is a different thing wearing the same name.

**The redirect is cheap and lands in our own repo.** Tiering belongs in the SQL
builder, as an order key on a filter already marked `entity_name: true`
(`capital_markets_entity.yaml` L277) — conceptually
`ORDER BY CASE WHEN UPPER(name) = UPPER(:term) THEN 0
WHEN UPPER(name) LIKE UPPER(:term) || '%' THEN 1 ELSE 2 END` emitted ahead of
the existing activity keys. Class A, no view cycle.

Two limits to state honestly:
- Today `order` sorts on the **output alias** and every sort field must be a
  projected dimension (`SKILL.md` §0b), so this needs a builder change — it is
  not reachable from YAML alone.
- **Ordering is not gating.** Spec §4 wants *"if an exact match exists, return
  only exact matches"*, which needs `MAX(...) OVER ()`. Ordering puts the exact
  match at row 1 of 10, which is what the ontology's own contract already asks
  the agent to do (*"If an exact match exists it comes back INSIDE these rows —
  recognise it there"*, L52–55). Take the 90%; do not pretend the gate shipped.

**Action:** ✅ the decline itself is already recorded (L187–196). What remains is
to swap its *reason* from scope rule 1 to the search-term argument above, and to
open the builder item separately.

## R2 — A normalised UPPER status column  ❌ REJECT — redirect to config

Three variants, all rejected as view changes:

**(a) A new `DEAL_STATUS_UPPER` column** — barred by scope rule 1, and it earns
no exception because it removes **zero hops and zero latency** (see (c)).

**(b) `UPPER()` the existing column in place** — actively harmful. It changes
displayed values that non-agent consumers read: every view footer grants to
`DGLOBE_ORAAS_TABLEAU_ROLE`, `DGLOBE_TABLEAU_RESTRICTED_ROLE`,
`DGLOBE_ORAAS_RO_ROLE` and `DGLOBE` — **two Tableau roles plus two more
consumers**, not three Tableau roles. And it destroys the camelCase boundary that `SKILL.md` §11
depends on — *"`freeToTrade` reads 'Free to Trade'; camelCase never reaches the
user"* — because `FREETOTRADE` cannot be humanised back.

**(c) A canonicalising `CASE`** (`priced`→`Priced`) — the honest one, and still
a reject on cost/benefit. **The filter path is already correct**: the builder
wraps both sides in `UPPER()` for `eq`, `ne`, `like`, `in` and `not_in` on any
filter declared `case_insensitive: true` (BUILDER, `sql_builder.py`
`_filter_predicate` L62–75; V1-DOC addendum), and both status filters are so
declared (`capital_markets_deal.yaml` L369, `capital_markets_tranche.yaml` L364). The only thing
case variants break is **GROUP BY bucketing** — Q17 measured `priced` 4,231 /
`Priced` 111 and `announced` 2,187 / `Announced` 2,076, which split one bucket
into two and violate count honesty. That is worth fixing **where the value list
lives**, not with 2–4 days of view cycle — and ✅ **it already has been:**

- **Enumerated.** All 16 measured Q17 literals are now written out in
  `capital_markets_deal.yaml` L374–376 and `capital_markets_tranche.yaml` L367–372: Settled ·
  priced · Priced · announced · Announced · draft · freeToTrade · cancelled ·
  allocated · subject · archived · deleted · postponed · confidential ·
  `'Final Settled'` · NULL. ⚠️ **The original claim that "the ontology currently
  asserts `'Open'`/`'OPEN'`" is FALSE** — `capital_markets_deal.yaml` L380–384 already
  refutes exactly that, calling it a V1 single-view artefact and "NOT among the
  16 measured DCM literals".
- **Case-variant pairs stated** as the worked example, with the merge
  instruction (`capital_markets_deal.yaml` L680–683).
- **Merge in the answer** — `SKILL.md` §7b and §11 both carry it.

Nothing to do here beyond keeping those lists in sync with any re-measurement.

There is also no index payoff. V1-DOC's addendum offers normalisation as the
alternative to function-based indexes — but a **view** cannot be indexed at all,
and the three data views are far too large to materialise (**R8**). The
argument only lands on the entity object, where **P3** already covers it.

**⏳ One genuinely broken thing survives this rejection — see D4.** DCM
`deal_status` on the deal card is `MAX(ODT.STATUS)` across tranches (view L162),
and Q18's note is decisive: *"MAX() on text picks lowercase over uppercase by
codepoint. So the aggregate is unsound regardless of how often statuses differ."*
A deal with tranches `Settled` and `announced` reports `announced`, and
`VW_TRANCHE_SUMMARY` exposes the per-tranche status directly (view L244–245), so
the two objects contradict each other for the same deal. Fixing it needs a
status **precedence** (which status wins on a multi-tranche deal?), which is a
business answer nobody has given and Q18 was never run.

## R3 — Drop the `ROW_NUMBER` dedupes if the source adds unique constraints  ❌ REJECT

Round-4 open risk #1 is the motivation and it is sound: *"`OB_ORDER` (5.86M in
QA, more in PROD) and `OB_ECM_ORDER` are each wrapped in a window function to
remove 6 and 101 duplicate rows respectively."* Removing 6 rows by sorting 5.86M
looks absurd. It is still a reject, for four reasons:

1. **We have not measured that it costs anything.** Whether the window forces a
   sort depends on whether `ORDER_ID` is indexed — **open question D6**, one
   `ALL_IND_COLUMNS` query away. "Remove the dedupe" is currently speculation
   about a cost we have not observed.
2. **The prerequisite is not ours and is not fast.** It needs a unique
   constraint added at source, on tables owned by another team, for data that
   *currently violates it* — Q12 lists offenders on **every single join
   checked**, and V5 found 1,835 duplicate `(txn, tranche)` pairs. The
   constraint cannot be added until the duplicates are cleaned.
3. **PROD makes this worse, not better.** Round 4, verbatim: *"QA had exactly
   ONE unparseable tranche size and ONE duplicate `(deal, tranche)` key. Both
   are certain to be more common in PROD."* The dedupes are what make the grain
   invariant hold when that happens. Removing them trades a measured invariant
   for an unmeasured saving.
4. **The whole premise of the split is a grain the planner can trust.** V23/V24
   found *one* duplicate row each and both were treated as blocking, on exactly
   that reasoning.

**Accept the two prerequisites, decouple them from the view.** (a) **P4** —
confirm the indexes; that is where any real win lives, and it costs no cycle.
(b) Ask for the unique constraints as a **data-quality fix in its own right**,
because duplicate order rows are a source defect regardless of what our SQL
does. Do not couple view simplification to either. If both ever land, revisit —
with V22/V26/V27 re-run as the gate.

## R4 — Oracle Text (`CONTEXT`) index for contains-search  ❌ REJECT

V1-DOC names it as the mechanism that supports `LIKE '%X%'`, and it is the right
mechanism *in Oracle*. It is unreachable here: an Oracle Text index is only used
by a `CONTAINS(col, 'X') > 0` predicate, and our SQL is generated by the Trino
dialect against Starburst (`dialect: trino`, `catalog: dataglobe_oraas`) — the
builder emits `UPPER(col) LIKE UPPER(?)` (BUILDER) and there is no path for an
Oracle-specific text predicate to reach the base table. **P3** makes it
unnecessary anyway: a scan of 178k narrow materialised rows does not need an
index.

## R5 — Add `DISTINCT` to the ECM syndicate `LISTAGG`  ❌ REJECT

The asymmetry is real: `DEAL_SHARING_TYPE` uses
`COUNT(DISTINCT S.SYNDICATE_MEMBER_NAME) = 1` (view L200) while the member
`LISTAGG` has no `DISTINCT` (L167), so a tranche listing one bank twice can show
`syndicate_member_count = 2` **and** `DEAL_SHARING_TYPE = 'SOLO'`.

**Do not "fix" it by adding `DISTINCT`.** All four ECM syndicate `LISTAGG`s
(member, role, broker code, B&D flag — L167–170) share one
`WITHIN GROUP (ORDER BY S.BND_BROKER DESC, S.SYNDICATE_MEMBER_NAME)` and are
position-aligned by construction. Deduplicating the member list alone would
shift it against the other three and silently break the alignment that
`SKILL.md` §7 and §11 both depend on — the exact failure mode Q24 documented for
identifiers (6,223 tranches mis-zipped) and that this rewrite just fixed.

The likely truth is that a repeated member is **one bank in two roles**, in
which case both numbers are right and only the *label* misleads. That is an
ontology wording fix — and ✅ the guard is already in place: `SKILL.md` L255–256
says *"Do not cross-check with `syndicate_member_count`: it counts the list
without de-duplicating and can disagree with the flag."* See **D5** for the query
that sizes it; a zero answer lets that line be deleted, a non-zero answer
confirms it should stay.

## R6 — A precomputed `CURRENCY_COUNT` column  ❌ REJECT — superseded

Tempting: it turns `having currency_count gt 1` (non-pushable
`CARDINALITY(SPLIT(...))`) into a pushable `WHERE`. But **P1** gets the same
predicate pushdown with `currencies like '% | %'`, needs no column, no cycle and
no exception. Prefer the lookup over the computation, and prefer the free one
over the costed one.

## R7 — Drop `SETTLEMENT_TS` and `EXECUTION_STATUS`  ❌ REJECT — scope rule 2

`SETTLEMENT_TS` is 100% NULL (Q32 measured **22,347 pre-rewrite ECM deal rows** —
that figure is rows, not deals; the rewritten ECM branch is 18,399 deals, V1 —
zero populated either way) and the DCM branch casts NULL (view L145).
`EXECUTION_STATUS` is a constant on ECM and NULL on DCM (view L131–134). Both are
worthless to the agent and both **stay** — rule 2 keeps placeholders, with
`SETTLEMENT_CURRENCY` as the worked precedent.

✅ **The ontology fix this section asked for is already shipped.** `SKILL.md`
L137 now refuses settlement-date asks outright (*"the column exists and is 100%
empty (measured: zero populated deals)"*, offering pricing dates, the `Settled`
status, or settlement CURRENCY instead), and L454 states *"There is no
announced/created/launch date, and no settlement date either"* — which also
preserves spec §3.2 item 5's announced-date rule. The cited *"SKILL.md §9 L342"*
never held this text; L342 is `coupon_type` guidance. Nothing to do. Do not touch
the views.

## R8 — Materialise the deal / tranche / order views  ❌ REJECT — no measured pain

`VW_ORDER_DETAIL` is 5.87M rows (V4 + V22) — an MV of it is a second copy of the
order book with a refresh window measured in the tens of minutes, for no
measured problem. The deal branch runs in **0.9 s** (V1). TRACE puts a whole
`run_bqs_query` at 6.2 s of a 50 s turn and concludes *"the server is no longer
the lever."* **P3** applies only to the entity object because that is the only
one where the diagnostics measured a number (9.4 s / 79.4 s) larger than the
query it precedes.

---
---

# TIER 4 — deferred, one query each

None of these can be encoded as a rule or a fix until answered. All are cheap.
Do not guess any of them.

| # | Question | Why it blocks something | Query |
|---|---|---|---|
| **D1** | Does ECM `VW_DEAL_SUMMARY.CURRENCIES` render currency **ids** where the tranche object renders **names**? | The deal view LISTAGGs `TRANCHE_CURRENCY_ID` (view L103/L106); the tranche view resolves `TDC.CURRENCY_NAME` (L74/L162). If they differ, the two objects contradict each other in one answer and **P1's `currencies like '%USD%'` filter is wrong on ECM**. (The `'% \| %'` multi-currency idiom is unaffected.) | `SELECT CURRENCIES FROM DGSTREAM.VW_DEAL_SUMMARY WHERE PRODUCT='ECM' AND CURRENCIES IS NOT NULL FETCH FIRST 20 ROWS ONLY;` compared with `SELECT DISTINCT CURRENCY FROM DGSTREAM.VW_TRANCHE_SUMMARY WHERE PRODUCT='ECM' FETCH FIRST 20 ROWS ONLY;` |
| **D2** | Is DCM `SECTOR` populated? | Both rewritten views now source it from `ODT.ISSUER_SECTOR` (deal L160, tranche L222), but V1's dictionary says DCM sector is NULL and sector asks are ECM-only. Either the dictionary is stale or every DCM sector filter zero-rows. | `SELECT COUNT(*) AS ALL_, COUNT(SECTOR) AS WITH_SECTOR FROM DGSTREAM.VW_DEAL_SUMMARY WHERE PRODUCT='DCM';` |
| **D3** | Is `MAX(TPD.EXCHANGE)` lossy? | V11 measured `SECURITY_TYPE_NAME` (0 divergent keys — lossless) but **not** `EXCHANGE`, across Q12's 1,737 duplicate `(txn, tranche)` keys. A dual-listed tranche would silently report one venue, and this drives the NYSE example. | `SELECT COUNT(*) FROM (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID HAVING COUNT(DISTINCT EXCHANGE) > 1);` |
| **D4** | How many DCM deals hold genuinely different tranche statuses after case-folding? | Sizes **R2**'s surviving defect — the unsound `MAX(ODT.STATUS)` deal-level aggregate. Q18 was never run. If the answer is small, disclose; if large, a precedence rule is needed **and it is a business decision, not a SQL one**. | `SELECT COUNT(*) FROM (SELECT DEAL_ID FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY DEAL_ID HAVING COUNT(DISTINCT UPPER(STATUS)) > 1);` |
| **D5** | Can `syndicate_member_count` contradict `deal_sharing_type`? | Sizes **R5**. If zero, delete the ontology's cross-check advice (C09 says it is already redundant); if non-zero, it is a wording fix, not a view fix. | `SELECT COUNT(*) FROM (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID HAVING COUNT(*) > COUNT(DISTINCT SYNDICATE_MEMBER_NAME));` |
| **D6** | Is `OB_ORDER.ORDER_ID` indexed? (and the seven other keys in **P4**) | Decides whether the `ROW_NUMBER` dedupes sort 5.86M rows on every query — the entire premise of **R3**, and the sizing for **P4**. | `SELECT TABLE_NAME, INDEX_NAME, COLUMN_NAME, COLUMN_POSITION FROM ALL_IND_COLUMNS WHERE TABLE_OWNER='DGSTREAM' AND TABLE_NAME IN ('OB_ORDER','OB_ECM_ORDER','OB_DEAL_TRANCHE','OB_TRANCHE','OB_TRANCHE_RATING','OB_TRANCHE_SYNDICATE_MEMBER','OB_DEAL_ISSUER','OPUS_ECM_TRANSACTION','OPUS_ECM_TRANSACTION_TRANCHE','OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE') ORDER BY TABLE_NAME, INDEX_NAME, COLUMN_POSITION;` |
| **D7** | Is `OB_ECM_ORDER_IOI.LIMIT_VALUE` a limit **price** or an indication **amount**? | Round-4 open risk #2 plus V11's 14,341 ECM orders with several IOI limit points. If it is a price, ECM `order_amount` must never be aggregated at all — only displayed — and a `SUM` returns a plausible wrong number with no safety net (the old "it's empty on ECM so a SUM is harmless" doctrine is dead). A median near a share price settles it. | `SELECT MIN(LIMIT_VALUE) AS MIN_, MEDIAN(LIMIT_VALUE) AS MED_, MAX(LIMIT_VALUE) AS MAX_ FROM DGSTREAM.OB_ECM_ORDER_IOI;` |

Two more from the brief's open list, unblocking ontology text rather than any
view change, so they are not proposals here: the exact stored agency literals in
`ISSUER_RATINGS` (`SELECT AGENCY, COUNT(*) FROM DGSTREAM.OB_TRANCHE_RATING GROUP
BY AGENCY;` — the rewrite puts the agency name **inside** the string, view
L300–302, so `like '%MOODY%'` beats notation-guessing) and the domain of
`TENOR_PERIOD` (`SELECT TENOR_PERIOD, COUNT(*) FROM DGSTREAM.OB_DEAL_TRANCHE
GROUP BY TENOR_PERIOD;` — decides whether `'10-YEAR'` or `'10-Y'` is canonical,
and whether a numeric tenor column would even be writable).

---
---

# What this file deliberately does not propose

- **Any row-exclusion filter.** Q17 shows DCM carries `confidential` (14 rows /
  12 deals), `cancelled`, `deleted`, `archived`, `draft` and `postponed` with
  nothing filtering them, while ECM excludes Confidential/Withdrawn/Terminated
  at deal level and CANCELLED/DELETED/PASS plus `IS_OWNED = 'true'` at order
  level. Q19 shows 25 DCM order status combinations, unfiltered. This is real,
  it is cheap, and it is a **later batch** by explicit instruction. Until then
  it is a **disclosure**, and the ontology is the only place it can live: an ECM
  "confidential deals" ask returns zero **by construction**, while the same DCM
  ask returns rows. ✅ That disclosure is already written —
  `capital_markets_deal.yaml` L117–120 and the `deal_status` filter L382–388, plus
  `capital_markets_tranche.yaml` L372–377.
- **Any column beyond P5.** Every other gap identified in the current-state map
  — `deal_region` on the DCM deal branch, a real `EXECUTION_STATUS`, a numeric
  tenor, a `MATCH_RANK` — is either withdrawn by scope rule 1, impossible
  (R1), or blocked on D7/the tenor question.
- **Removing anything.** Rule 2, without exception.
- **Anything requiring a source-system change as a precondition.** Unique
  constraints (R3) and datatype alignment (P4's note) are asked for on their own
  merits, never as a gate on our work.

# Open items I could not resolve from the evidence

1. **The NULL-`ENTITY_ID` decision in P6(c)** — drop the rows or keep them
   ungrouped. A judgement call about what a useless candidate is worth, not a
   measurement.
2. **Status precedence for the DCM deal card** (D4's follow-on) — if two
   tranches of one deal disagree, which status is the deal's? No evidence in
   the diagnostics answers this; it is a banker's answer.
3. **Whether P8 buys anything at all.** Oracle may already prune the unused
   projections. Measurable only with the `execute=` phase timer, before and
   after, and not worth a cycle either way.
4. **Whether the `TRY_CAST` in P2b costs pushdown.** Same — measure with the
   phase timers, do not assume.
5. **The V25 outlier**: a DCM tranche with `max_size = 10,000,000,000,000` —
   "either a large JPY notional or a data error" (Round 4, open risk #3). Not a
   view fix until somebody looks at the row. If it is real, `largest_tranche_size`
   needs an outlier caveat; if it is a data error, it is a source ticket.
