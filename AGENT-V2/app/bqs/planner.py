"""Request validator + query planner.

Validates every business name in a BQS request against the governed ontology
using EXACT matching (no fuzzy guessing). Any unrecognized name fails with a
clear error. Produces a resolved QueryPlan mapping business names to physical
columns/aggregations — the only place where business<->schema mapping happens.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .models import BQSComputedFilter, BQSFilter, BQSRequest, BQSError
from .ontology import Aggregation, OntologySpec

# Rows an omitted `limit` resolves to. Deliberately small: see the note at the
# limit clamp in plan_query. Tune with BQS_DEFAULT_LIMIT.
_DEFAULT_ROW_LIMIT = 50


def _default_row_limit() -> int:
    try:
        value = int(os.getenv("BQS_DEFAULT_LIMIT", str(_DEFAULT_ROW_LIMIT)))
    except ValueError:
        return _DEFAULT_ROW_LIMIT
    return value if value > 0 else _DEFAULT_ROW_LIMIT


@dataclass
class ResolvedMetric:
    business_name: str
    column: str
    aggregation: Aggregation
    dedup_key: list[str] = field(default_factory=list)
    numeric: bool = False
    list_count: bool = False


@dataclass
class ResolvedDimension:
    business_name: str
    column: str


@dataclass
class ResolvedTimeGrain:
    business_name: str  # alias for the bucketed column in the output
    column: str
    grain: str


@dataclass
class ResolvedFilter:
    business_name: str
    column: str
    op: str
    value: object
    case_insensitive: bool = False


@dataclass
class ResolvedComputedFilter:
    business_name: str
    column: str
    # Server-composed regex pattern (already OR-joined + escaped). Bound as a
    # parameter at build time — never concatenated into SQL.
    pattern: str
    # When true, the predicate is wrapped in NOT (...) — "non-B&D" / "not Citi".
    negate: bool = False


@dataclass
class ResolvedOrder:
    column_alias: str
    direction: str


@dataclass
class ResolvedPartition:
    """Top-N-per-group: keep `limit` ranked rows inside each group of `by`.

    `by` holds OUTPUT ALIASES (business names), validated as a proper subset of
    the projected dimensions. The ranking order is plan.orders (defaulted to
    the metric descending when the request names none).

    `order_globally`: True when the REQUEST named an order — the surviving
    rows are then sorted by it across groups (e.g. "5 latest deals": rank
    tranches inside each deal by date, keep the latest, sort the deals by
    date, limit 5). False (defaulted ranking) keeps groups together."""

    by: list[str]
    limit: int
    order_globally: bool = False


@dataclass
class ResolvedHaving:
    """A resolved post-aggregation threshold (HAVING) on a metric."""

    business_name: str
    column: str
    aggregation: Aggregation
    numeric: bool
    op: str
    value: object
    list_count: bool = False


@dataclass
class ResolvedDerivedFilter:
    """A resolved governed derived predicate (template + token->column map)."""

    business_name: str
    predicate: str
    columns: dict[str, str]


@dataclass
class QueryPlan:
    spec: OntologySpec
    metric: ResolvedMetric
    dimensions: list[ResolvedDimension] = field(default_factory=list)
    filters: list[ResolvedFilter] = field(default_factory=list)
    computed_filters: list[ResolvedComputedFilter] = field(default_factory=list)
    derived_filters: list[ResolvedDerivedFilter] = field(default_factory=list)
    having: list[ResolvedHaving] = field(default_factory=list)
    time_grain: ResolvedTimeGrain | None = None
    orders: list[ResolvedOrder] = field(default_factory=list)
    partition: ResolvedPartition | None = None
    limit: int = 0
    offset: int = 0


_VALID_GRAINS = {"day", "week", "month", "quarter", "year"}


def _validate_filter(spec: OntologySpec, f: BQSFilter) -> ResolvedFilter:
    fs = spec.filters.get(f.field)
    if fs is None:
        raise BQSError(
            f"Unknown filter field '{f.field}' for source '{spec.source}'. "
            f"Known filters: {sorted(spec.filters)}",
            code="unknown_filter",
        )
    if f.op not in fs.operators:
        raise BQSError(
            f"Operator '{f.op.value}' not allowed on filter '{f.field}'. "
            f"Allowed: {[o.value for o in fs.operators]}",
            code="operator_not_allowed",
        )
    # Shape checks for value-carrying operators.
    #
    # value=None must be rejected here, not passed through: the model defaults
    # value to None, so a typo'd key ({"val": ...}) validates silently, and the
    # dialect renders None as the literal NULL — `col = NULL` is never true, so
    # the banker gets "no data" for a request whose real defect was a typo.
    if f.value is None and f.op.value not in ("is_null", "is_not_null"):
        raise BQSError(
            f"Filter '{f.field}' with op '{f.op.value}' requires a 'value'. "
            f"Use is_null/is_not_null to test for missing data.",
            code="bad_filter_value",
        )
    if f.op.value in ("in", "not_in") and not isinstance(f.value, (list, tuple)):
        raise BQSError(
            f"Filter '{f.field}' with op '{f.op.value}' needs a list value.",
            code="bad_filter_value",
        )
    if f.op.value in ("in", "not_in") and not f.value:
        raise BQSError(
            f"Filter '{f.field}' with op '{f.op.value}' got an EMPTY list — "
            f"that renders IN () which no warehouse accepts. Send the values, "
            f"or drop the filter.",
            code="bad_filter_value",
        )
    if f.op.value == "between" and (
        not isinstance(f.value, (list, tuple)) or len(f.value) != 2
    ):
        raise BQSError(
            f"Filter '{f.field}' 'between' needs a 2-item list.",
            code="bad_filter_value",
        )
    return ResolvedFilter(
        f.field, fs.column, f.op.value, f.value, fs.case_insensitive
    )


def _resolve_computed_filter(
    spec: OntologySpec, cf: BQSComputedFilter
) -> ResolvedComputedFilter:
    cspec = spec.computed_filters.get(cf.name)
    if cspec is None:
        raise BQSError(
            f"Unknown computed filter '{cf.name}' for source '{spec.source}'. "
            f"Known computed filters: {sorted(spec.computed_filters)}",
            code="unknown_computed_filter",
        )
    if "{value}" not in cspec.pattern_template:
        raise BQSError(
            f"Computed filter '{cf.name}' is misconfigured (no {{value}} slot).",
            code="bad_computed_filter",
        )

    # Resolve codes: fixed_codes short-circuits the token entirely.
    if cspec.fixed_codes:
        codes = list(cspec.fixed_codes)
    else:
        token = (cf.token or "").strip().lower()
        if not token:
            raise BQSError(
                f"Computed filter '{cf.name}' requires a token. "
                f"Allowed tokens: {sorted(cspec.aliases)}",
                code="missing_token",
            )
        alias = cspec.aliases.get(token)
        if alias is None:
            raise BQSError(
                f"Unknown token '{cf.token}' for computed filter '{cf.name}'. "
                f"Allowed tokens: {sorted(cspec.aliases)}",
                code="unknown_token",
            )
        codes = list(alias.codes)

    if not codes:
        raise BQSError(
            f"Computed filter '{cf.name}' resolved to no codes.",
            code="bad_computed_filter",
        )

    # Escape each governed code and substitute into the anchor template, then
    # OR-join. Only allow-listed codes ever reach the pattern.
    parts = [cspec.pattern_template.replace("{value}", re.escape(code)) for code in codes]
    pattern = "|".join(f"(?:{p})" for p in parts) if len(parts) > 1 else parts[0]
    return ResolvedComputedFilter(cf.name, cspec.column, pattern, cf.negate)


def _check_unsupported(spec: OntologySpec, req: BQSRequest) -> None:
    """Reject requests that explicitly target a governed unsupported intent.

    The agent should refuse these using discovery, but we enforce server-side:
    if any filter/computed-filter/dimension name matches a declared unsupported
    intent id, fail with the governed user_message instead of guessing.
    """
    if not spec.unsupported_intents:
        return
    referenced = (
        {f.field for f in req.filters}
        | {c.name for c in req.computed_filters}
        | set(req.dimensions)
        | {req.metric}
    )
    for intent_id, u in spec.unsupported_intents.items():
        if intent_id in referenced:
            raise BQSError(
                u.user_message or f"Intent '{intent_id}' is not supported.",
                code="unsupported_intent",
            )


def _resolve_metric(req: BQSRequest, spec: OntologySpec) -> ResolvedMetric:
    """Resolve the requested metric (exact match) against the ontology."""
    ms = spec.metrics.get(req.metric)
    if ms is None:
        raise BQSError(
            f"Unknown metric '{req.metric}' for source '{spec.source}'. "
            f"Known metrics: {sorted(spec.metrics)}",
            code="unknown_metric",
        )
    return ResolvedMetric(
        req.metric, ms.column, ms.aggregation, list(ms.dedup_key), ms.numeric,
        ms.list_count,
    )


def _resolve_dimensions(req: BQSRequest, spec: OntologySpec) -> list[ResolvedDimension]:
    """Resolve requested dimensions (exact match) against the ontology."""
    dims: list[ResolvedDimension] = []
    for dname in req.dimensions:
        ds = spec.dimensions.get(dname)
        if ds is None:
            raise BQSError(
                f"Unknown dimension '{dname}' for source '{spec.source}'. "
                f"Known dimensions: {sorted(spec.dimensions)}",
                code="unknown_dimension",
            )
        dims.append(ResolvedDimension(dname, ds.column))
    return dims


def _check_required_filters(req: BQSRequest, ms) -> None:
    """Performance guardrail: heavy metrics must be scoped by required filter(s)
    so the DB can prune instead of scanning/deduping the whole view. The agent
    should add the filter and retry."""
    if not ms.requires_filters:
        return
    present = {f.field for f in req.filters}
    missing = [rf for rf in ms.requires_filters if rf not in present]
    if missing:
        raise BQSError(
            f"Metric '{req.metric}' requires filter(s) {missing} to run "
            f"efficiently. Add a filter on each of {missing} and try again.",
            code="missing_required_filter",
        )
    # ---------------------------------------------------------------------
    # NOTE: this checks that the FIELD is PRESENT, not that it scopes to a
    # single value. `requires_filters: [product]` is satisfied by
    # {"field": "product", "op": "in", "value": ["ECM", "DCM"]}.
    #
    # That matters because mcpserver._entitlement_gate() REPLACES the agent's
    # product filter with exactly that multi-product filter for any dual-
    # entitled caller. So for its real purpose — stopping ECM share counts from
    # being summed with DCM notional money — this guard cannot fire.
    #
    # Fix lives in mcpserver.py (_entitlement_gate now intersects rather than
    # replaces). If we later want defence in depth here, the shape would be a
    # per-metric `requires_single_value: [product]` in the ontology plus a check
    # that op is 'eq' (or 'in' with len(value) == 1). That needs an
    # ontology.py change, so it is NOT done here.
    #
    # NOTE: this runs on req.filters AFTER the entitlement gate has
    # mutated them, so an agent that omits `product` entirely still passes.
    # ---------------------------------------------------------------------


def _resolve_time_grain(
    req: BQSRequest, spec: OntologySpec
) -> ResolvedTimeGrain | None:
    """Bucket a date dimension into day/week/month/quarter/year, if requested."""
    if not req.time_grain:
        return None
    grain = req.time_grain.strip().lower()
    if grain not in _VALID_GRAINS:
        raise BQSError(
            f"Unknown time_grain '{req.time_grain}'. "
            f"Allowed: {sorted(_VALID_GRAINS)}",
            code="bad_time_grain",
        )
    # The grain must reference a real date dimension. Prefer an explicit
    # 'time_dimension' the request names; else require the source to declare a
    # default date dimension.
    date_dim_name = req.time_dimension or spec.default_time_dimension
    if not date_dim_name:
        raise BQSError(
            "time_grain requires a time_dimension (or a source "
            "default_time_dimension).",
            code="missing_time_dimension",
        )
    ds = spec.dimensions.get(date_dim_name)
    if ds is None:
        raise BQSError(
            f"Unknown time_dimension '{date_dim_name}'.",
            code="unknown_time_dimension",
        )
    return ResolvedTimeGrain(date_dim_name, ds.column, grain)


def _resolve_orders(
    req: BQSRequest, time_grain: ResolvedTimeGrain | None
) -> list[ResolvedOrder]:
    """Order fields must reference the metric, a selected dimension, or the
    time-grain bucket alias."""
    allowed = {req.metric} | set(req.dimensions)
    if time_grain:
        allowed.add(time_grain.business_name)
    orders: list[ResolvedOrder] = []
    for o in req.order:
        if o.field not in allowed:
            raise BQSError(
                f"Order field '{o.field}' must be the metric or a selected "
                f"dimension. Allowed: {sorted(allowed)}",
                code="bad_order_field",
            )
        orders.append(ResolvedOrder(o.field, o.direction.value.upper()))
    return orders


_HAVING_OPS = {"eq", "ne", "gt", "gte", "lt", "lte"}
_TOKEN_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def _resolve_having(
    req: BQSRequest, spec: OntologySpec, primary: ResolvedMetric
) -> list[ResolvedHaving]:
    """Resolve HAVING thresholds. Each references a catalog metric compared to
    a value. Only supported on the plain (non-dedup) aggregation path, so both
    the primary metric and every HAVING metric must be non-deduplicated."""
    if not req.having:
        return []
    if primary.dedup_key:
        raise BQSError(
            f"HAVING is not supported together with the deduplicated metric "
            f"'{req.metric}'. Use a count/sum metric (e.g. deal_count, "
            f"investor_count, total_allocation) as the primary metric.",
            code="having_unsupported",
        )
    out: list[ResolvedHaving] = []
    for h in req.having:
        ms = spec.metrics.get(h.metric)
        if ms is None:
            raise BQSError(
                f"Unknown HAVING metric '{h.metric}' for source '{spec.source}'. "
                f"Known metrics: {sorted(spec.metrics)}",
                code="unknown_metric",
            )
        if ms.dedup_key:
            raise BQSError(
                f"HAVING metric '{h.metric}' is deduplicated and cannot be used "
                f"in a HAVING clause. Use a plain count/sum metric.",
                code="having_unsupported",
            )
        if h.op.value not in _HAVING_OPS:
            raise BQSError(
                f"HAVING operator '{h.op.value}' not allowed. "
                f"Use one of {sorted(_HAVING_OPS)}.",
                code="operator_not_allowed",
            )
        out.append(
            ResolvedHaving(
                h.metric, ms.column, ms.aggregation, ms.numeric, h.op.value,
                h.value, ms.list_count,
            )
        )
    return out


def _resolve_derived_filter(spec: OntologySpec, name: str) -> ResolvedDerivedFilter:
    """Resolve a governed derived predicate. Its {token}s must each map to a
    known dimension or filter column — never to raw agent input."""
    dspec = spec.derived_filters.get(name)
    if dspec is None:
        raise BQSError(
            f"Unknown derived filter '{name}' for source '{spec.source}'. "
            f"Known derived filters: {sorted(spec.derived_filters)}",
            code="unknown_derived_filter",
        )
    tokens = set(_TOKEN_RE.findall(dspec.predicate))
    if not tokens:
        raise BQSError(
            f"Derived filter '{name}' is misconfigured (no column tokens).",
            code="bad_derived_filter",
        )
    columns: dict[str, str] = {}
    for tok in tokens:
        src = spec.filters.get(tok) or spec.dimensions.get(tok)
        if src is None:
            raise BQSError(
                f"Derived filter '{name}' references unknown token '{tok}'.",
                code="bad_derived_filter",
            )
        columns[tok] = src.column
    return ResolvedDerivedFilter(name, dspec.predicate, columns)


def _check_product_applicability(req, spec) -> None:
    """Reject a request that uses a field the requested product cannot have.

    23+ columns are HARD NULL on one product — CAST(NULL AS ...) in the view's
    other UNION branch. Asking for investor_category while scoped to DCM cannot
    match anything, and the empty result reads to the agent as "no data" rather
    than "impossible combination", so it retries, widens, or reports nothing
    found. Spec section 3.2 asked for this to be mechanical rather than prose.

    WHY IT SHOWS UP AS AN ENVIRONMENT BUG. A caller entitled to ONE product gets
    `product eq '<that>'` injected by the entitlement gate, so every request is
    single-product scoped by accident and this never fires. A DUAL-entitled
    caller is scoped to both, so the same question that worked on a
    single-product login returns nothing. Production is the dual case.
    """
    requested: set[str] = set()
    for f in req.filters:
        if f.field == "product":
            v = f.value
            requested |= {str(x).upper() for x in (v if isinstance(v, list) else [v])}
    if not requested:
        requested = {"ECM", "DCM"}  # unscoped spans everything entitled

    used: list[tuple[str, list[str]]] = []
    ms = spec.metrics.get(req.metric)
    if ms is not None and getattr(ms, "products", None):
        used.append((req.metric, ms.products))
    for name in req.dimensions:
        d = spec.dimensions.get(name)
        if d is not None and getattr(d, "products", None):
            used.append((name, d.products))
    for f in req.filters:
        fs = spec.filters.get(f.field)
        if fs is not None and getattr(fs, "products", None):
            used.append((f.field, fs.products))

    for name, allowed in used:
        allow = {p.upper() for p in allowed}
        impossible = requested - allow
        if impossible:
            only = "/".join(sorted(allow))
            bad = "/".join(sorted(impossible))
            raise BQSError(
                f"'{name}' exists only on {only} — it is empty on {bad}. This "
                f"request is scoped to {'/'.join(sorted(requested))}, so it "
                f"cannot match anything. Add a filter product eq '{only}' if "
                f"you want the {only} answer, or drop '{name}'.",
                code="product_not_applicable",
            )


def plan_query(req: BQSRequest, spec: OntologySpec) -> QueryPlan:
    """Validate the request against the ontology and build a QueryPlan."""
    metric = _resolve_metric(req, spec)

    _check_unsupported(spec, req)

    _check_product_applicability(req, spec)
    dims = _resolve_dimensions(req, spec)
    filters = [_validate_filter(spec, f) for f in req.filters]
    computed_filters = [
        _resolve_computed_filter(spec, cf) for cf in req.computed_filters
    ]
    derived_filters = [
        _resolve_derived_filter(spec, name) for name in req.derived_filters
    ]

    _check_required_filters(req, spec.metrics[req.metric])

    having = _resolve_having(req, spec, metric)

    time_grain = _resolve_time_grain(req, spec)
    orders = _resolve_orders(req, time_grain)

    # Limit clamp.
    #
    # An omitted limit used to become spec.max_limit — 5000 rows. Those rows go
    # into an LLM context, and a listing that resolved to a few thousand of them
    # ended the turn with RESOURCE_EXHAUSTED at ~300k tokens. "No limit given"
    # means the agent did not think about size, which is the case that most
    # needs a small answer, not the largest one the object allows.
    #
    # This is the SQL limit. The response is capped again, independently, in
    # domain_query_service — the two are different concerns: this one bounds
    # what the warehouse does, that one bounds what the model reads.
    limit = req.limit or _default_row_limit()
    limit = min(limit, spec.max_limit)

    offset = max(0, int(req.offset or 0))
    if offset and not orders:
        # OFFSET without ORDER BY is not paging, it is sampling: nothing in SQL
        # promises two runs order rows the same way, so page 2 can repeat or
        # skip rows from page 1. A GROUP BY guarantees distinct dimension
        # tuples, so ordering by every projected dimension is fully
        # deterministic — do that rather than refuse. The time-grain bucket is
        # part of the group too: without it, a monthly series inside one
        # dimension value ties on every sort key and pages non-deterministically
        # — silently wrong trend data, the worst kind.
        orders = [
            ResolvedOrder(column_alias=d.business_name, direction="ASC") for d in dims
        ]
        if time_grain:
            orders.append(
                ResolvedOrder(
                    column_alias=time_grain.business_name, direction="ASC"
                )
            )
        if not orders:
            raise BQSError(
                "offset needs a deterministic sort, and this request has no "
                "dimensions and no time_grain to order by. An aggregate with "
                "neither returns a single row, so there is nothing to page "
                "through — drop the offset.",
                code="offset_without_order",
            )

    partition = None
    if req.per_partition_limit and not req.partition_by:
        raise BQSError(
            "per_partition_limit only makes sense with partition_by — name "
            "the dimension(s) that define the groups.",
            code="bad_partition",
        )
    if req.partition_by:
        projected = [d.business_name for d in dims]
        if time_grain:
            projected.append(time_grain.business_name)
        allowed = set(projected)
        bad = [p for p in req.partition_by if p not in allowed]
        if bad:
            raise BQSError(
                f"partition_by fields {bad} must also be projected — add them "
                f"to `dimensions` (or use the time_grain bucket). Projected: "
                f"{sorted(allowed)}",
                code="bad_partition",
            )
        if len(set(req.partition_by)) >= len(allowed):
            raise BQSError(
                "partition_by lists EVERY projected dimension, so each group "
                "is a single row and nothing gets ranked. Partition by the "
                "grouping dimension(s) only (e.g. sector) and keep the "
                "identifying ones (deal_name, deal_id) out of partition_by.",
                code="bad_partition",
            )
        if offset:
            raise BQSError(
                "offset cannot be combined with partition_by — ranked groups "
                "are not a pageable stream. Narrow the partitions with "
                "filters, or raise per_partition_limit.",
                code="bad_partition",
            )
        explicit_order = bool(req.order)
        if not orders:
            # The natural reading of "top per group" ranks by the metric.
            orders = [
                ResolvedOrder(
                    column_alias=metric.business_name, direction="DESC"
                )
            ]
        partition = ResolvedPartition(
            by=list(dict.fromkeys(req.partition_by)),
            limit=req.per_partition_limit or 1,
            order_globally=explicit_order,
        )

    return QueryPlan(
        spec=spec,
        metric=metric,
        dimensions=dims,
        filters=filters,
        computed_filters=computed_filters,
        derived_filters=derived_filters,
        having=having,
        time_grain=time_grain,
        orders=orders,
        partition=partition,
        limit=limit,
        offset=offset,
    )
