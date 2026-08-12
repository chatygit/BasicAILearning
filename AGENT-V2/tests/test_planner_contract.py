"""The planner contract: paging determinism, product applicability, partition_by.

Every case here pins a shipped bug or a 2026-08-11 fix:

  - The offset fallback ORDER BY once shipped as `d.alias` — an AttributeError
    on EVERY paged listing without an explicit order (page 2 crashed).
  - The fallback ignored the time_grain bucket, so monthly buckets tied inside
    a dimension and pages could repeat or skip months — silently wrong trends.
  - _check_product_applicability is what turns "ECM-only field asked on DCM"
    into a rejection instead of an empty result read as "no data". It only
    fires for dual-entitled callers — which is what PRODUCTION has — so a
    single-product local login can never reproduce its absence.
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

def test_ecm_only_field_on_dcm_is_rejected_not_empty():
    if not _deps():
        SKIPPED.append("product applicability (pydantic/yaml not installed)")
        return
    e = _expect_code(
        {
            "source": "capital_markets_order",
            "metric": "order_count",
            "dimensions": ["investor_category"],
            "filters": [{"field": "product", "op": "eq", "value": "DCM"}],
        },
        "product_not_applicable",
        "investor_category is hard NULL on every DCM row",
    )
    assert "investor_category" in e.message


def test_same_field_on_ecm_is_accepted():
    if not _deps():
        SKIPPED.append("product applicability happy path (pydantic/yaml not installed)")
        return
    plan = _plan({
        "source": "capital_markets_order",
        "metric": "order_count",
        "dimensions": ["investor_category"],
        "filters": [{"field": "product", "op": "eq", "value": "ECM"}],
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
    ("ECM-only field on DCM rejected", test_ecm_only_field_on_dcm_is_rejected_not_empty),
    ("same field on ECM accepted", test_same_field_on_ecm_is_accepted),
    ("partition_by plans and compiles", test_partition_by_plans_and_compiles),
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
