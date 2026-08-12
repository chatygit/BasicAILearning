"""Deterministic SQL builder.

Builds parameterized, read-only SQL from a validated QueryPlan. Identifiers
come only from the governed ontology; all agent-supplied values are bound as
parameters. The agent's SQL is never used.
"""

from __future__ import annotations

from dataclasses import dataclass

from .dialects.base import BaseDialect
from .ontology import Aggregation
from .planner import QueryPlan

_OP_SQL = {
    "eq": "=",
    "ne": "<>",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "like": "LIKE",
}


@dataclass
class BuiltQuery:
    sql: str
    params: dict


def _agg_expr(
    agg: Aggregation, col_sql: str, dialect: BaseDialect, numeric: bool
) -> str:
    if agg == Aggregation.COUNT_DISTINCT:
        return f"COUNT(DISTINCT {col_sql})"
    if agg == Aggregation.COUNT:
        return f"COUNT({col_sql})"
    # Value aggregations (SUM/AVG/MIN/MAX) require a numeric argument. Cast when
    # the governed measure is stored as text (e.g. Trino VARCHAR columns).
    arg = dialect.numeric_cast(col_sql) if numeric else col_sql
    return f"{agg.value}({arg})"


def _metric_agg_sql(
    agg: Aggregation,
    column: str,
    dialect: BaseDialect,
    numeric: bool,
    list_count: bool,
) -> str:
    """Aggregate SQL for a metric, applying list_count when set (the per-row
    value becomes the count of a pipe-delimited list, then aggregated)."""
    col = dialect.quote_ident(column)
    if list_count:
        # The count is already numeric - do not numeric_cast it.
        return _agg_expr(agg, dialect.list_count(col), dialect, numeric=False)
    return _agg_expr(agg, col, dialect, numeric)


def _filter_predicate(i: int, f, dialect: BaseDialect, params: dict) -> str:
    """Build one WHERE predicate, mutating `params` with bound values.

    Case-insensitive text filters wrap both the column and each bound value in
    UPPER() so a case-mismatched guess still matches (parity with the legacy
    UPPER(col)=UPPER(val) behaviour). Only affects the string operators;
    ids/dates/numerics keep exact comparison.
    """
    col = dialect.quote_ident(f.column)
    ci = f.case_insensitive
    lhs = f"UPPER({col})" if ci else col

    def _bind(ph: str) -> str:
        return f"UPPER({ph})" if ci else ph

    if f.op == "is_null":
        return f"{col} IS NULL"
    if f.op == "is_not_null":
        return f"{col} IS NOT NULL"
    if f.op in ("in", "not_in"):
        names = []
        for j, v in enumerate(f.value):
            pname = f"f{i}_{j}"
            params[pname] = v
            names.append(_bind(dialect.placeholder(len(params), pname)))
        kw = "IN" if f.op == "in" else "NOT IN"
        return f"{lhs} {kw} ({', '.join(names)})"
    if f.op == "between":
        lo, hi = f"f{i}_lo", f"f{i}_hi"
        params[lo], params[hi] = f.value[0], f.value[1]
        return (
            f"{col} BETWEEN {dialect.placeholder(0, lo)} "
            f"AND {dialect.placeholder(0, hi)}"
        )
    pname = f"f{i}"
    params[pname] = f.value
    return f"{lhs} {_OP_SQL[f.op]} {_bind(dialect.placeholder(0, pname))}"


def _build_where(
    plan: QueryPlan,
    dialect: BaseDialect,
    params: dict,
    exclude_fields: set[str] | None = None,
) -> str:
    """Build the WHERE clause, mutating `params` with bound values.

    ``exclude_fields`` drops the named plain filters (by business name) from
    the clause. The zero-row suggestion probe uses it to keep the request's
    governed scope (product, dates, computed/derived filters) while removing
    the guessed values it is probing alternatives FOR — excluding only one
    guess at a time would let a second bad guess zero out every probe.
    """
    where_parts: list[str] = [
        _filter_predicate(i, f, dialect, params)
        for i, f in enumerate(plan.filters)
        if not (exclude_fields and f.business_name in exclude_fields)
    ]

    # Computed (regex) filters — pattern is always a bound parameter.
    for k, cf in enumerate(plan.computed_filters):
        col = dialect.quote_ident(cf.column)
        pname = f"cf{k}"
        params[pname] = cf.pattern
        pred = dialect.regexp_predicate(col, dialect.placeholder(0, pname))
        # Negation ("non-B&D", "not Citi"): the regexp helper COALESCEs NULLs to
        # a non-matching sentinel, so NOT(...) is well-defined (NULLs pass the
        # negation, i.e. a row with no B&D flag is correctly "non-B&D").
        where_parts.append(f"NOT ({pred})" if cf.negate else pred)

    # Derived (governed, server-authored) predicates — e.g. column-vs-column
    # comparisons. Tokens resolve to governed columns and are quoted here; the
    # predicate text is authored in the ontology, never agent input.
    for df in plan.derived_filters:
        pred = df.predicate
        for tok, col in df.columns.items():
            pred = pred.replace("{" + tok + "}", dialect.quote_ident(col))
        where_parts.append(f"({pred})")

    if where_parts:
        # NOTE: predicates are ANDed with no grouping — there is no OR anywhere
        # in a BQS request. The only OR the system can express is inside a
        # governed computed_filter, where an alias maps to several codes that
        # the planner OR-joins into one regex.
        return " WHERE " + " AND ".join(where_parts)
    return ""


def build_sql(plan: QueryPlan, dialect: BaseDialect) -> BuiltQuery:
    spec = plan.spec
    params: dict = {}

    metric_alias = plan.metric.business_name
    base = dialect.quote_ident(spec.base_view)
    where_sql = _build_where(plan, dialect, params)

    # Grouping keys shared by both paths: dimensions + optional time bucket.
    # Each entry is (select_expr, group_expr, output_alias).
    group_cols: list[tuple[str, str, str]] = []
    for d in plan.dimensions:
        col = dialect.quote_ident(d.column)
        group_cols.append((col, col, d.business_name))
    if plan.time_grain:
        tg = plan.time_grain
        bucket = dialect.date_trunc(tg.grain, dialect.quote_ident(tg.column))
        group_cols.append((bucket, bucket, tg.business_name))

    dedup_key = plan.metric.dedup_key
    if dedup_key:
        # ---- Dedup path ---------------------------------------------------
        # Collapse base rows to one row per (dedup_key [+ grouping keys]) so the
        # metric column is not double-counted, then aggregate the distinct set.
        inner_select: list[str] = []
        inner_group: list[str] = []
        for key_col in dedup_key:
            qc = dialect.quote_ident(key_col)
            inner_select.append(qc)
            inner_group.append(qc)
        outer_group_aliases: list[tuple[str, str]] = []
        for idx, (sel_expr, _grp_expr, alias) in enumerate(group_cols):
            inner_alias = f"g{idx}"
            inner_select.append(f'{sel_expr} AS "{inner_alias}"')
            inner_group.append(sel_expr)
            outer_group_aliases.append((inner_alias, alias))
        metric_inner = dialect.quote_ident(plan.metric.column)
        inner_select.append(f'{metric_inner} AS "m"')
        inner_group.append(metric_inner)

        inner_sql = (
            f"SELECT {', '.join(inner_select)} FROM {base}{where_sql} "
            f"GROUP BY {', '.join(inner_group)}"
        )

        outer_select: list[str] = []
        outer_group: list[str] = []
        for inner_alias, alias in outer_group_aliases:
            outer_select.append(f'd."{inner_alias}" AS "{alias}"')
            outer_group.append(f'd."{inner_alias}"')
        agg_arg = 'd."m"'
        outer_select.append(
            f'{_agg_expr(plan.metric.aggregation, agg_arg, dialect, plan.metric.numeric)} AS "{metric_alias}"'
        )
        sql = f"SELECT {', '.join(outer_select)} FROM ({inner_sql}) d"
        if outer_group:
            sql += " GROUP BY " + ", ".join(outer_group)
    else:
        # ---- Plain path ---------------------------------------------------
        select_parts = [
            f'{sel_expr} AS "{alias}"' for sel_expr, _g, alias in group_cols
        ]
        select_parts.append(
            f'{_metric_agg_sql(plan.metric.aggregation, plan.metric.column, dialect, plan.metric.numeric, plan.metric.list_count)} AS "{metric_alias}"'
        )
        sql = f"SELECT {', '.join(select_parts)} FROM {base}{where_sql}"
        if group_cols:
            sql += " GROUP BY " + ", ".join(g for _s, g, _a in group_cols)
        # HAVING (post-aggregation thresholds) — plain path only; the planner
        # rejects HAVING combined with a deduplicated metric.
        if plan.having:
            having_parts: list[str] = []
            for hi, h in enumerate(plan.having):
                hexpr = _metric_agg_sql(
                    h.aggregation, h.column, dialect, h.numeric, h.list_count
                )
                pname = f"h{hi}"
                params[pname] = h.value
                having_parts.append(
                    f"{hexpr} {_OP_SQL[h.op]} {dialect.placeholder(0, pname)}"
                )
            sql += " HAVING " + " AND ".join(having_parts)

    if plan.partition:
        # ---- Top-N-per-group wrapper --------------------------------------
        # Wrap the finished aggregate (either path — both end in output
        # aliases) and rank rows INSIDE each group. The agent never writes a
        # window function: it named business fields, the server owns the SQL.
        # rank_in_group is projected on purpose — it lets the agent caption
        # "#1 / #2 within <group>" without recomputing anything.
        p = plan.partition
        part_cols = ", ".join(f'q."{a}"' for a in p.by)
        rank_orders = [f'q."{o.column_alias}" {o.direction}' for o in plan.orders]
        # Deterministic tiebreak: ROW_NUMBER breaks ties arbitrarily, so two
        # runs could crown different "winners". Append the non-partition
        # aliases the request already projects.
        ranked_aliases = {o.column_alias for o in plan.orders} | set(p.by)
        for _sel, _grp, alias in group_cols:
            if alias not in ranked_aliases:
                rank_orders.append(f'q."{alias}" ASC')
        rn = (
            f"ROW_NUMBER() OVER (PARTITION BY {part_cols} "
            f"ORDER BY {', '.join(rank_orders)}) AS \"rank_in_group\""
        )
        sql = (
            f"SELECT * FROM (SELECT q.*, {rn} FROM ({sql}) q) ranked "
            f'WHERE "rank_in_group" <= {int(p.limit)}'
        )
        # Groups together, winners first inside each.
        final_order = [f'"{a}" ASC' for a in p.by] + ['"rank_in_group" ASC']
        sql += " ORDER BY " + ", ".join(final_order)
        sql += " " + dialect.limit_clause(plan.limit)
        return BuiltQuery(sql=sql, params=params)

    if plan.orders:
        # ORDER BY references the OUTPUT ALIAS, so every sort field must be the
        # metric or a projected dimension (enforced in planner._resolve_orders).
        order_parts = [f'"{o.column_alias}" {o.direction}' for o in plan.orders]
        sql += " ORDER BY " + ", ".join(order_parts)

    # OFFSET must precede LIMIT. The planner guarantees a deterministic ORDER BY
    # whenever offset > 0 — without one, page 2 can repeat or skip rows from
    # page 1, because nothing in SQL promises a stable order between runs.
    if plan.offset:
        sql += " " + dialect.offset_clause(plan.offset)
    sql += " " + dialect.limit_clause(plan.limit)
    return BuiltQuery(sql=sql, params=params)
