# QA GREEN ASKS — capability verdicts

Scope: the nine "green" asks. Each verdict was checked field-by-field against
`app/bqs/ontology/capital_markets_{deal,tranche,order,entity}.yaml`,
`adk/skills/text2sql-capital-markets/SKILL.md`, `views/vw_*.sql`, and
`app/bqs/{planner,sql_builder,models,formatter}.py`. Nothing was executed —
no warehouse access. Every field name below is declared, every operator below
is in that field's declared list. Where a literal is prose-only and never
measured in this environment, §4 says so.

Contract enforced throughout: one metric per request · filters ANDed, no OR ·
no joins · order on output aliases only · no window functions · no
`computed_filters`/`derived_filters` declared on any of the four objects
(grepped: zero hits).

---

## 1. Verdict table

| # | Ask | Verdict | Object | Reason |
|---|---|---|---|---|
| 2 | Top 5 ECM convertible-bond deals that were Live in 2025 | **SUPPORTED** | deal | One metric, all fields declared. "Live **in** 2025" is answerable only as *pricing* year — there is no status-effective date. |
| 3 | ECM warrants deals priced in the last year | **SUPPORTED** | deal | `deal_type` does not exist; the ask routes to `equity_type like %WARRANT%`. Everything else is declared. |
| 12 | List all deals with use of proceeds "Legal Redemptions", ECM, 2026 | **SUPPORTED** | deal | `Legal Redemptions` is a stored ECM literal; `use_of_proceeds eq` is declared. |
| 15 | Security identifiers for the tranches of deal "Suneel999" | **SUPPORTED** | tranche | Named deal goes inline as a `deal_name like` filter — no entity hop. `tranche_count` needs no product filter. |
| 17 | The top deal for each product type by largest tranche size (ECM, 2026) | **BLOCKED** | tranche | Top-N-per-group needs a partitioned rank. No window function exists anywhere in the SQL path. |
| 20 | Top 5 deals by tranche size — ECM Healthcare — with identifiers | **SUPPORTED-2HOP** | tranche | Ranking deals and listing their tranches are two grains; one request cannot do both. |
| 24 | Syndicate members on deal "RM_CONTRA_Sender" | **SUPPORTED** | tranche | All syndicate lists are declared dimensions on one object at one grain. |
| 25 | Deals where Citi was bill-and-deliver in 2026 | **SUPPORTED-2HOP** | tranche | Listing the deals and counting them are two metrics. |
| 27 | Which of those Citi B&D 2026 deals were SOLO on every tranche | **SUPPORTED-2HOP** | tranche | "Every tranche" is a set difference across two populations; `HAVING` cannot express it. Needs 2 requests beyond #25. |

**Counts — SUPPORTED 5 · SUPPORTED-2HOP 3 · BLOCKED 1.**

---

## 2. The exact requests

Conventions: dates are half-open (`gte` start, `lt` next boundary) per
`SKILL.md:546-547`. Every ranking/paged `order` ends on a unique key
(`SKILL.md:241-244`) — `deal_id`, or `deal_id` then `tranche_id` on tranche.
All string matching is case-insensitive server-side: `sql_builder.py:70-75`
wraps `UPPER()` on **both** sides for `eq`, `in` and `like` alike, so
`eq "Priced"` matches the stored `priced`, and `%WARRANT%` needs no manual
casing.

### Ask #2 — SUPPORTED (pricing-year reading)

```jsonc
{
  "source": "capital_markets_deal",
  "metric": "total_deal_size",
  "dimensions": ["deal_id", "deal_name", "issuer_name", "equity_type",
                 "deal_status", "deal_size", "last_priced"],
  "filters": [
    {"field": "product",     "op": "eq",   "value": "ECM"},
    {"field": "equity_type", "op": "like", "value": "%CONVERTIBLE BOND%"},
    {"field": "deal_status", "op": "eq",   "value": "Live"},
    {"field": "deal_size",   "op": "is_not_null"},
    {"field": "last_priced", "op": "gte",  "value": "2025-01-01"},
    {"field": "last_priced", "op": "lt",   "value": "2026-01-01"}
  ],
  "order": [{"field": "total_deal_size", "direction": "desc"},
            {"field": "deal_id",         "direction": "asc"}],
  "limit": 5
}
```

- `total_deal_size` carries `requires_filters: [product]` (deal.yaml:142-146),
  so `product eq ECM` is mandatory — and it is also load-bearing for **grain**:
  `grain: [product, deal_id]` (deal.yaml:52) asserts the *pair* is unique, so
  grouping on `deal_id` with product unpinned could collide an ECM and a DCM id.
- `%CONVERTIBLE BOND%` deliberately narrows the governed `%CONVERT%`
  (SKILL.md:362-363), because `%CONVERT%` also pulls `Convertible Preferred`
  (deal.yaml:430) and there is no way to drop it after ranking without changing
  the question. **On 0 rows, retry ONCE with `%CONVERT%`, project `equity_type`,
  and say you widened** (deal.yaml:439, SKILL.md:370-371).
- `deal_size is_not_null` is **mandatory, not cosmetic**. There is no
  `NULLS FIRST`/`NULLS LAST` anywhere in the repo (grepped);
  `sql_builder.py:223` emits a bare `ORDER BY "total_deal_size" DESC`, so null
  placement is the engine default and `capital_markets_entity.yaml:276` records
  it as UNVERIFIED. Without the guard, five size-less deals could occupy the
  whole "top 5".

Must be disclosed in the answer: ranked by **share count**, not money (no
price/FX/notional column exists — deal.yaml:244, SKILL.md:257-258, :261-262);
size-less deals excluded and how many; `equity_type` and `deal_status` are
`MAX()` collapses across the deal's transactions (deal.yaml:592-604; 115 ECM
keys carry two different statuses, deal.yaml:408-409); the window was applied to
**pricing** dates; ECM structurally excludes Confidential/Withdrawn/Terminated
(vw_deal_summary.sql:85-86).

### Ask #3 — SUPPORTED

```jsonc
{
  "source": "capital_markets_deal",
  "metric": "deal_count",
  "dimensions": ["deal_id", "deal_name", "issuer_name", "equity_type",
                 "deal_status", "last_priced"],
  "filters": [
    {"field": "product",     "op": "eq",   "value": "ECM"},
    {"field": "equity_type", "op": "like", "value": "%WARRANT%"},
    {"field": "deal_status", "op": "eq",   "value": "Priced"},
    {"field": "last_priced", "op": "gte",  "value": "2025-08-11"},
    {"field": "last_priced", "op": "lt",   "value": "2026-08-12"}
  ],
  "order": [{"field": "last_priced", "direction": "desc"},
            {"field": "deal_id",     "direction": "asc"}],
  "limit": 50
}
```

- `deal_count` is unit-free and declares no `requires_filters`
  (deal.yaml:177-179); `product eq ECM` is here because `equity_type` is NULL on
  every DCM row (deal.yaml:250).
- **`limit` must be 50, not 200.** `formatter.py:26` caps the response at 100
  rows and `:130` sets `next_offset = offset + len(records)`. A `limit: 200`
  fetches 200, hands the model 100, and reports `next_offset: 100` — so an
  agent that prints 50 per SKILL.md:585 and then pages from `next_offset`
  **never shows rows 51-100**. At `limit: 50` the SQL limit, the response cap,
  the printed page and `next_offset` all agree.
- Trailing window = both bounds, upper bound tomorrow-midnight
  (SKILL.md:546-549). Today is 2026-08-11, so `lt 2026-08-12`.
- Add a **second** request only to quote a total larger than the page:
  identical filters, `metric: deal_count`, `dimensions: []`, no order, no
  offset. That is legal — `sql_builder.py:196-204` emits a single-row aggregate
  when there are no group columns.

### Ask #12 — SUPPORTED

```jsonc
{
  "source": "capital_markets_deal",
  "metric": "deal_count",
  "dimensions": ["deal_id", "deal_name", "issuer_name",
                 "use_of_proceeds", "deal_status", "last_priced"],
  "filters": [
    {"field": "product",         "op": "eq",  "value": "ECM"},
    {"field": "use_of_proceeds", "op": "eq",  "value": "Legal Redemptions"},
    {"field": "last_priced",     "op": "gte", "value": "2026-01-01"},
    {"field": "last_priced",     "op": "lt",  "value": "2027-01-01"}
  ],
  "order": [{"field": "last_priced", "direction": "desc"},
            {"field": "deal_id",     "direction": "asc"}],
  "limit": 200
}
```

`limit: 200` is safe here **only because the answer pages** — page with
`offset` set to `next_offset` and every other field byte-identical. If QA wants
the simpler contract, use `limit: 50` as in #3.

- ECM-only by vocabulary: DCM stores just three use-of-proceeds literals
  (deal.yaml:349-350), so a DCM run is structurally empty, not "no deals".
- "In 2026" is the year to date. Say so.
- The count can be **short, never inflated**: `use_of_proceeds` is a `MAX()`
  collapse across the deal's transactions (deal.yaml:596), so a deal whose other
  transaction carries an alphabetically-higher label is missed. Ten of the 19
  ECM labels sort above `Legal Redemptions`. Bound: 43,718 transactions over
  41,779 deals means **at most ~4.6% of deals** have more than one transaction
  and are exposed at all (`_diagnostics-results.md:472`).
- "All the deals" is already a reduced population: `vw_deal_summary.sql:80-89`
  is an **INNER JOIN** that drops both the excluded statuses and every ECM
  transaction with no execution-status row — 41,779 source deals become 18,399
  in the view (`_diagnostics-results.md:464`, `:473`). For an ask whose first
  word is *List all*, that belongs in the answer.
- On 0 rows: report it as an environment-population fact. One sanctioned
  widening to `like '%REDEMPTION%'` (legal per deal.yaml:339; over-matches
  nothing in the known ECM list), announced as a widening. Never substitute a
  different label.

### Ask #15 — SUPPORTED

```jsonc
{
  "source": "capital_markets_tranche",
  "metric": "tranche_count",
  "dimensions": ["product", "deal_id", "deal_name", "tranche_id",
                 "tranche_name", "identifier_type", "identifier_value"],
  "filters": [
    {"field": "deal_name", "op": "like", "value": "%SUNEEL999%"}
  ],
  "order": [{"field": "deal_id",    "direction": "asc"},
            {"field": "tranche_id", "direction": "asc"}],
  "limit": 50
}
```

- **No entity hop.** SKILL.md:144 routes a named deal used as a FILTER inline;
  the entity object is default-off and costs 9.4s of a 79.4s budget
  (`capital_markets_entity.yaml:10-11`).
- **No `product` filter, `product` projected instead.** `tranche_count` is
  `COUNT_DISTINCT tranche_id` with no `requires_filters`
  (tranche.yaml:196-199), and tranche.yaml:786-791 explicitly blesses one
  request with `product` in dimensions covering both. Note the ontology
  contradicts itself here — tranche.yaml:785 says "Always set a product filter".
  Follow SKILL.md:267-271.
- `tranche_id` is in the GROUP BY, so `tranche_count` reads 1 on every row —
  this is a listing, and the metric is a formality.
- The identifier joins are LEFT (vw_tranche_summary.sql:185, :292), so a tranche
  with no identifiers still appears with NULLs. That is a real answer, not a gap.
- **`identifier_type` and `identifier_value` must be zipped by position into ONE
  cell** (SKILL.md:623-624). See the truncation hazard in §5 — this is the ask
  most exposed to it.

### Ask #24 — SUPPORTED

```jsonc
{
  "source": "capital_markets_tranche",
  "metric": "tranche_count",
  "dimensions": ["product", "deal_id", "deal_name", "tranche_id", "tranche_name",
                 "syndicate_member_name", "syndicate_role", "broker_code",
                 "bnd_broker", "bnd_bank", "deal_sharing_type"],
  "filters": [
    {"field": "deal_name", "op": "like", "value": "%RM_CONTRA_SENDER%"}
  ],
  "order": [{"field": "deal_id",    "direction": "asc"},
            {"field": "tranche_id", "direction": "asc"}],
  "limit": 25
}
```

- **Do not add `product eq ECM`.** The deal's product is unknown
  (`RM_CONTRA_Sender` is grep-negative across the repo). Hardcoding ECM turns a
  DCM deal into 0 rows, indistinguishable from "no such deal", and triggers an
  unscoped `SELECT DISTINCT` suggestion query per suggestable filter
  (`suggestions.py:140`). With `product` projected, a DCM deal instead appears
  with NULL `syndicate_role`/`broker_code` (vw_tranche_summary.sql:253-254) and
  the agent refuses with the `syndicate_on_dcm` message **from evidence**.
- Alignment contract: `syndicate_member_name`, `syndicate_role`, `broker_code`
  and `bnd_broker` share one `ORDER BY` inside the view
  (vw_tranche_summary.sql:172-175) and may be zipped by position **only when the
  element counts match**. `bnd_bank` uses a *different* sort key and a
  `BND_BROKER='true'` filter (`:176-177`) — it is outside the aligned set,
  never zip it. Use it as the position-free cross-check.
- Prefer the inline `(true)`/`(false)` suffix on a member token as the B&D flag
  when present (tranche.yaml:258, SKILL.md:307-308): it rides on the token, so
  it cannot shift. Strip it for display.
- `_` is a LIKE wildcard and nothing escapes it (`sql_builder.py:96-98` binds
  the value verbatim; no `ESCAPE` clause anywhere). The result is a **superset**,
  not zero rows — so the deal name must be verified from the returned
  `deal_name`/`deal_id`, not assumed.
- Disambiguation is free here: `deal_name` declares `entity_name: true` +
  `entity_id_column: deal_id` (tranche.yaml:294-295) and the request projects
  it, so `build_disambiguation` reads the returned rows with no extra query
  (`suggestions.py:342-348`). **But it dedupes on distinct name**, and
  tranche.yaml:238 says `deal_name` is not unique — two different `deal_id`s
  sharing one name raise no block. Count distinct `deal_id` off the rows.
- If 0 rows: `deal_id` offers no `like` (tranche.yaml:288). The only retry is
  `deal_id eq "RM_CONTRA_Sender"`, once (SKILL.md:146).

### Ask #20 — SUPPORTED-2HOP

One request cannot rank deals *and* list each one's tranche identifiers: the
ranking is deal-grain, the identifiers are tranche-grain, and projecting the
tranche fields would make the "top 5" a top-5 of tranches.

**Hop 1 — rank the deals.**

```jsonc
{
  "source": "capital_markets_tranche",
  "metric": "total_tranche_size",
  "dimensions": ["deal_id"],
  "filters": [
    {"field": "product",      "op": "eq", "value": "ECM"},
    {"field": "sector",       "op": "eq", "value": "Healthcare"},
    {"field": "tranche_size", "op": "gt", "value": 0}
  ],
  "order": [{"field": "total_tranche_size", "direction": "desc"},
            {"field": "deal_id",            "direction": "asc"}],
  "limit": 5
}
```

**Hop 1 must project `deal_id` and nothing else.** Adding `deal_name` or
`ticker` splits one deal into two group rows and silently corrupts the top-5:
on ECM, `DEAL_ID = T.DEAL_TRANSACTION_ID` (vw_tranche_summary.sql:64) while
`DEAL_NAME`/`TICKER`/`SECTOR` come from the per-**transaction** row (`:65-69`),
and one deal spans several transactions (deal.yaml:9-13). On DCM, `TICKER`
joins per tranche (`:226`, `:281-291`). Same for `currency` on a DCM variant —
scope it, never group by it.

**Hop 2 — list the tranches of those 5 deals.**

```jsonc
{
  "source": "capital_markets_tranche",
  "metric": "tranche_count",
  "dimensions": ["deal_id", "deal_name", "ticker", "sector", "tranche_id",
                 "tranche_name", "tranche_size", "currency",
                 "identifier_type", "identifier_value"],
  "filters": [
    {"field": "product", "op": "eq",  "value": "ECM"},
    {"field": "sector",  "op": "eq",  "value": "Healthcare"},
    {"field": "deal_id", "op": "in",  "value": ["<the 5 ids from hop 1>"]}
  ],
  "order": [{"field": "deal_id",    "direction": "asc"},
            {"field": "tranche_id", "direction": "asc"}],
  "limit": 50
}
```

At tranche grain `deal_name` and `ticker` are row facts, not group keys, so no
split is possible in hop 2. Hop 2 omits `tranche_size gt 0`, so it will show
0-size tranches that hop 1 excluded from the ranking — the totals still
reconcile, but say so.

### Ask #25 — SUPPORTED-2HOP

**Request 1 — the listing.**

```jsonc
{
  "source": "capital_markets_tranche",
  "metric": "tranche_count",
  "dimensions": ["product", "deal_id", "deal_name", "issuer_name",
                 "tranche_id", "tranche_name", "pricing_date", "bnd_bank"],
  "filters": [
    {"field": "bnd_bank",     "op": "like", "value": "%CITIGROUP GLOBAL MARKETS%"},
    {"field": "pricing_date", "op": "gte",  "value": "2026-01-01"},
    {"field": "pricing_date", "op": "lt",   "value": "2027-01-01"}
  ],
  "order": [{"field": "pricing_date", "direction": "desc"},
            {"field": "deal_id",      "direction": "asc"},
            {"field": "tranche_id",   "direction": "asc"}],
  "limit": 50
}
```

**Request 2 — the deal total** (a second metric = a second request;
`models.py:129` allows exactly one).

```jsonc
{
  "source": "capital_markets_tranche",
  "metric": "deal_count",
  "dimensions": ["product"],
  "filters": [ ...identical to request 1... ]
}
```

- `bnd_bank` offers **only** `like`, `is_null`, `is_not_null`
  (tranche.yaml:539) — by design, because ECM can hold several co-B&D banks in
  one pipe cell. `%CITIGROUP GLOBAL MARKETS%` follows the governing rule at
  tranche.yaml:517-520 / SKILL.md:301-303, which beats the bare `%CITIGROUP%`
  recipe at tranche.yaml:543.
- Neither request sets `product`, so the entitlement gate injects the caller's
  scope (`mcpserver.py:406-416`). An ECM-only caller must **never** be told
  "no DCM Citi B&D deals" — that is scope, not absence (SKILL.md:539-541).
- The date filter is tranche-level, so the population is *deals with at least
  one Citi-B&D tranche priced in 2026*. A deal whose other tranches priced in
  2025 is still counted and those tranches are absent from the listing. State
  that reading.
- NULL `pricing_date` rows are dropped silently by the bounds
  (tranche.yaml:727 offers `is_null`, so the NULL population is real).
- Caption the period from the response's `as_of_date`
  (`domain_query_service.py:242`, `formatter.py:143-145`), not the wall clock.
- Summing request 2's two product rows double-counts any `deal_id` present on
  both products — report the split, not the sum.

### Ask #27 — SUPPORTED-2HOP (two requests **beyond** #25)

"SOLO on every tranche" is a set difference. `HAVING` takes a catalog metric,
never an expression over a dimension (`planner.py:345-387`); no metric counts
SHARED tranches; and no deal-grain sharing field exists — grepping
`deal.yaml` + `vw_deal_summary.sql` for `solo|sharing|bnd|syndicate` returns
only `MAX(T.SYNDICATE_DEAL_NAME) AS DEAL_NAME`.

```
Hop A = #25 request 1, scoped ECM, projecting deal_sharing_type
        → the candidate deal_ids
Hop B:  source     capital_markets_tranche
        metric     tranche_count
        dimensions [deal_id, tranche_id, pricing_date, deal_sharing_type]
        filters    product           eq  "ECM"
                   deal_id           in  [ids from hop A]
                   deal_sharing_type eq  "SHARED"
        order      [{deal_id asc}, {tranche_id asc}]
Answer = hop A ids MINUS hop B ids
```

Two hard guards:

1. **Hop B must carry NO `pricing_date` filter.** "Every tranche" spans the
   deal's whole life. Re-applying the 2026 window would inspect only 2026
   tranches and would wrongly certify a deal whose 2025 tranche was SHARED.
   This is the workaround that silently changes the question.
2. **Hop A must be exhausted, not paged.** If hop A came back `truncated`
   (`formatter.py:124-139`), the `in` list is a *page* and the set difference is
   a page-derived total — forbidden by SKILL.md:614-617.

`deal_sharing_type` is never NULL (tranche.yaml:589), so `eq SHARED` loses
nothing. **Reject** the tempting shortcut of comparing this SOLO count against
the *deal* object's precomputed `tranche_count`: different populations, taken
before this view's status exclusions (SKILL.md:127-133, tranche.yaml:206-208).
Also note `deal_sharing_type` on DCM is computed from
`OB_TRANCHE_SYNDICATE_MEMBER.DEALER` (vw_tranche_summary.sql:313-323), a table
exposed nowhere else — so "project `syndicate_member_name` as SOLO evidence"
works on **ECM only**. #27 is ECM-scoped, so it does not bite here.

---

## 3. BLOCKED — Ask #17

**Ask:** the top deal for each ECM product type by largest tranche size, 2026.

**Missing capability:** a partitioned rank. `ROW_NUMBER() OVER (PARTITION BY
product_type ORDER BY tranche_size DESC)` — or `QUALIFY`, or a correlated
subquery — none of which the compiler can emit. `sql_builder.build_sql`
(`sql_builder.py:137-232`) produces exactly two shapes, a dedup collapse and a
plain aggregate, both SELECT / WHERE / GROUP BY / HAVING / ORDER BY / OFFSET /
LIMIT. `BQSRequest` (`models.py:116-169`) declares no rank, partition or
per-group field. A grep for `row_number|dense_rank|partition by|over (` across
`app/bqs/` returns **only** `suggestions.py:97 def _rank(...)`, a Python string
matcher, plus prose in `capital_markets_entity.yaml`. `LIMIT` is global
(`:231`) — it cuts the result, never each group.

**What IS possible today — a partial, self-verifying 2-hop.** Report it as
partial; do not present it as the answer.

- Hop 1: `metric largest_tranche_size`, `dimensions [product_type]`,
  filters `product eq ECM` + the 2026 pricing window, `limit 50`. Gives the
  maximum `M_t` per product type (≤27 labels, plus a possible NULL bucket).
- Hop 2: `metric largest_tranche_size`, `dimensions [product_type, deal_id,
  deal_name, tranche_id, tranche_name]`, same filters, ordered by size desc,
  **`limit 100`** (100 is the response cap at `formatter.py:26`; anything
  larger is discarded, anything smaller throws away resolvable types).
- Client-side: for each type `t`, the hop-2 row with `product_type = t` and size
  `= M_t` *is* that type's top deal, and hop 1 proves it independently.
- The shortfall is **self-detecting**: `row_count` vs `returned_rows` and
  `truncated`/`next_offset` (`formatter.py:113-130`) tell the agent exactly
  which types it resolved. It must **name the types it could not resolve**.
- Whether 100 rows covers all ~27 labels depends on the 2026 ECM size
  distribution, which is **not in any file** — unresolved, not "probably".

Also required in the answer: `GROUP BY` keeps NULLs, so a **NULL
`product_type` bucket** can appear and must be reported as "product type not
recorded" — never dropped, never merged into another label.

**Smallest fixes, cheapest first:**

| Fix | Layer | Effort | Effect |
|---|---|---|---|
| Add `in` to `tranche_size` operators (tranche.yaml:322-324) | **ontology** | ~5 min, 1 token | Upgrades the partial 2-hop to a **complete** one: `tranche_size in [M_1…M_K]` returns exactly the K maxima regardless of where they sit in the global size ordering. Does not create the 2-hop — it removes its only real limit. |
| Add a `top_n_per_group` entry to `unsupported_intents` + a per-group-ranking rule in SKILL.md (which today has none — grepped) | **prompt** | ~30 min | Stops the agent inventing a global top-N and calling it per-group. **Label it prompt, not server guard:** `planner._check_unsupported` (`:201-221`) matches an intent id against *field names only*, and no agent sends `top_n_per_group` as a field name, so it can never fire. |
| A `rank`/`partition_by` field on `BQSRequest` plus window emission in `sql_builder` | **planner** | days, new SQL shape + dialect work + tests | The only complete general fix. Not justified by one ask. |

---

## 4. Values QA should expect zero rows for

A 0-row result on any of these is **data absence or a spelling variant, not a
bug**. Note the evidence tiers: `values:` in the yaml is machine-checked at
authoring time; a `†` list in SKILL.md is *observed*; a prose list in a
description is neither. Crucially, `planner._validate_filter`
(`planner.py:120-149`) checks field existence, operator membership and value
*shape* only — **it never compares a value against `values:`**, so nothing
server-side rejects an unattested literal. It just returns nothing.

| Value | Ask | Where declared | Tier | Risk |
|---|---|---|---|---|
| `Convertible Bonds` | #2 | deal.yaml:430 prose; SKILL.md:344 marked **†** | observed, **never measured in this env** | Real. Asserted directly at SKILL.md:364 and tied to a production incident at :534-536, but never a measured DISTINCT. A stored `Conv. Bonds` would return 0. |
| `Live` | #2 | deal.yaml:396 prose, in a list the file itself calls "Indicative, not closed" | observed, **never measured** | Real, and **the same tier as `Convertible Bonds`** — the ECM status literals were explicitly not measured in the diagnostics (deal.yaml:391-393). |
| `Warrants` | #3 | deal.yaml:431 prose; SKILL.md:343 marked **†** | observed, never measured | Real, same tier. |
| `Legal Redemptions` | #12 | deal.yaml:346, tranche.yaml:450, SKILL.md:382 | observed; ECM list is **†** | Exact-spelling match across 5 repo locations, no variant anywhere. `USE_OF_PROCEEDS` appears in `_diagnostics-results.md` only as a DDL row (lines 68, 107) — the **column was never value-profiled**. |
| `Healthcare` | #20 | tranche.yaml:431, deal.yaml:320, SKILL.md:374; part of a stated **closed** 28-value list | strongest of the five | Low on ECM. On **DCM** the sector population is unmeasured (tranche.yaml:437-440) — a 0-row DCM sector query means "field unpopulated", not "no Healthcare bonds". |
| `SOLO` | #27 | tranche.yaml:581, in a real `values: ["SOLO","SHARED"]` list, and confirmed in the view (vw_tranche_summary.sql:207, :319) | **machine-declared + view-confirmed** | None. Never NULL (tranche.yaml:589). |
| `ECM` / `DCM` | all | deal.yaml:269, tranche.yaml:287 — real `values:` lists | machine-declared | None. |
| `%CITIGROUP GLOBAL MARKETS%` | #25/#27 | pattern, not a stored value | n/a | **See the cross-cutting defect below** — a genuine consistency bug, not data absence. |
| `Suneel999`, `RM_CONTRA_Sender` | #15, #24 | not in any file | test fixtures | Existence unknown. 0 rows ≠ bug. Note `_` is an unescaped LIKE wildcard, so #24 returns a **superset**. |

**Two distinct 0-row causes QA must separate on #2.** If ECM `Live` denotes a
pre-pricing state, then `deal_status eq Live` AND a `last_priced` window are
close to mutually exclusive, and the query returns 0 rows *with every literal
correct*. `did_you_mean` cannot diagnose that — it is an empty intersection, not
a bad value, and the agent must be able to say which one it hit.

**Cross-cutting value defect (#25 vs #27): the view's Citi tests are
case-SENSITIVE.** All three are Oracle `LIKE` against a mixed-case literal
`'%Citigroup Global%'` — vw_tranche_summary.sql:206 (ECM SOLO), :256 (DCM
`BND_BROKER`), :318 (DCM SOLO). Every agent-side filter is `case_insensitive`
and gets `UPPER()`-wrapped on both sides (tranche.yaml:540,
`sql_builder.py:70-72`). So `bnd_bank like '%CITIGROUP GLOBAL MARKETS%'`
matches any casing while `deal_sharing_type` only matches the exact mixed-case
spelling. If any `BD_BANK` value is stored uppercase, **#25's population and
#27's flag disagree by construction**, in a direction no filter change can fix.
Measure before changing anything:

```sql
SELECT DISTINCT BND_BANK FROM <view>
WHERE UPPER(BND_BANK) LIKE '%CITIGROUP GLOBAL%'
  AND BND_BANK NOT LIKE '%Citigroup Global%';
```

Fix (**view**, ~15 min): `UPPER()` both sides at :206, :256, :318.

---

## 5. Supported, but the agent must ASSUME something

These are where a wrong assumption produces a confident answer to a different
question. Each needs either a stated assumption in the answer or a clarifying
question first.

| # | Ambiguity | What the agent would assume | Consequence if wrong |
|---|---|---|---|
| **20** | **"Top 5 deal by tranche size" — 5 deals, or 5 tranches?** This is a bigger fork than SUM-vs-MAX. | Deals (the 2-hop above). | If the user meant tranches it is **one** request, not two — `dimensions [deal_id, deal_name, ticker, tranche_id, tranche_name, identifier_type, identifier_value]`, order by size desc, `limit 5`. **Ask before running.** |
| **20** | SUM of the deal's Healthcare tranches vs MAX single tranche | `total_tranche_size` (SUM). | A different top-5. State the aggregation in the answer. |
| **2** | "Top 5" **by what** | `deal_size` — the only size figure on the object. | Low risk, but state it: this is a **share count**, not money. No price, FX or notional column exists (deal.yaml:244, SKILL.md:261-262). |
| **2** | **"Live in 2025" — status *now*, or status *during 2025*?** | Current `deal_status = Live`, windowed on **pricing** date. | The status-history reading is genuinely **BLOCKED**: there is no status-effective date, `announced_date` and `settlement_date` are declared unsupported intents (deal.yaml:537-558), and no `last_priced` means a deal is undatable. Disclose the reading used. |
| **3** | "Last year" — calendar 2025, or trailing 12 months? | Trailing 12 months (`gte 2025-08-11`, `lt 2026-08-12`), per SKILL.md:546-549. | Calendar 2025 is a different set. One line in the answer resolves it. |
| **12** | "In 2026" is an incomplete year | Year to date. | Label it "2026 to date". Do **not** substitute a tomorrow-midnight bound — the governed rule reserves that for *trailing* windows, and using it here silently answers a different question. |
| **12** | "All the deals" | The view population. | Say the population: ECM excludes Confidential/Withdrawn/Terminated **and** transactions with no execution-status row (41,779 → 18,399). |
| **25** | "Deals in 2026" under a tranche-level date filter | Deals with ≥1 Citi-B&D tranche priced in 2026. | A deal's 2025 tranches are invisible in the listing but the deal is counted. State it. |
| **27** | "SOLO deals" | Citi was the **only syndicate member** on every tranche. | Never render SOLO as a bare "sole-managed" (tranche.yaml:583-589): a tranche solely managed by *another* bank reads SHARED, and so does a tranche with no syndicate rows. |
| **15 / 24** | Pipe-list cells | Zip aligned lists by position into one cell. | See the truncation defect below — this is the silent-corruption case. |

**The silent-corruption hazard on #15 and #24.** `formatter.py:46` caps a single
cell at 4,000 chars and appends **`…[truncated]`** (`:71-75`), applied to every
cell on the BQS response path. This is a **different marker** from the view's
own `...(N)` overflow (vw_tranche_summary.sql:172-177), and grepping
`adk/` and `app/bqs/ontology/` for `truncated]` returns **nothing** — the prompt
layer teaches only `...(N)` (SKILL.md:623-624, tranche.yaml:811). The nine wide
columns named at `formatter.py:31-36` include five that #24 projects and both
that #15 projects. Because `identifier_value` is longer per element than
`identifier_type`, it clips first, the element counts stop matching, and the zip
misaligns silently — or worse, two lists clipped to equal counts zip *wrongly*.
**Fix (prompt, ~10 min): one line in SKILL.md §11 beside the `...(N)` rule and
one at tranche.yaml:116-118 — treat `…[truncated]` exactly like `...(N)`.**

---

## 6. Cross-cutting defects found while verifying (all confirmed in code)

1. **`planner.py:462` — live `AttributeError` on the paging path.**
   `ResolvedOrder(column_alias=d.alias, ...)`, but `ResolvedDimension`
   (`planner.py:41-45`) declares only `business_name` and `column`. Any request
   with `offset > 0`, empty `order` and ≥1 dimension raises `AttributeError`
   instead of the deterministic dimension sort the comment at `:456-460`
   promises. **Reachable in normal operation**, because `formatter.py:131-139`
   instructs the agent to "repeat this EXACT request with offset=N". Untested —
   `tests/test_response_paging.py` covers the formatter and `offset_clause`
   only. **Fix: `column_alias=d.business_name`** — correct because
   `sql_builder.py:150` aliases each dimension as exactly `d.business_name` and
   `:223` sorts on that alias. One word.
2. **Every declared `unsupported_intent` on the tranche object is dead
   server-side.** `_check_unsupported` (`:201-221`) matches an intent id against
   `{filter fields} | {computed filter names} | {dimensions} | {metric}`. None
   of the six tranche ids (`syndicate_on_dcm`, `role_attribution`,
   `ecm_league_table`, `hedge_securities_count`, `selling_restrictions`,
   `pricing_economics`) is a field name, so none can ever fire. On the deal
   object only the field-shaped ids (`announced_date`, `settlement_date`,
   `issuer_country_domicile`) can. Fix: match on `patterns`, or key each intent
   to a triggering dimension.
3. **`…[truncated]` is invisible to the prompt layer** — §5 above.
4. **Case-sensitive Citi tests inside the view vs case-insensitive filters
   outside it** — §4 above.
5. **`tranche.yaml:785` contradicts `:786-791`** ("Always set a product filter"
   vs "one request with product in dimensions covers both"). #15 and #24 follow
   the latter. Fix: qualify `:785` to "always scope product, by filter or by
   projecting it as a dimension on a unit-free metric".
6. **The entitlement gate does not guarantee scoping.** `_entitlement_gate`
   returns at `mcpserver.py:356-357` (`if not entitled: return None`) before any
   injection, and `entitled` is empty on two fail-open paths
   (`:310-316`, `:336-343`). QA will see two different behaviours for #20 and
   #24 depending on `ECM_DCM_ENTITLEMENT_FEATURE_FLAG`. The gate *does* now
   intersect rather than replace (`:406-416`), so an explicit `product eq ECM`
   survives for a dual-entitled caller — but the planner comment at `:268-286`
   describing the old replace behaviour is stale.

---

## 7. Unresolved

- Nothing was executed. Whether `Suneel999` or `RM_CONTRA_Sender` exist, their
  product, tranche and identifier counts, and whether ECM `ticker` actually
  disagrees within any real deal are **unmeasured** — the split mechanism is
  proven from the view SQL, its frequency is not.
- NULL ordering on a `DESC` sort is engine default and **unverified**
  (`capital_markets_entity.yaml:276`). Pin it once; #2's guard makes the answer
  correct either way.
- `TRY_CAST` damage is undetectable from the response: `total_deal_size` is
  `numeric: true` (deal.yaml:144) so `sql_builder._agg_expr` (`:42`) applies
  `TRY_CAST(col AS DOUBLE)` (`trino.py:52-55`), which yields NULL for anything
  unparseable — and `deal_size is_not_null` does **not** protect against it,
  because a non-numeric string is NOT NULL yet casts to NULL. Projecting
  `deal_size` (as #2 does) at least makes it inspectable.
- Whether hop 2 of the #17 workaround covers all ~27 product types depends on
  the 2026 ECM size distribution, which is in no file read.
- DCM `sector` and DCM `ticker` populations are both unmeasured. `ticker` is
  additionally absent from the per-product applicability list at
  tranche.yaml:119-127 — a real ontology gap; smallest fix is to add it to the
  BOTH-PRODUCTS set with the same unmeasured-population caveat `sector` carries.
- `python3 -c "import yaml"` fails in this environment, so the specs could not
  be loaded through `app/bqs/ontology.py`. All ontology assertions above are
  textual reads of the yaml.
