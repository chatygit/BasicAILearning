"""A missing field must say WHERE it lives — or that it lives nowhere.

Observed 2026-08-10, "Who are the top 10 investors by allocation in Energy deals
over the last 2 years, grouped by Investor Type?":

  #4/#6/#8  discover capital_markets_order, then _deal, then _tranche  (3 LLM turns)
  #10..#19  ten run_bqs_query calls, cycling unknown_filter 'sector' and
            bad_order_field 'pricing_date'
  #20       429 RESOURCE_EXHAUSTED

`allocation` and `investor_category` are on capital_markets_order; `sector` is only on
capital_markets_deal. One BQS request runs against ONE object, so the question is not
expressible — but "Unknown filter field 'sector' ... Known filters: [...]" reads
like a spelling problem, so the agent kept guessing.

The registry knows every object's fields. These cases pin the distinction the
agent could not make on its own: a field at ANOTHER grain versus one that exists
nowhere. They are different answers to the user, and neither is "try again".

Runs under pytest, or standalone. No third-party packages.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

APP = Path(__file__).parent.parent / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


def _stub(name: str, **attrs) -> None:
    """Install a module only if the real one is absent — so this runs both here
    (no third-party packages) and in the repo (where they are installed)."""
    if name in sys.modules:
        return
    try:
        __import__(name)
        return
    except ImportError:
        pass
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod


class _BaseModel:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    @classmethod
    def model_validate(cls, data):
        return cls(**(data or {}))


_stub(
    "pydantic",
    BaseModel=_BaseModel,
    Field=lambda default=None, **_kw: (None if default is Ellipsis else default),
    field_validator=lambda *_a, **_kw: (lambda fn: fn),
    ValidationError=type("ValidationError", (Exception,), {}),
)
_stub("yaml", safe_load=lambda *_a, **_kw: {},
      YAMLError=type("YAMLError", (Exception,), {}))
# The service imports the executor, which imports the Trino driver. `trino` is a
# PACKAGE, so the stub needs __path__ or importing trino.dbapi walks the real
# filesystem finder and fails.
_stub("trino", __path__=[])
_stub("trino.dbapi", connect=lambda **_kw: None, Connection=object)
_stub("trino.auth", BasicAuthentication=object)
_stub("trino.exceptions", TrinoQueryError=type("TrinoQueryError", (Exception,), {}),
      TrinoUserError=type("TrinoUserError", (Exception,), {}))
# app/bqs/dialects/factory.py is not part of the AGENT-V2 tree (README: "Not
# included"). Present in the repo, so _stub leaves the real one alone there.
_stub("bqs.dialects.factory", get_dialect=lambda *_a, **_kw: None)


class FakeError(Exception):
    """Stands in for BQSError — same surface the explainer touches."""

    def __init__(self, message, code):
        super().__init__(message)
        self.message = message
        self.code = code

    def to_dict(self):
        return {"error": True, "code": self.code, "message": self.message}


class FakeSpec:
    def __init__(self, filters, dimensions):
        self.filters = filters
        self.dimensions = dimensions


class FakeRegistry:
    """The real four-object shape, reduced to the fields these cases need.

    capital_markets_order's filter list is copied verbatim from the `unknown_filter`
    error in the 2026-08-10 trace, so `deal_name` really is on three objects and
    `sector` really is on one.
    """

    SPECS = {
        "capital_markets_order": FakeSpec(
            {"currency", "deal_id", "deal_name", "investor_category", "investor_id",
             "investor_name", "investor_region", "ioi_type", "meeting_type",
             "order_allocation", "order_amount", "order_demand_qty", "order_id",
             "order_type", "pricing_date", "product", "tranche_id"},
            {"investor_name", "investor_category", "order_allocation"},
        ),
        "capital_markets_deal": FakeSpec(
            {"sector", "deal_name", "product", "pricing_date"},
            {"sector", "deal_name", "issuer_name"},
        ),
        "capital_markets_tranche": FakeSpec({"deal_name", "product"}, {"tranche_id"}),
        "capital_markets_entity": FakeSpec({"entity_name"}, {"entity_id"}),
    }

    def list_sources(self):
        return sorted(self.SPECS)

    def get(self, name):
        return self.SPECS[name]


def explain(message, code, source):
    """Call the real method with a stubbed registry — no DB, no pydantic."""
    from services.domain_query_service import DomainQueryService

    svc = object.__new__(DomainQueryService)
    svc.registry = FakeRegistry()
    return DomainQueryService._explain_cross_object(
        svc, FakeError(message, code), {"source": source}
    )


SECTOR_ERR = (
    "Unknown filter field 'sector' for source 'capital_markets_order'. "
    "Known filters: ['currency', 'deal_id', 'investor_name']"
)


def test_field_on_another_object_is_named():
    res = explain(SECTOR_ERR, "unknown_filter", "capital_markets_order")
    assert res["field_available_on"] == ["capital_markets_deal"]
    assert "capital_markets_deal" in res["message"]


def test_it_says_one_request_cannot_span_grains():
    msg = explain(SECTOR_ERR, "unknown_filter", "capital_markets_order")["message"].lower()
    assert "cannot span" in msg, (
        "without this the agent reads a grain problem as a spelling problem"
    )
    assert "do not retry" in msg, "the retry loop is what reached 429"


def test_field_that_exists_nowhere_says_so():
    res = explain(
        "Unknown filter field 'esg_rating' for source 'capital_markets_order'. "
        "Known filters: ['currency']",
        "unknown_filter",
        "capital_markets_order",
    )
    assert res["field_available_on"] == []
    assert "not available on any object" in res["message"].lower()
    assert "not tracked" in res["message"].lower()


def test_a_field_present_on_several_objects_lists_them_all():
    res = explain(
        "Unknown filter field 'deal_name' for source 'capital_markets_entity'. "
        "Known filters: ['entity_name']",
        "unknown_filter",
        "capital_markets_entity",
    )
    assert res["field_available_on"] == ["capital_markets_deal", "capital_markets_order", "capital_markets_tranche"]


def test_the_source_asked_for_is_never_suggested_back():
    res = explain(SECTOR_ERR, "unknown_filter", "capital_markets_order")
    assert "capital_markets_order" not in res["field_available_on"], (
        "suggesting the object that just rejected the field is a retry loop"
    )


def test_dimension_misses_are_explained_too():
    res = explain(
        "Unknown dimension 'sector' for source 'capital_markets_order'.",
        "unknown_dimension",
        "capital_markets_order",
    )
    assert res["field_available_on"] == ["capital_markets_deal"]


def test_unrelated_errors_pass_through_untouched():
    original = "Order field 'pricing_date' must be the metric or a selected dimension."
    res = explain(original, "bad_order_field", "capital_markets_order")
    assert res["message"] == original, "only field-miss codes are rewritten"
    assert "field_available_on" not in res


def test_a_message_with_no_quoted_field_is_left_alone():
    res = explain("Unknown filter field.", "unknown_filter", "capital_markets_order")
    assert res["message"] == "Unknown filter field."


def test_explainer_never_raises():
    class Exploding:
        def list_sources(self):
            raise RuntimeError("registry down")

    from services.domain_query_service import DomainQueryService

    svc = object.__new__(DomainQueryService)
    svc.registry = Exploding()
    res = DomainQueryService._explain_cross_object(
        svc, FakeError(SECTOR_ERR, "unknown_filter"), {"source": "capital_markets_order"}
    )
    assert res["code"] == "unknown_filter", "an error path must never add an error"


CASES = [
    ("field on another object is named", test_field_on_another_object_is_named),
    ("says one request cannot span grains", test_it_says_one_request_cannot_span_grains),
    ("field that exists nowhere says so", test_field_that_exists_nowhere_says_so),
    ("lists every object carrying it", test_a_field_present_on_several_objects_lists_them_all),
    ("never suggests the rejecting source", test_the_source_asked_for_is_never_suggested_back),
    ("dimension misses explained too", test_dimension_misses_are_explained_too),
    ("unrelated errors pass through", test_unrelated_errors_pass_through_untouched),
    ("no quoted field -> left alone", test_a_message_with_no_quoted_field_is_left_alone),
    ("explainer never raises", test_explainer_never_raises),
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
    if failures:
        print(f"{failures} case(s) FAILED")
        sys.exit(1)
    print("A missing field ends the attempt with an explanation, not another guess.")
    sys.exit(0)
