# The server contract — what `models.py` and `sql_builder.py` actually do

Recorded 2026-08-07 from screenshots of `app/bqs/models.py`,
`app/bqs/sql_builder.py` and `app/mcpserver.py`. **These are extracts, not full
transcriptions** — I saw fragments, and a half-file that looks complete is worse
than an honest extract. Everything below is quoted or directly derived from what
was visible.

This file exists because the ontology YAML can declare anything; only this code
decides what any of it means.

---

## 1. Operators — the complete set

```python
class FilterOperator(str, Enum):
    EQ="eq"  NE="ne"  GT="gt"  GTE="gte"  LT="lt"  LTE="lte"
    IN="in"  NOT_IN="not_in"  BETWEEN="between"  LIKE="like"
    IS_NULL="is_null"  IS_NOT_NULL="is_not_null"
```

```python
_OP_SQL = {"eq":"=", "ne":"<>", "gt":">", "gte":">=",
           "lt":"<", "lte":"<=", "like":"LIKE"}
```

**There is no `not_like`, and no `OR`.** `_build_where` ends with
`" WHERE " + " AND ".join(where_parts)` — filters, computed filters and derived
filters are all ANDed together with no grouping. Any "A or B" ask has to be
expressed as `in [...]`, or not at all.

`value` semantics (from the field description): *"List for in/not_in; 2-item
list for between; omitted for is_null/is_not_null."*

## 2. `case_insensitive: true` is real — and it costs an index

```python
ci  = f.case_insensitive
lhs = f"UPPER({col})" if ci else col
def _bind(ph): return f"UPPER({ph})" if ci else ph
```

Both sides are wrapped: `UPPER(col) LIKE UPPER(?)`. The docstring says it
*"Only affects the string operators; ids/dates/numerics keep exact comparison"*,
and indeed `between`, `is_null` and `is_not_null` use the bare `col`.

> **Performance consequence, and it is not small.** Every case-insensitive filter
> is a function on the column, so **a plain B-tree index on that column cannot be
> used** — Oracle needs a *function-based* index on `UPPER(col)`. This applies to
> nearly every string filter we generate: `issuer_name`, `investor_name`,
> `deal_name`, `entity_name`, `sector`, `currency`, all the DCM taxonomies.
>
> This is very likely part of why entity search took ~5 s in v1. It belongs in
> the data-team findings as a concrete, cheap ask: **function-based indexes on
> `UPPER(...)` for the searched name columns**, not plain indexes.

## 3. `numeric: true` triggers a CAST — and we need it

```python
arg = dialect.numeric_cast(col_sql) if numeric else col_sql
return f"{agg.value}({arg})"
```

*"Value aggregations (SUM/AVG/MIN/MAX) require a numeric argument. Cast when the
governed measure is stored as text (e.g. Trino VARCHAR columns)."*

This is exactly the DDL-vs-JSON type mismatch we hit on `TRANCHE_SIZE` in v1. All
size/allocation/demand metrics in the four ontologies declare `numeric: true`.
**Do not remove it from a size metric** — the aggregate will misbehave on a
VARCHAR-backed column rather than fail loudly.

## 4. `list_count: true` is real

```python
if list_count:
    # The count is already numeric - do not numeric_cast it.
    return _agg_expr(agg, dialect.list_count(col), dialect, numeric=False)
```

So `currency_count` (deal) and `syndicate_member_count` (tranche) — `MAX` +
`list_count: true`, no `numeric:` — are correctly declared. The per-row value
becomes the count of the pipe-delimited list, then aggregates.

## 5. Computed-filter negation is well-defined, including NULLs

```python
pred = dialect.regexp_predicate(col, placeholder)
# Negation ("non-B&D", "not Citi"): the regexp helper COALESCEs NULLs to
# a non-matching sentinel, so NOT(...) is well-defined (NULLs pass the
# negation, i.e. a row with no B&D flag is correctly "non-B&D").
where_parts.append(f"NOT ({pred})" if cf.negate else pred)
```

Two things settled:
- Computed filters are **regex predicates over one governed column**, with the
  pattern bound as a parameter. The agent supplies a name and a token; the
  server owns the regex entirely.
- **`negate` handles NULLs correctly** — a tranche with no B&D flag *does* come
  back under a negated B&D filter. That is the right business answer and it is
  the reason `negate` is the correct tool rather than `ne`, which would silently
  drop those rows.

Still open: does `bill_and_deliver` accept a **token**? If yes,
`bill_and_deliver('citi', negate)` is exactly "did not bill". If it is
token-less, negating it means "no B&D designated at all" — a different
population.

## 6. `derived_filters` are server-authored column-vs-column predicates

```python
for df in plan.derived_filters:
    pred = df.predicate
    for tok, col in df.columns.items():
        pred = pred.replace("{" + tok + "}", dialect.quote_ident(col))
```

*"Governed derived-predicate names from discovery (e.g.
'settlement_currency_mismatch'). Token-less; the server owns the SQL."*

These express things a `BQSFilter` cannot — comparisons between two columns.
**Read what discovery offers before hand-building an equivalent**; we may
already have predicates for asks we are answering the long way.

## 7. ORDER BY references output ALIASES — so sort fields must be projected

```python
order_parts = [f'"{o.column_alias}" {o.direction}' for o in plan.orders]
sql += " ORDER BY " + ", ".join(order_parts)
```

Every select item is aliased to its **business name**
(`{sel_expr} AS "{alias}"`, metric as `"{metric_alias}"`). So an `order` field
must be the metric or a **projected dimension** — you cannot sort by something
you did not ask for.

This confirms the tiebreaker rule is not just good practice but a hard
constraint: the unique key you sort on has to be in `dimensions`, which is
exactly what `ontology_check.py` enforces.

## 8. There is a dedup path, and our ontologies do not use it

```python
dedup_key = plan.metric.dedup_key
if dedup_key:
    # Collapse base rows to one row per (dedup_key [+ grouping keys]) so the
    # metric column is not double-counted, then aggregate the distinct set.
```

A metric may declare `dedup_key`; the builder then wraps an inner
`SELECT … GROUP BY dedup_key + grouping keys` and aggregates the collapsed set
in the outer query. This is the v1 fan-out problem (deal_size repeated once per
tranche/order) solved in the compiler.

**No metric in any of the four ontologies declares `dedup_key`** — and that is
correct *if* the views really are grain-aligned, which is the entire premise of
the split. Two consequences worth holding on to:

- **If any metric ever needs `dedup_key`, that is a signal the view is not at
  its claimed grain** — fix the view, don't paper over it in the ontology.
- **`HAVING` is rejected on a deduplicated metric** (*"plain path only; the
  planner rejects HAVING combined with a deduplicated metric"*). Our
  `currency_count` and `syndicate_member_count` examples both rely on `HAVING`,
  so they work **only** while those metrics stay dedup-free. Adding a
  `dedup_key` to either would break them.

## 9. Confirmed shape of a generated query

Plain path:

```sql
SELECT <dim> AS "<business name>", …, <AGG>(<col>) AS "<metric name>"
FROM   <base_view>
WHERE  <ANDed predicates>
GROUP BY <dims>
HAVING <agg> <op> ?
ORDER BY "<alias>" <dir>, …
LIMIT  n
```

- Identifiers come only from the ontology; **all agent values are bound
  parameters** (`"""Builds parameterized, read-only SQL … The agent's SQL is
  never used."""`). SQL injection via a filter value is not a live risk.
- `time_grain` becomes `dialect.date_trunc(grain, col)` added to both SELECT and
  GROUP BY — so a "by month" ask is one request with correct buckets.

## 10. The tool surface (`mcpserver.py`)

```python
@mcp.tool()
def discover_business_terms(source: str | None = None) -> dict:
    # source: "If omitted, returns the catalog for ALL enabled sources"
    return _get_bqs_service().discover(source)

@mcp.tool()
def run_bqs_query(metric, source=None, dimensions=None, filters=None,
                  computed_filters=None, derived_filters=None, having=None,
                  time_grain=None, time_dimension=None, order=None,
                  limit=None) -> dict
```

**Discovery is scopeable.** Pass one source name and get one catalog. The agent
instruction's `(no arguments)` is what made it fetch four. `limit` is *"clamped
to the source's max_limit"* — so `max_limit: 5000` is a real ceiling.

A third tool is registered — `tool_echo_user_context`, a diagnostic returning
the resolved SOEID — which is why `mcp_tool_names` is pinned rather than `[]`.

`app = mcp.http_app(stateless_http=True)`: **no server-side session**, so
"discovery once per session" is purely agent behaviour and can only be enforced
by instruction.

The `run_bqs_query` docstring also settles the B&D question verbatim:

```
Add "negate": true to match rows that do NOT satisfy it - e.g.
"non-B&D" = bill_and_deliver with negate, "Citi non-B&D" =
syndicate_member "citi" plus bill_and_deliver with negate.
```

`bill_and_deliver` is **token-less**. Our recipe now matches this exactly.

## 11. The entitlement gate — one bug, three fail-open paths

Enforced in `run_bqs_query` before any SQL is built. Full analysis in
REVIEW-08 H2/H3. The bug, in one line:

```python
filters = [f for f in (request.get("filters") or [])
           if str(f.get("field","")).strip().lower() != "product"]   # drops the agent's scope
filters.append({"field":"product","op":"in","value": entitled})      # replaces it with entitlement
```

`requested` (what the user asked for) is computed, used only to decide denial,
then discarded. **A user entitled to ECM+DCM who asks for ECM gets both** — and
`total_deal_size` then sums share counts with notional money. Fix is to
intersect: `scope = [p for p in requested if p in entitled] or entitled`.

Fail-open paths, all currently "allow": entitlement module import failure
(`_ENTITLEMENT_AVAILABLE = False` → no gate), gate-ok-but-no-products (*"let the
query proceed unscoped"*), and `RUN_MODE` defaulting to `"local"` (which
disables the gate entirely).

## 12. The planner — validation, and the answer to `requires_filters`

**`requires_filters` IS ENFORCED.** It raises, it does not advise:

```python
def _check_required_filters(req, ms) -> None:
    """Performance guardrail: heavy metrics must be scoped by required filter(s)
    so the DB can prune instead of scanning/deduping the whole view."""
    if not ms.requires_filters: return
    present = {f.field for f in req.filters}
    missing = [rf for rf in ms.requires_filters if rf not in present]
    if missing:
        raise BQSError(..., code="missing_required_filter")
```

So the units guard we added across all four ontologies is real. **But note what
it checks: that the FIELD is PRESENT, not that it scopes to a single value.**
`requires_filters: [product]` is satisfied by
`{"field": "product", "op": "in", "value": ["ECM", "DCM"]}` — which is exactly
what the old entitlement gate injected. That is why the gate fix (§11) is the
load-bearing one; without it this guard cannot do the job it was added for.
It also runs *after* the gate has mutated `filters`, so an agent that omits
`product` entirely still passes.

Other planner facts worth holding:

- **`limit` defaults to `max_limit`**: `limit = req.limit or spec.max_limit`,
  then clamped. Omitting `limit` returns up to **5000 rows**, not a sensible
  default. Always set one on a listing.
- **`_HAVING_OPS = {eq, ne, gt, gte, lt, lte}`** — no `in`, no `between` in a
  HAVING clause.
- **`_resolve_orders`**: `allowed = {req.metric} | set(req.dimensions)` (+ the
  time-grain alias). Sorting on an unprojected field raises `bad_order_field` —
  the tiebreaker rule is a hard constraint, confirmed a second time.
- **`unsupported_intents` enforcement keys on the INTENT ID**, matched against
  the filter / computed-filter / dimension / metric *names* the request
  references. The `patterns:` list is **not used server-side at all** — it
  exists for the agent, via discovery. The practical consequence: an intent
  fires server-side only if its id is the name the agent would have invented.
  `investor_classification` is named correctly for that (an agent hallucinating
  a classification dimension hits it); `role_attribution` and `away_orders`
  never will, and are advisory only.
- **The only OR in the entire system** lives inside a computed filter: an
  alias's `codes` are each substituted into `pattern_template` and OR-joined
  into one regex. Everything else is ANDed.

  > That is the clean fix for the exchange problem. "NYSE **or** New York Stock
  > Exchange" is not expressible as two `like` filters, but it *is* expressible
  > as a governed `exchange_venue` computed filter whose `nyse` alias maps to
  > both codes. Same for a `refinancing` alias covering `Refinance` +
  > `Debt Repayment`, and a `usa` alias covering `United States` + `US`.
  > **Recommended next config step** — confirm the YAML key names against an
  > existing declared `computed_filters` block before writing them.

- Error codes the agent can receive: `unknown_filter`, `operator_not_allowed`,
  `bad_filter_value`, `unknown_computed_filter`, `bad_computed_filter`,
  `missing_token`, `unknown_token`, `unsupported_intent`, `unknown_metric`,
  `unknown_dimension`, `missing_required_filter`, `bad_time_grain`,
  `missing_time_dimension`, `unknown_time_dimension`, `bad_order_field`,
  `having_unsupported`, `unknown_derived_filter`, `bad_derived_filter` — plus
  `entitlement_denied` / `product_not_entitled` from the gate. Every one names
  exactly what to fix, which is why the skill's rule is "apply the exact change
  named and nothing else".

## 13. The ontology loader — three answers and one operational win

**`suggestable: true` fetches live `DISTINCT` values — on a 0-row result only.**

```python
# When true, this filter's column is a bounded, suggestable field: on a
# 0-row result the server may probe DISTINCT values and fuzzy-rank the
# agent's guess against them to return "did_you_mean" suggestions.
suggestable: bool = False
```

Recovery, not prevention. It fixes typo/casing traps that return nothing; it
cannot fix a filter that returns the *wrong rows*. See SKILL §7b.

**`values:` is NOT validated.**

```python
# Optional curated value list. When present, suggestions are ranked against
# these instead of a live DISTINCT probe (zero live queries). Best for small
# fixed enums (product, product_class).
values: list[str] = Field(default_factory=list)
```

So a curated list is a performance win (no live probe) and a partial list is a
quality *loss* (real values replaced by our guess). Declare it only for enums we
know completely.

**`grain` exists precisely to retire `dedup_key`:** *"For a grain-aligned view
(one physical row per grain) value metrics need no dedup_key — the row is
already unique."* Our four objects declaring `grain` and no `dedup_key` is the
intended design, confirmed in the source.

**HOT RELOAD — the operational win.** `OntologyRegistry` re-reads a YAML when
its **mtime changes**, on every `get()`:

```python
def get(self, source):
    self.reload()          # <- every call
    canonical = self.resolve(source)
```

> **Ontology changes take effect without redeploying the server.** In v1 a
> promote meant an app restart because bootstrap ran once. Here, dropping a
> corrected `capital_markets_order.yaml` into the ontology directory is live on the next
> query. That materially changes how we ship the config half of this work — and
> it means a bad YAML is live just as fast, so `ontology_check.py` before every
> copy is not optional.

**`BQS_ENABLED_SOURCES`** is an allow-list of source ids; anything not listed is
loaded and then ignored, with an explicit ENABLED/DISABLED summary logged at
startup. **All four object names must be in it** or the agent simply cannot see
that object. Promote-checklist item.

**Source resolution is forgiving but never silent** (`resolve`): omitted +
exactly one registered → that one; otherwise `Missing 'source'. Available
sources: [...]`. Case/separator folding (`ECM-DCM` → `capital_markets`), and a
sub-scope match on `_`-split parts — so `deal`, `tranche`, `order`, `entity`
each resolve uniquely, while `ecm` matches all four and raises.

**Discovery leaks no physical names** — `discovery()` returns business names,
descriptions, operators, `values`, `entity_name`, `allowed_tokens`,
`needs_token`, `grain`, `usage_notes`, `examples`, `response_features`. No
`column` anywhere. The confidentiality rule in the skill is enforced by
construction.

**A concrete cost of unscoped discovery:** `_generic_how_to_use()` — ~10 lines of
source-agnostic instructions — is **prepended to every source's `how_to_use`**.
Calling `discover_business_terms()` with no argument therefore returns that same
block **four times**, on top of four full catalogs.

**Not used by us: `as_of_date`.** A source may declare a governed availability
query; the server then returns `as_of_date` on every response so the agent can
render an accurate *"Data as of: &lt;Month YYYY&gt;"* header instead of guessing.
None of our four objects declare it. Worth asking whether the ECM/DCM views have
a data-availability date — bankers ask "how current is this?" and right now we
have no answer that isn't a guess.

---

## What this changed in our files

- `not_like` removed from four places; non-B&D rewritten onto
  `computed_filters` + `negate`.
- Operator whitelist added to `ontology_check.py`, taken verbatim from the enum.
- SKILL §0b gained the ANDed-filters, one-metric, `source`-mandatory,
  `time_grain` and order-must-be-projected rules.

## What it adds to the open list

| Item | Who |
|---|---|
| Function-based indexes on `UPPER(...)` for searched name columns — every case-insensitive filter defeats a plain index | data team |
| Does `bill_and_deliver` accept a token? | POC team |
| Which `derived_filters` exist? | POC team |
| Is `requires_filters` enforced? Still not seen — it is a `planner.py` concern, not `models.py` or `sql_builder.py` | POC team |
