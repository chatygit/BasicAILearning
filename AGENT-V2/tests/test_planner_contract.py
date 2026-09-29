"""The planner contract: paging determinism, product applicability, partition_by.

Every case here pins a shipped bug or a 2026-08-11 fix:

  - The offset fallback ORDER BY once shipped as `d.alias` — an AttributeError
    on EVERY paged listing without an explicit order (page 2 crashed).
  - The fallback ignored the time_grain bucket, so monthly buckets tied inside
    a dimension and pages could repeat or skip months — silently wrong trends.
  - _check_product_applicability is what turns "ECM-only FILTER asked on DCM"
    into a rejection instead of an empty result read as "no data". It only
    fires for dual-entitled callers — which is what PRODUCTION has — so a
    single-product local login can never reproduce its absence. A column that
    is only LISTED never decides the product (user ruling 2026-09-29): it is
    blank on the other product's rows, and the plan names it in blank_dims.
  - partition_by (top-N-per-group) closed QA ask #17, the one true V1
    architectural regression. Misuse must fail with code bad_partition, not
    compile into wrong SQL.
  - A filter whose value key was typo'd used to render `col = NULL` (never
    true) and return 0 rows as "no data".

Runs under pytest, or standalone (`python3 tests/test_planner_contract.py`).
The planner imports pydantic/yaml; where they are absent the cases SKIP LOUDLY
(same convention as test_response_paging.py) — the load-bearing facts are also
pinned textually by _review/ontology_check.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).parent.parent / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

SKIPPED: list[str] = []


def _deps():
    try:
        import pydantic  # noqa: F401
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True


def _spec(source: str):
    from bqs.ontology import OntologyRegistry

    return OntologyRegistry(str(APP / "bqs" / "ontology")).get(source)


def _plan(body: dict):
    from bqs.models import BQSRequest
    from bqs.planner import plan_query

    req = BQSRequest.model_validate(body)
    return plan_query(req, _spec(body["source"]))


def _expect_code(body: dict, code: str, why: str):
    from bqs.models import BQSError

    try:
        _plan(body)
    except BQSError as e:
        assert e.code == code, f"expected code {code}, got {e.code}: {e.message}"
        return e
    raise AssertionError(f"accepted, but should have been rejected ({why})")


# --------------------------------------------------------------------------
# paging fallback determinism
# --------------------------------------------------------------------------

def test_offset_without_order_sorts_every_dimension():
    if not _deps():
        SKIPPED.append("offset fallback (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_deal",
        "metric": "deal_count",
        "dimensions": ["sector", "deal_name"],
        "offset": 50,
        "limit": 50,
    })
    # The exact attribute that shipped broken: ResolvedOrder.column_alias built
    # from d.business_name (d.alias crashed here on every unordered page 2).
    assert [o.column_alias for o in plan.orders] == ["sector", "deal_name"]
    assert all(o.direction == "ASC" for o in plan.orders)


def test_offset_fallback_includes_time_grain_bucket():
    if not _deps():
        SKIPPED.append("offset+time_grain fallback (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_deal",
        "metric": "deal_count",
        "dimensions": ["sector"],
        "time_grain": "month",
        "offset": 10,
    })
    aliases = [o.column_alias for o in plan.orders]
    assert plan.time_grain is not None
    assert plan.time_grain.business_name in aliases, (
        "the time-grain bucket must join the fallback sort — without it the "
        "months inside one sector tie and page 2 repeats or skips buckets"
    )


def test_offset_with_nothing_to_sort_is_refused():
    if not _deps():
        SKIPPED.append("bare offset refusal (pydantic/yaml not installed)")
        return
    _expect_code(
        {"source": "capital_markets_deal", "metric": "deal_count", "offset": 10},
        "offset_without_order",
        "no dimensions and no time_grain: single row, nothing to page",
    )


# --------------------------------------------------------------------------
# product applicability — the dual-entitlement bug class
# --------------------------------------------------------------------------

def test_ecm_only_filter_on_dcm_is_rejected_not_empty():
    if not _deps():
        SKIPPED.append("product applicability (pydantic/yaml not installed)")
        return
    # A FILTER on an ECM-only column under an explicit DCM scope cannot match
    # a row (the column is hard NULL there): rejected, never an empty result
    # read as "no data". investor_category_key stays ECM-only (investor_category
    # itself was de-scoped in release 3).
    e = _expect_code(
        {
            "source": "capital_markets_order",
            "metric": "order_count",
            "filters": [
                {"field": "product", "op": "eq", "value": "DCM"},
                {"field": "investor_category_key", "op": "eq", "value": "LONG_ONLY"},
            ],
        },
        "product_not_applicable",
        "investor_category_key is hard NULL on every DCM row",
    )
    assert "investor_category_key" in e.message


def test_same_filter_on_ecm_is_accepted():
    if not _deps():
        SKIPPED.append("product applicability happy path (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "order_count",
        "filters": [
            {"field": "product", "op": "eq", "value": "ECM"},
            {"field": "investor_category_key", "op": "eq", "value": "LONG_ONLY"},
        ],
    })
    assert plan.metric.business_name == "order_count"
    assert plan.narrowed_product is None and plan.blank_dims == {}


def test_listed_single_product_column_is_projected_not_rejected():
    # User ruling 2026-09-29 (dual-entitled Fidelity prompt): a column that is
    # only LISTED never decides the product — it is one view, and the column
    # is simply blank on the other product's rows. An explicit DCM scope plus
    # an ECM-only dimension therefore plans, and the plan names the blank.
    if not _deps():
        SKIPPED.append("listed single-product column (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "order_count",
        "dimensions": ["investor_category_key"],
        "filters": [{"field": "product", "op": "eq", "value": "DCM"}],
    })
    assert plan.narrowed_product is None
    assert plan.blank_dims == {"investor_category_key": "ECM"}
    assert [d.business_name for d in plan.dimensions] == ["investor_category_key"]


def test_dual_scope_with_ecm_only_filter_narrows_to_ecm():
    # UAT run 5 (2026-09-24), prompt 37: five queries because a both-products
    # scope plus an ECM-only field was rejected twice. "Either product" plus a
    # FILTER that can only match one of them IS the product — scope to it and
    # say so.
    if not _deps():
        SKIPPED.append("product narrowing (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "order_count",
        "filters": [
            {"field": "product", "op": "in", "value": ["ECM", "DCM"]},
            {"field": "offering_type", "op": "eq", "value": "IPO"},
        ],
    })
    assert plan.narrowed_product == "ECM"
    assert plan.narrowed_by == ["offering_type"]
    prods = [f for f in plan.filters if f.business_name == "product"]
    assert len(prods) == 1 and prods[0].op == "eq" and prods[0].value == "ECM", (
        "the product filter must be rewritten to eq ECM — a scope that still "
        "spans DCM would make the planner reject the field again"
    )


def test_unscoped_request_with_dcm_only_filter_narrows_to_dcm():
    if not _deps():
        SKIPPED.append("product narrowing, unscoped (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "order_count",
        "filters": [{"field": "tenors", "op": "like", "value": "%5%YEAR%"}],
    })
    assert plan.narrowed_product == "DCM"
    assert [f.value for f in plan.filters if f.business_name == "product"] == ["DCM"]


def test_explicit_single_scope_is_never_narrowed():
    # The agent said ECM; a DCM-only FILTER is a contradiction, not a hint.
    if not _deps():
        SKIPPED.append("product narrowing, explicit scope (pydantic/yaml not installed)")
        return
    _expect_code(
        {
            "source": "capital_markets_order",
            "metric": "order_count",
            "filters": [
                {"field": "product", "op": "eq", "value": "ECM"},
                {"field": "tenors", "op": "like", "value": "%5%YEAR%"},
            ],
        },
        "product_not_applicable",
        "an explicit ECM scope with a DCM-only filter must still be rejected",
    )


def test_dual_scope_with_conflicting_single_product_filters_is_rejected():
    if not _deps():
        SKIPPED.append("product narrowing, conflict (pydantic/yaml not installed)")
        return
    e = _expect_code(
        {
            "source": "capital_markets_order",
            "metric": "order_count",
            "filters": [
                {"field": "product", "op": "in", "value": ["ECM", "DCM"]},
                {"field": "offering_type", "op": "eq", "value": "IPO"},
                {"field": "tenors", "op": "like", "value": "%5%YEAR%"},
            ],
        },
        "product_not_applicable",
        "an ECM-only filter beside a DCM-only filter cannot be narrowed either way",
    )
    assert "offering_type" in e.message or "tenors" in e.message


def test_mixed_product_dimensions_run_as_one_query_on_a_dual_scope():
    # The Fidelity prompt (2026-09-29): Deal Name, Pricing Date, Deal Size,
    # Offering Type (ECM-only), Deal Type (product_class, DCM-only), order and
    # allocation for one investor across BOTH products. Before this ruling the
    # two listed columns read as an ECM/DCM contradiction and the request was
    # rejected; the agent then planned a per-product split and gave up. Now:
    # one request, no narrowing, no rejection, both columns projected, and
    # the plan names them as blank by design.
    if not _deps():
        SKIPPED.append("mixed-product dimensions (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "row_count",
        "dimensions": ["deal_name", "pricing_date", "deal_size", "offering_type",
                       "product_class", "order_demand_qty", "order_allocation",
                       "product"],
        "filters": [
            {"field": "product", "op": "in", "value": ["ECM", "DCM"]},
            {"field": "investor_name", "op": "like", "value": "%FIDELITY MANAGEMENT%"},
            {"field": "pricing_date", "op": "gte", "value": "2024-09-29"},
        ],
        "limit": 50,
    })
    assert plan.narrowed_product is None and plan.narrowed_by == []
    assert plan.blank_dims == {"offering_type": "ECM", "product_class": "DCM",
                               "equity_type": "ECM"}, (
        "blank_dims is computed AFTER the auto-projection, so the added "
        "equity_type is named as blank on DCM rows too (PR bot 2026-09-29)"
    )
    names = [d.business_name for d in plan.dimensions]
    assert "offering_type" in names and "product_class" in names
    assert "equity_type" in names, "a unit column is projected → equity_type auto-added"
    prods = [f for f in plan.filters if f.business_name == "product"]
    assert len(prods) == 1 and prods[0].op == "in", "the both-products scope must survive"


def test_submitted_bid_alone_does_not_trigger_equity_type():
    # PR bot 2026-09-29: demand_as_submitted is the bid as placed, in
    # demand_unit (a currency or percent bid) — the security says nothing
    # about it, so it must not pull in the unit note by itself.
    if not _deps():
        SKIPPED.append("submitted bid unit (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "row_count",
        "dimensions": ["investor_name", "demand_as_submitted", "demand_unit"],
        "filters": [
            {"field": "product", "op": "eq", "value": "ECM"},
            {"field": "deal_id", "op": "eq", "value": "1447528575"},
        ],
        "limit": 5,
    })
    assert not plan.unit_auto
    assert "equity_type" not in [d.business_name for d in plan.dimensions]


def test_is_null_filter_on_single_product_column_never_decides():
    # offering_type is_null matches every DCM row (NULL there) as well as the
    # ECM rows without an offering type — it cannot decide the product, and a
    # both-products scope must neither narrow nor be rejected for it.
    if not _deps():
        SKIPPED.append("is_null on a single-product column (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "order_count",
        "filters": [
            {"field": "product", "op": "in", "value": ["ECM", "DCM"]},
            {"field": "offering_type", "op": "is_null"},
        ],
    })
    assert plan.narrowed_product is None
    assert len([f for f in plan.filters if f.business_name == "product"]) == 1


def test_ecm_allocation_request_gets_equity_type_projected():
    # 2026-09-28: convertibles were labelled 'shares' on the first answer
    # because the rows never carried the security. The planner now adds it.
    if not _deps():
        SKIPPED.append("equity_type auto-projection (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "total_allocation",
        "dimensions": ["investor_name", "investor_id"],
        "filters": [{"field": "product", "op": "eq", "value": "ECM"}],
    })
    assert plan.unit_auto is True
    assert [d.business_name for d in plan.dimensions][-1] == "equity_type"


def test_equity_type_not_added_for_counts_or_dcm_or_when_present():
    if not _deps():
        SKIPPED.append("equity_type auto-projection negatives (pydantic/yaml not installed)")
        return
    count = _plan({
        "source": "capital_markets_order", "metric": "order_count",
        "dimensions": ["investor_name"],
        "filters": [{"field": "product", "op": "eq", "value": "ECM"}],
    })
    assert count.unit_auto is False and all(d.business_name != "equity_type" for d in count.dimensions)
    dcm = _plan({
        "source": "capital_markets_order", "metric": "total_allocation",
        "dimensions": ["investor_name"],
        "filters": [{"field": "product", "op": "eq", "value": "DCM"}],
    })
    assert dcm.unit_auto is False
    present = _plan({
        "source": "capital_markets_order", "metric": "total_allocation",
        "dimensions": ["investor_name", "equity_type"],
        "filters": [{"field": "product", "op": "eq", "value": "ECM"}],
    })
    assert present.unit_auto is False
    assert [d.business_name for d in present.dimensions].count("equity_type") == 1


def test_descoped_field_on_dcm_is_now_accepted():
    # Release 3: investor_category works on BOTH products — the old
    # rejection must NOT fire (this is the de-scoping's regression guard).
    if not _deps():
        SKIPPED.append("release-3 de-scoping (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "order_count",
        "dimensions": ["investor_category"],
        "filters": [{"field": "product", "op": "eq", "value": "DCM"}],
    })
    assert plan.metric.business_name == "order_count"


# --------------------------------------------------------------------------
# partition_by — top-N-per-group (added 2026-08-11)
# --------------------------------------------------------------------------

def test_partition_by_plans_and_compiles():
    if not _deps():
        SKIPPED.append("partition_by compile (pydantic/yaml not installed)")
        return
    from bqs.dialects.trino import TrinoDialect
    from bqs.sql_builder import build_sql
    from bqs.sql_validator import assert_read_only

    plan = _plan({
        "source": "capital_markets_deal",
        "metric": "total_deal_size",
        "dimensions": ["sector", "deal_name", "deal_id"],
        "filters": [{"field": "product", "op": "eq", "value": "ECM"}],
        "partition_by": ["sector"],
        "per_partition_limit": 2,
    })
    assert plan.partition is not None
    assert plan.partition.by == ["sector"]
    assert plan.partition.limit == 2
    # No order given -> ranking defaults to the metric descending.
    assert plan.orders[0].column_alias == "total_deal_size"
    assert plan.orders[0].direction == "DESC"

    sql = build_sql(plan, TrinoDialect()).sql
    assert_read_only(sql)
    assert "ROW_NUMBER() OVER (PARTITION BY" in sql
    assert '"rank_in_group"' in sql
    assert '"rank_in_group" <= 2' in sql
    # Defaulted ranking (no request order): groups stay together in the output.
    assert 'ORDER BY "sector" ASC, "rank_in_group" ASC' in sql


def test_partition_with_explicit_order_sorts_survivors_globally():
    # The DEDUPE shape (QA 2026-08-14): "5 latest DEALS" on a tranche-grain
    # object. Without this, a two-tranche deal eats two of the five slots —
    # observed as "5 latest deals" returning 4 deals in 5 rows. The explicit
    # order ranks inside each group AND sorts the surviving rows across groups.
    if not _deps():
        SKIPPED.append("partition global order (pydantic/yaml not installed)")
        return
    from bqs.dialects.trino import TrinoDialect
    from bqs.sql_builder import build_sql

    plan = _plan({
        "source": "capital_markets_deal",
        "metric": "deal_count",
        "dimensions": ["sector", "deal_name", "deal_id"],
        "partition_by": ["deal_name", "deal_id"],
        "per_partition_limit": 1,
        "order": [{"field": "sector", "direction": "desc"}],
        "limit": 5,
    })
    assert plan.partition is not None and plan.partition.order_globally is True
    sql = build_sql(plan, TrinoDialect()).sql
    tail = sql[sql.index("ranked WHERE"):]
    assert tail.startswith('ranked WHERE "rank_in_group" <= 1 ORDER BY "sector" DESC'), (
        "the requested order must govern the survivors across groups — "
        "otherwise LIMIT N takes the first N groups alphabetically, not the "
        "N the user asked for"
    )


def test_partition_by_misuse_is_rejected():
    if not _deps():
        SKIPPED.append("partition_by misuse (pydantic/yaml not installed)")
        return
    base = {"source": "capital_markets_deal", "metric": "deal_count"}
    # Every projected dimension -> each group is one row, nothing is ranked.
    _expect_code(
        {**base, "dimensions": ["sector"], "partition_by": ["sector"]},
        "bad_partition", "partition covers all dims",
    )
    # Unprojected field.
    _expect_code(
        {**base, "dimensions": ["sector", "deal_name"], "partition_by": ["issuer_name"]},
        "bad_partition", "partition field not projected",
    )
    # Ranked groups are not a pageable stream.
    _expect_code(
        {
            **base,
            "dimensions": ["sector", "deal_name"],
            "partition_by": ["sector"],
            "offset": 5,
            "order": [{"field": "deal_count", "direction": "desc"}],
        },
        "bad_partition", "partition + offset",
    )
    # A per-group limit with no groups.
    _expect_code(
        {**base, "per_partition_limit": 3},
        "bad_partition", "per_partition_limit without partition_by",
    )


# --------------------------------------------------------------------------
# filter value shape — the silent `col = NULL` class
# --------------------------------------------------------------------------

def test_missing_value_on_value_bearing_op_is_rejected():
    if not _deps():
        SKIPPED.append("value=None rejection (pydantic/yaml not installed)")
        return
    _expect_code(
        {
            "source": "capital_markets_deal",
            "metric": "deal_count",
            "filters": [{"field": "sector", "op": "eq"}],
        },
        "bad_filter_value",
        "eq with no value used to render `col = NULL` -> 0 rows as 'no data'",
    )


def test_empty_in_list_is_rejected():
    if not _deps():
        SKIPPED.append("empty in-list rejection (pydantic/yaml not installed)")
        return
    _expect_code(
        {
            "source": "capital_markets_deal",
            "metric": "deal_count",
            "filters": [{"field": "sector", "op": "in", "value": []}],
        },
        "bad_filter_value",
        "IN () is malformed SQL — reject in the planner, not the warehouse",
    )


def test_is_null_needs_no_value():
    if not _deps():
        SKIPPED.append("is_null without value (pydantic/yaml not installed)")
        return
    # deal_status declares is_null in its operators (sector does not).
    plan = _plan({
        "source": "capital_markets_deal",
        "metric": "deal_count",
        "filters": [{"field": "deal_status", "op": "is_null"}],
    })
    assert plan.filters[0].op == "is_null"


def test_typoed_filter_key_is_a_validation_error():
    if not _deps():
        SKIPPED.append("extra-key rejection (pydantic not installed)")
        return
    from pydantic import ValidationError

    from bqs.models import BQSRequest

    try:
        BQSRequest.model_validate({
            "source": "capital_markets_deal",
            "metric": "deal_count",
            "filters": [{"field": "sector", "op": "eq", "val": "ENERGY"}],
        })
    except ValidationError:
        return
    raise AssertionError(
        "a typo'd key ('val') validated silently — value stayed None and the "
        "query rendered `col = NULL`, returning 0 rows as 'no data'"
    )


CASES = [
    ("offset fallback sorts every dimension", test_offset_without_order_sorts_every_dimension),
    ("offset fallback includes time-grain bucket", test_offset_fallback_includes_time_grain_bucket),
    ("bare offset is refused", test_offset_with_nothing_to_sort_is_refused),
    ("ECM-only filter on DCM rejected", test_ecm_only_filter_on_dcm_is_rejected_not_empty),
    ("same filter on ECM accepted", test_same_filter_on_ecm_is_accepted),
    ("listed single-product column projected, not rejected", test_listed_single_product_column_is_projected_not_rejected),
    ("dual scope + ECM-only filter narrows to ECM", test_dual_scope_with_ecm_only_filter_narrows_to_ecm),
    ("unscoped + DCM-only filter narrows to DCM", test_unscoped_request_with_dcm_only_filter_narrows_to_dcm),
    ("explicit single scope is never narrowed", test_explicit_single_scope_is_never_narrowed),
    ("conflicting single-product filters rejected", test_dual_scope_with_conflicting_single_product_filters_is_rejected),
    ("mixed-product dimensions run as ONE query", test_mixed_product_dimensions_run_as_one_query_on_a_dual_scope),
    ("is_null on a single-product column never decides", test_is_null_filter_on_single_product_column_never_decides),
    ("submitted bid alone does not trigger equity_type", test_submitted_bid_alone_does_not_trigger_equity_type),
    ("ECM allocation request gets equity_type", test_ecm_allocation_request_gets_equity_type_projected),
    ("equity_type not added for counts/DCM/present", test_equity_type_not_added_for_counts_or_dcm_or_when_present),
    ("release-3 de-scoped field on DCM accepted", test_descoped_field_on_dcm_is_now_accepted),
    ("partition_by plans and compiles", test_partition_by_plans_and_compiles),
    ("partition explicit order sorts globally", test_partition_with_explicit_order_sorts_survivors_globally),
    ("partition_by misuse rejected", test_partition_by_misuse_is_rejected),
    ("missing value rejected", test_missing_value_on_value_bearing_op_is_rejected),
    ("empty in-list rejected", test_empty_in_list_is_rejected),
    ("is_null needs no value", test_is_null_needs_no_value),
    ("typo'd filter key is an error", test_typoed_filter_key_is_a_validation_error),
]


if __name__ == "__main__":
    print()
    failures = 0
    for label, fn in CASES:
        try:
            fn()
            print(f"  ok   {label}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {label}\n         {exc}")
    for note in SKIPPED:
        print(f"  SKIP {note} — asserted textually by _review/ontology_check.py")
    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        sys.exit(1)
    print("The planner rejects what it cannot answer honestly, and pages deterministically.")
    sys.exit(0)
