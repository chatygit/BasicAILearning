"""The REAL entitlement gate — mcpserver._entitlement_gate/_entitlement_preflight.

tests/test_entitlement_scope.py asserts a hand-written MIRROR of the gate's
scoping rules; a mirror rots the moment the shipped code changes, and it can
never catch a bug the author also copied into the mirror. These cases import
app/mcpserver.py itself (third-party imports stubbed) and drive the actual
functions, so the request-mutation behaviour under test is the one production
runs.

Every case pins a confirmed live bug or a 2026-08-11 fix:

  - INTERSECT: a dual-entitled caller asking for ECM used to have its filter
    dropped and the FULL entitlement injected — "ECM deals in 2025" silently
    became ECM+DCM, and size/allocation metrics summed shares with money.
  - NEGATION INVERSION: `product ne 'ECM'` collected requested=[ECM] and was
    rewritten to `product eq 'ECM'` — the exact opposite of the ask.
  - INVALID VALUE: a typo'd product ("EMC") was stripped and scope silently
    widened to the caller's full entitlement.
  - FAIL-OPEN: an entitlement-component import failure ran every query
    UNSCOPED while enforcement was on; decided fail-closed 2026-08-11.

Runs under pytest, or standalone (`python3 tests/test_entitlement_gate.py`).
No third-party packages required — everything mcpserver needs is stubbed.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

APP = Path(__file__).parent.parent / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


# --------------------------------------------------------------------------
# stubs — installed BEFORE importing mcpserver (same convention as
# test_cross_object_error.py). A permissive decorator object covers every
# @mcp.tool()/@mcp.resource(...)/@mcp.prompt usage, called with or without
# arguments; http_app() returns an object that accepts add_route/add_middleware.
# --------------------------------------------------------------------------

class _Anything:
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        if len(a) == 1 and callable(a[0]) and not k:
            return a[0]  # bare decorator: @mcp.prompt
        return _Anything()  # decorator factory / plain call

    def __getattr__(self, name):
        return _Anything()


def _module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


def _install_stubs() -> None:
    _module("uvicorn", run=lambda *a, **k: None)
    _module("fastmcp", FastMCP=_Anything)
    mcp_pkg = _module("mcp")
    mcp_pkg.types = _module("mcp.types", ToolAnnotations=_Anything)
    starlette = _module("starlette")
    starlette.responses = _module("starlette.responses", JSONResponse=_Anything)
    # Repo-local modules with heavy deps of their own (starlette middleware,
    # prometheus, otel) — the gate under test touches none of them.
    _module("middleware.auth_middleware", AuthMiddleware=_Anything)
    _module(
        "middleware.metrics_middleware", PrometheusMetricsMiddleware=_Anything
    )
    _module("middleware.tracing_middleware", TracingMiddleware=_Anything)
    _module("utils.logger", logger_setup=lambda *a, **k: None)
    _module("utils.tracing", setup_tracing=lambda *a, **k: None)
    _module("middleware.soeid_middleware", get_soeid=lambda: "", SoeidHeaderMiddleware=_Anything)


_STUBBED = [
    "uvicorn", "fastmcp", "mcp", "mcp.types", "starlette",
    "starlette.responses", "middleware.auth_middleware",
    "middleware.metrics_middleware", "middleware.tracing_middleware",
    "utils.logger", "utils.tracing", "middleware.soeid_middleware",
]

_install_stubs()
import mcpserver  # noqa: E402

# Uninstall the stubs immediately: mcpserver already captured the references
# it needs, and leaving fakes in sys.modules would poison later test modules
# that import the REAL repo-local modules (test_soeid_resolution.py stubs
# starlette its own way and then imports the real soeid middleware).
for _name in _STUBBED:
    sys.modules.pop(_name, None)


# --------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------

_ENV = ["ECM_DCM_ENTITLEMENT_FEATURE_FLAG"]
_SAVED: dict[str, str | None] = {}
_MOD_ATTRS = [
    "_SOEID_AVAILABLE",
    "_ENTITLEMENT_AVAILABLE",
    "_resolve_soeid",
    "perform_initial_entitlement_check",
]
_SAVED_ATTRS: dict[str, object] = {}
_MISSING = object()


def setup_function(func=None) -> None:
    for k in _ENV:
        _SAVED[k] = os.environ.get(k)
        os.environ.pop(k, None)
    for a in _MOD_ATTRS:
        _SAVED_ATTRS[a] = getattr(mcpserver, a, _MISSING)


def teardown_function(func=None) -> None:
    for k, v in _SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    for a, v in _SAVED_ATTRS.items():
        if v is _MISSING:
            if hasattr(mcpserver, a):
                delattr(mcpserver, a)
        else:
            setattr(mcpserver, a, v)


def _grant(entitled: list[str]) -> None:
    """Point the gate at a known identity + a fake entitlement service."""
    mcpserver._SOEID_AVAILABLE = True
    mcpserver._ENTITLEMENT_AVAILABLE = True
    mcpserver._resolve_soeid = lambda: "ts12345"
    mcpserver.perform_initial_entitlement_check = lambda **kw: {
        "ok": True,
        "entitled_products": list(entitled),
    }


def _product_filters(request: dict) -> list[dict]:
    return [
        f for f in request["filters"]
        if str(f.get("field", "")).lower() == "product"
    ]


# --------------------------------------------------------------------------
# scoping — the intersect fix
# --------------------------------------------------------------------------

def test_dual_entitled_eq_ecm_stays_ecm():
    _grant(["ECM", "DCM"])
    request = {"filters": [{"field": "product", "op": "eq", "value": "ECM"}]}
    assert mcpserver._entitlement_gate(request) is None
    pf = _product_filters(request)
    assert pf == [{"field": "product", "op": "eq", "value": "ECM"}], (
        "the caller asked for ECM; injecting the full entitlement is how ECM "
        "share counts got summed with DCM notional money"
    )


def test_dual_entitled_unscoped_gets_both_injected():
    _grant(["ECM", "DCM"])
    request = {"filters": [{"field": "sector", "op": "eq", "value": "Energy"}]}
    assert mcpserver._entitlement_gate(request) is None
    pf = _product_filters(request)
    assert pf == [{"field": "product", "op": "in", "value": ["ECM", "DCM"]}]
    # The agent's own filter must survive the rewrite.
    assert {"field": "sector", "op": "eq", "value": "Energy"} in request["filters"]


def test_single_entitled_asking_other_product_is_denied():
    _grant(["ECM"])
    request = {"filters": [{"field": "product", "op": "eq", "value": "DCM"}]}
    denial = mcpserver._entitlement_gate(request)
    assert denial and denial["code"] == "product_not_entitled"
    assert "ECM" in denial["message"], "the denial must name what IS entitled"


# --------------------------------------------------------------------------
# the gate polices op and value — it rewrites BEFORE the planner can
# --------------------------------------------------------------------------

def test_negated_product_filter_is_rejected_not_inverted():
    _grant(["ECM", "DCM"])
    request = {"filters": [{"field": "product", "op": "ne", "value": "ECM"}]}
    denial = mcpserver._entitlement_gate(request)
    assert denial and denial["code"] == "operator_not_allowed", (
        "product ne 'ECM' used to be collected as requested=[ECM] and "
        "rewritten to eq 'ECM' — the exact opposite of the ask"
    )
    assert _product_filters(request), "the request must NOT be mutated on denial"


def test_invalid_product_value_is_rejected_not_widened():
    _grant(["ECM", "DCM"])
    request = {"filters": [{"field": "product", "op": "eq", "value": "EMC"}]}
    denial = mcpserver._entitlement_gate(request)
    assert denial and denial["code"] == "invalid_product_value", (
        "a typo'd product used to be stripped, widening scope to the full "
        "entitlement — a product-scoped question answered with everything"
    )


# --------------------------------------------------------------------------
# fail-closed (decided 2026-08-11)
# --------------------------------------------------------------------------

def test_import_failure_with_enforcement_on_refuses():
    _grant(["ECM", "DCM"])
    mcpserver._ENTITLEMENT_AVAILABLE = False  # flag defaults to "true"
    denial, entitled = mcpserver._entitlement_preflight()
    assert denial and denial["code"] == "entitlement_unavailable", (
        "enforcement ON + component missing used to run every query UNSCOPED"
    )
    assert entitled == []


def test_import_failure_with_flag_off_stays_permissive():
    _grant(["ECM", "DCM"])
    mcpserver._ENTITLEMENT_AVAILABLE = False
    os.environ["ECM_DCM_ENTITLEMENT_FEATURE_FLAG"] = "false"
    denial, entitled = mcpserver._entitlement_preflight()
    assert denial is None and entitled == [], (
        "flag off is an explicit developer opt-out (their .env, announced at "
        "startup) — it must keep working or local dev breaks"
    )


# --------------------------------------------------------------------------
# entitlement scope in discovery (added 2026-08-12)
#
# QA trace: an ECM-only caller asked for top Healthcare deals, got a correct
# ECM answer — then the agent volunteered "the top DCM deals", ran the query,
# was denied, and closed with an entitlement apology. The skill's rule (never
# request the unentitled product) was unfollowable because nothing told the
# agent WHAT was entitled. Discovery now carries the set.
# --------------------------------------------------------------------------

def test_discovery_carries_entitled_products():
    result = mcpserver._attach_entitlement_scope({"error": False}, ["ECM"])
    assert result["entitled_products"] == ["ECM"]
    note = result["entitlement_note"]
    assert "ONLY products" in note
    assert "never run" in note.lower(), (
        "the note must forbid RUNNING the unentitled query, not just "
        "mentioning it — the wasted round-trip is the bug"
    )


def test_bare_scope_for_query_responses():
    # Every run_bqs_query response carries the bare key (no note) — a scope
    # stated once at session start gets buried/trimmed in long conversations
    # (observed 2026-08-18: 50+-event ECM-only session drifted to DCM).
    result = mcpserver._attach_entitlement_scope(
        {"error": False, "rows": []}, ["ECM"], note=False
    )
    assert result["entitled_products"] == ["ECM"]
    assert "entitlement_note" not in result, (
        "query responses carry the bare key; the instruction text rides only "
        "on discovery — per-response notes would cost tokens on every turn"
    )


def test_scope_not_attached_when_gate_inactive_or_error():
    # Enforcement off -> entitled=[] -> key absent; the skill then treats both
    # products as queryable (dev mode must not look like a one-product user).
    assert "entitled_products" not in mcpserver._attach_entitlement_scope(
        {"error": False}, []
    )
    # Error payloads pass through untouched — a denial needs no catalog decor.
    denial = {"error": True, "code": "missing_soeid"}
    assert "entitled_products" not in mcpserver._attach_entitlement_scope(
        denial, ["ECM"]
    )


def test_ok_with_no_products_refuses_when_flag_on():
    _grant([])
    denial, entitled = mcpserver._entitlement_preflight()
    assert denial and denial["code"] == "no_entitled_products", (
        "'ok with nothing' must never widen to 'everything' while enforcement "
        "is on"
    )
    assert entitled == []


# --------------------------------------------------------------------------
# stale relative window guard (added 2026-08-18)
#
# QA: the model fired run_bqs_query in the SAME turn as discovery, before the
# date_anchor existed, and anchored "this year" on its training cutoff — the
# 2024 window ran and was answered as fact. The server knows today; when the
# ask says now-relative time and every date bound is before Jan 1 of the
# current year, the window cannot be what the user meant.
# --------------------------------------------------------------------------

def _dt_filters(*bounds):
    ops = ["gte", "lt"]
    return [
        {"field": "last_priced", "op": ops[i % 2], "value": b}
        for i, b in enumerate(bounds)
    ]


def test_stale_this_year_window_is_refused():
    denial = mcpserver._check_relative_date_mismatch(
        "break down ecm deals by region this year, grouped by month",
        _dt_filters("2024-01-01", "2025-01-01"),
    )
    assert denial and denial["code"] == "stale_relative_window"
    assert "TODAY IS" in denial["message"], (
        "the refusal must carry the real date — it is the anchor the model "
        "was missing"
    )


def test_explicit_historical_ask_passes():
    # "deals in 2024" has no relative phrase — history is queryable, never
    # refused (the date-anchor doctrine's own HISTORY rule).
    assert mcpserver._check_relative_date_mismatch(
        "ecm deals by region in 2024, grouped by month",
        _dt_filters("2024-01-01", "2025-01-01"),
    ) is None


def test_correctly_anchored_relative_window_passes():
    from datetime import date, timedelta
    today = date.today()
    assert mcpserver._check_relative_date_mismatch(
        "top investors in the last 3 years",
        _dt_filters(
            f"{today.year - 3}-01-01",
            (today + timedelta(days=1)).isoformat(),
        ),
    ) is None


def test_guard_noops_without_question_or_dates():
    assert mcpserver._check_relative_date_mismatch(None, _dt_filters("2024-01-01")) is None
    assert mcpserver._check_relative_date_mismatch(
        "this year", [{"field": "sector", "op": "eq", "value": "Energy"}]
    ) is None


CASES = [
    ("dual + eq ECM stays ECM", test_dual_entitled_eq_ecm_stays_ecm),
    ("dual + unscoped injects both", test_dual_entitled_unscoped_gets_both_injected),
    ("single asking other product denied", test_single_entitled_asking_other_product_is_denied),
    ("product ne rejected, not inverted", test_negated_product_filter_is_rejected_not_inverted),
    ("invalid product rejected, not widened", test_invalid_product_value_is_rejected_not_widened),
    ("discovery carries entitled_products", test_discovery_carries_entitled_products),
    ("query responses carry bare scope", test_bare_scope_for_query_responses),
    ("stale this-year window refused", test_stale_this_year_window_is_refused),
    ("explicit historical ask passes", test_explicit_historical_ask_passes),
    ("anchored relative window passes", test_correctly_anchored_relative_window_passes),
    ("guard noops without question/dates", test_guard_noops_without_question_or_dates),
    ("scope absent when inactive/error", test_scope_not_attached_when_gate_inactive_or_error),
    ("import failure + flag on refuses", test_import_failure_with_enforcement_on_refuses),
    ("import failure + flag off permissive", test_import_failure_with_flag_off_stays_permissive),
    ("ok-with-no-products refuses", test_ok_with_no_products_refuses_when_flag_on),
]


if __name__ == "__main__":
    print()
    failures = 0
    for label, fn in CASES:
        setup_function()
        try:
            fn()
            print(f"  ok   {label}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {label}\n         {exc}")
        finally:
            teardown_function()
    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        sys.exit(1)
    print("The gate that ships is the gate under test.")
    sys.exit(0)
