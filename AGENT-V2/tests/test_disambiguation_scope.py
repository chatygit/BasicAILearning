"""The disambiguation probe must be scoped exactly like the query it explains.

`build_disambiguation` runs a `SELECT DISTINCT <name>` probe whenever an
entity-name filter's field was not projected as a dimension. That probe used to
carry ONLY the entity predicate — no date range, no product — so it scanned the
whole view for all time and both products.

Measured on "how much did Blackrock invest in ECM deals in 2025":

    BQS timing rows=1 | build=0.00s execute=6.11s format=0.00s
                        enrich=34.89s total=41.00s

85% of the tool call, for a list that was also WRONG: it offered the user 26
Blackrock entities, including ones with no 2025 ECM activity at all. The
hand-rolled predicate was case-SENSITIVE too, while the main query wraps both
sides in UPPER().

The fix reuses `sql_builder._build_where` — the same renderer the main SQL uses
— so the probe and the answer can never disagree about scope.

Runs under pytest, or standalone (`python3 tests/test_disambiguation_scope.py`).
"""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from pathlib import Path

APP = Path(__file__).parent.parent / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


def _stub_pydantic() -> None:
    """Minimal pydantic stand-in so this runs with no third-party packages.

    Only enough surface for `models.py` / `ontology.py` to IMPORT — the SQL text
    under test never constructs a model.
    """
    if "pydantic" in sys.modules:
        return
    mod = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

        @classmethod
        def model_validate(cls, data):
            return cls(**(data or {}))

    def Field(default=None, **_kw):
        return None if default is Ellipsis else default

    def field_validator(*_a, **_kw):
        def deco(fn):
            return fn
        return deco

    class ValidationError(Exception):
        pass

    mod.BaseModel = BaseModel
    mod.Field = Field
    mod.field_validator = field_validator
    mod.ValidationError = ValidationError
    sys.modules["pydantic"] = mod


def _stub_yaml() -> None:
    """`ontology.py` imports PyYAML at module load; nothing here parses YAML."""
    if "yaml" in sys.modules:
        return
    mod = types.ModuleType("yaml")
    mod.safe_load = lambda *_a, **_kw: {}
    mod.YAMLError = type("YAMLError", (Exception,), {})
    sys.modules["yaml"] = mod


_stub_pydantic()
_stub_yaml()

from bqs.dialects.trino import TrinoDialect          # noqa: E402
from bqs.suggestions import _build_entity_distinct_probe, _EntityFilter  # noqa: E402


@dataclass
class FakeFilter:
    column: str
    op: str
    value: object
    case_insensitive: bool = False


@dataclass
class FakeSpec:
    base_view: str = "dataglobe_oraas.dgstream.vw_order_detail"


@dataclass
class FakePlan:
    filters: list = field(default_factory=list)
    computed_filters: list = field(default_factory=list)
    derived_filters: list = field(default_factory=list)


DIALECT = TrinoDialect()
SPEC = FakeSpec()
ENTITY = _EntityFilter(
    field="investor_name",
    column="investor_name",
    op="like",
    value="%BLACKROCK%",
)

# Exactly the shape of the measured 41s call.
PLAN = FakePlan(filters=[
    FakeFilter("investor_name", "like", "%BLACKROCK%", case_insensitive=True),
    FakeFilter("pricing_ts", "gte", "2025-01-01"),
    FakeFilter("pricing_ts", "lt", "2026-01-01"),
    FakeFilter("product", "eq", "ECM"),
])


def test_probe_carries_the_date_range():
    sql, params = _build_entity_distinct_probe(SPEC, ENTITY, DIALECT, PLAN)
    assert '"pricing_ts" >=' in sql and '"pricing_ts" <' in sql, (
        "the probe dropped the date range and will scan every year:\n" + sql
    )
    assert "2025-01-01" in params.values() or "2025-01-01" in str(params)


def test_probe_carries_the_product_filter():
    sql, params = _build_entity_distinct_probe(SPEC, ENTITY, DIALECT, PLAN)
    assert '"product"' in sql, (
        "the probe dropped the product filter and will scan both ECM and DCM:\n" + sql
    )
    assert "ECM" in str(params)


def test_probe_matches_case_insensitively_like_the_main_query():
    sql, _ = _build_entity_distinct_probe(SPEC, ENTITY, DIALECT, PLAN)
    assert 'UPPER("investor_name")' in sql, (
        "the probe is case-SENSITIVE while the main query uses UPPER() on both "
        "sides — the two can match different rows:\n" + sql
    )


def test_probe_still_selects_distinct_names_and_is_bounded():
    sql, _ = _build_entity_distinct_probe(SPEC, ENTITY, DIALECT, PLAN)
    assert 'SELECT DISTINCT "investor_name"' in sql
    assert "IS NOT NULL" in sql
    assert "LIMIT" in sql, "the probe must stay bounded"


def test_values_are_parameter_bound_never_inlined():
    sql, params = _build_entity_distinct_probe(SPEC, ENTITY, DIALECT, PLAN)
    assert "%BLACKROCK%" not in sql, (
        "the agent's value was concatenated into the SQL instead of bound:\n" + sql
    )
    assert "%BLACKROCK%" in str(params)


def test_no_plan_falls_back_without_crashing():
    sql, params = _build_entity_distinct_probe(SPEC, ENTITY, DIALECT, None)
    assert 'SELECT DISTINCT "investor_name"' in sql
    assert "IS NOT NULL" in sql
    assert "%BLACKROCK%" in str(params)


CASES = [
    ("probe carries the date range", test_probe_carries_the_date_range),
    ("probe carries the product filter", test_probe_carries_the_product_filter),
    ("probe matches case-insensitively", test_probe_matches_case_insensitively_like_the_main_query),
    ("probe still DISTINCT + bounded", test_probe_still_selects_distinct_names_and_is_bounded),
    ("values are parameter-bound", test_values_are_parameter_bound_never_inlined),
    ("no-plan fallback still works", test_no_plan_falls_back_without_crashing),
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
    print()
    sql, _ = _build_entity_distinct_probe(SPEC, ENTITY, DIALECT, PLAN)
    print("  probe SQL:")
    print("   ", sql)
    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        sys.exit(1)
    print("The probe is scoped exactly like the query it explains.")
    sys.exit(0)
