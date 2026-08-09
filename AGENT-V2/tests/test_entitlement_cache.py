"""Entitlement caching, failure taxonomy and error-message hygiene.

The ECMO entitlement API sits in front of EVERY query. Before this, the service
called it live on every single one, and a single API blip flipped an active
session to "you have no ECM/DCM access". These cases pin the contract:

  - one API call per SOEID per TTL, not one per query
  - a transient failure falls back to the LAST KNOWN-GOOD scope
  - ...but a MISCONFIGURED deployment never does, and never claims a scope it
    can no longer verify
  - a stale scope expires, so a revocation still lands during an outage
  - a connection error / timeout returns a governed dict instead of escaping
    into run_bqs_query, which has no exception handler of its own
  - a 200 carrying a proxy's HTML error page is transient, not "misconfigured"
  - `reason` is a stable slug: mcpserver copies it into the agent-facing error
    `code`, so an upstream response body must never reach it

Runs under pytest, or standalone (`python3 tests/test_entitlement_cache.py`).
No third-party packages and no real HTTP: if `requests` is unavailable a stub is
injected JUST long enough to import the module, then removed from sys.modules so
nothing else in the suite ever sees it.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import types
from pathlib import Path

APP = Path(__file__).parent.parent / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))


def _install_requests_stub() -> list[str]:
    """Only when the real package is missing. Returns the names we injected."""
    try:
        import requests  # noqa: F401

        return []
    except ImportError:
        pass

    injected: list[str] = []

    requests_mod = types.ModuleType("requests")

    class RequestException(Exception):
        pass

    class Session:
        def mount(self, prefix, adapter):
            pass

        def post(self, *args, **kwargs):
            raise AssertionError("the real session must never be used in tests")

    requests_mod.RequestException = RequestException
    requests_mod.Session = Session

    adapters_mod = types.ModuleType("requests.adapters")

    class HTTPAdapter:
        def __init__(self, **kwargs):
            pass

    adapters_mod.HTTPAdapter = HTTPAdapter
    requests_mod.adapters = adapters_mod

    urllib3_mod = types.ModuleType("urllib3")
    util_mod = types.ModuleType("urllib3.util")
    retry_mod = types.ModuleType("urllib3.util.retry")

    class Retry:
        def __init__(self, **kwargs):
            pass

    retry_mod.Retry = Retry
    util_mod.retry = retry_mod
    urllib3_mod.util = util_mod

    for name, mod in [
        ("requests", requests_mod),
        ("requests.adapters", adapters_mod),
        ("urllib3", urllib3_mod),
        ("urllib3.util", util_mod),
        ("urllib3.util.retry", retry_mod),
    ]:
        sys.modules[name] = mod
        injected.append(name)
    return injected


_INJECTED = _install_requests_stub()

from services import entitlement_service as ent  # noqa: E402

# Hand sys.modules back exactly as found. `ent` keeps its own references, so it
# still works; nothing LATER in the suite can accidentally import our fake.
for _name in _INJECTED:
    sys.modules.pop(_name, None)


REQUEST_EXCEPTION = ent.requests.RequestException

CALLS: list[str] = []
POST_DELAY = 0.0

# What the fake endpoint does next: ("json", payload) | ("status", code)
#   | ("raise", exc) | ("badjson", None)
BEHAVIOUR: tuple = ("json", {"entitled_products": ["ECM", "DCM"]})


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", raises_on_json=False):
        self.status_code = status_code
        self.text = text
        self._payload = payload
        self._raises_on_json = raises_on_json

    def json(self):
        if self._raises_on_json:
            # requests' JSONDecodeError subclasses ValueError — that inheritance
            # is exactly what used to misroute this into "misconfigured".
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class _FakeSession:
    def post(self, url, **kwargs):
        CALLS.append(kwargs.get("json", {}).get("soeid", ""))
        if POST_DELAY:
            time.sleep(POST_DELAY)
        kind, value = BEHAVIOUR
        if kind == "json":
            return _FakeResponse(200, payload=value)
        if kind == "status":
            return _FakeResponse(value, payload=None, text="<html>gateway error</html>")
        if kind == "badjson":
            return _FakeResponse(200, raises_on_json=True, text="<html>proxy</html>")
        if kind == "raise":
            raise value
        raise AssertionError(f"unknown behaviour {kind!r}")


_ORIG_GET_SESSION = ent._get_session
_ENV_KEYS = [
    "ECM_DCM_PRODUCT_ENTITLEMENT_URL",
    "ECM_DCM_ENTITLEMENT_POLICY_ID",
    "ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS",
    "ECM_DCM_ENTITLEMENT_STALE_MAX_AGE_SECONDS",
]
_ENV_SAVED: dict[str, str | None] = {}


def setup_function(func=None) -> None:
    global BEHAVIOUR, POST_DELAY
    for key in _ENV_KEYS:
        _ENV_SAVED[key] = os.environ.get(key)
    ent._get_session = lambda: _FakeSession()
    ent.clear_entitlement_cache()
    CALLS.clear()
    POST_DELAY = 0.0
    BEHAVIOUR = ("json", {"entitled_products": ["ECM", "DCM"]})
    os.environ["ECM_DCM_PRODUCT_ENTITLEMENT_URL"] = "https://entitlement.example/api"
    os.environ["ECM_DCM_ENTITLEMENT_POLICY_ID"] = "policy-123"
    os.environ["ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS"] = "300"
    os.environ["ECM_DCM_ENTITLEMENT_STALE_MAX_AGE_SECONDS"] = "3600"


def teardown_function(func=None) -> None:
    ent._get_session = _ORIG_GET_SESSION
    ent.clear_entitlement_cache()
    for key, val in _ENV_SAVED.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val


def check(soeid="bk42867"):
    return ent.perform_initial_entitlement_check(soeid)


# --------------------------------------------------------------------------
# caching
# --------------------------------------------------------------------------

def test_repeated_queries_hit_the_api_once():
    for _ in range(4):
        assert check()["ok"]
    assert len(CALLS) == 1, f"expected 1 API call, got {len(CALLS)}"


def test_second_call_reports_source_cache():
    assert check()["entitlement_source"] == "api"
    assert check()["entitlement_source"] == "cache"


def test_distinct_soeids_cached_separately():
    check("bk42867")
    check("sr37832")
    check("bk42867")
    assert len(CALLS) == 2


def test_cache_key_is_case_insensitive():
    check("bk42867")
    check("BK42867")
    assert len(CALLS) == 1, "a SOEID identifies a person, not a spelling"


def test_ttl_expiry_refetches():
    os.environ["ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS"] = "1"
    check()
    time.sleep(1.1)
    check()
    assert len(CALLS) == 2


def test_ttl_zero_disables_the_cache():
    os.environ["ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS"] = "0"
    check()
    check()
    assert len(CALLS) == 2


def test_denial_is_not_cached():
    global BEHAVIOUR
    BEHAVIOUR = ("json", {"entitled_products": []})
    assert check()["reason"] == "no_ecm_dcm_entitlement"
    assert check()["reason"] == "no_ecm_dcm_entitlement"
    assert len(CALLS) == 2, "a denial must be re-checked, not pinned for the TTL"


def test_concurrent_cold_callers_make_one_api_call():
    global POST_DELAY
    POST_DELAY = 0.25
    threads = [threading.Thread(target=check) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(CALLS) == 1, (
        f"8 concurrent cold callers made {len(CALLS)} API calls — the per-SOEID "
        f"lock is not collapsing the stampede"
    )


# --------------------------------------------------------------------------
# failure taxonomy
# --------------------------------------------------------------------------

def test_transient_failure_falls_back_to_last_known_good():
    global BEHAVIOUR
    check()                                              # warm the cache
    os.environ["ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS"] = "0.01"
    time.sleep(0.05)
    BEHAVIOUR = ("status", 503)
    res = check()
    assert res["ok"] is True, "an API blip must not revoke an active session"
    assert res["entitlement_source"] == "cache_fallback"
    assert res["entitled_products"] == ["ECM", "DCM"]


def test_transient_failure_with_no_cache_denies_retryably():
    global BEHAVIOUR
    BEHAVIOUR = ("status", 503)
    res = check()
    assert res["ok"] is False
    assert res["reason"] == "entitlement_unavailable"
    assert res["retryable"] is True


def test_stale_scope_expires_so_revocation_still_lands():
    global BEHAVIOUR
    check()
    os.environ["ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS"] = "0.01"
    os.environ["ECM_DCM_ENTITLEMENT_STALE_MAX_AGE_SECONDS"] = "0.05"
    time.sleep(0.1)
    BEHAVIOUR = ("status", 503)
    res = check()
    assert res["ok"] is False, "a scope this old must not keep being served"
    assert res["reason"] == "entitlement_unavailable"


def test_misconfiguration_is_not_retryable():
    os.environ.pop("ECM_DCM_PRODUCT_ENTITLEMENT_URL", None)
    res = check()
    assert res["ok"] is False
    assert res["reason"] == "entitlement_misconfigured"
    assert res["retryable"] is False


def test_misconfiguration_never_serves_a_stale_scope():
    check()                                              # warm the cache
    os.environ["ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS"] = "0.01"
    time.sleep(0.05)
    os.environ.pop("ECM_DCM_ENTITLEMENT_POLICY_ID", None)
    res = check()
    assert res["ok"] is False, (
        "if the deployment is wrong we cannot verify the scope, so we must not "
        "keep answering from it"
    )
    assert res["reason"] == "entitlement_misconfigured"


def test_connection_error_does_not_escape():
    global BEHAVIOUR
    BEHAVIOUR = ("raise", REQUEST_EXCEPTION("connection refused"))
    # A RequestException is an OSError, not a RuntimeError. It used to propagate
    # out of run_bqs_query, which has no handler, and reach the agent as a crash.
    res = check()
    assert res["ok"] is False
    assert res["reason"] == "entitlement_unavailable"


def test_timeout_does_not_escape():
    global BEHAVIOUR
    BEHAVIOUR = ("raise", REQUEST_EXCEPTION("Read timed out"))
    assert check()["reason"] == "entitlement_unavailable"


def test_unparseable_200_is_transient_not_misconfigured():
    global BEHAVIOUR
    BEHAVIOUR = ("badjson", None)
    res = check()
    assert res["reason"] == "entitlement_unavailable", (
        "an HTML error page from a proxy is an outage — telling the user the "
        "service is misconfigured sends them to the wrong team"
    )
    assert res["retryable"] is True


# --------------------------------------------------------------------------
# message hygiene — `reason` becomes the agent-facing error code
# --------------------------------------------------------------------------

_STABLE_REASONS = {
    "missing_soeid",
    "no_ecm_dcm_entitlement",
    "entitlement_misconfigured",
    "entitlement_unavailable",
}


def test_reason_is_always_a_stable_slug():
    global BEHAVIOUR
    seen = []

    BEHAVIOUR = ("status", 500)
    seen.append(check("a1")["reason"])
    BEHAVIOUR = ("raise", REQUEST_EXCEPTION("boom"))
    seen.append(check("a2")["reason"])
    BEHAVIOUR = ("badjson", None)
    seen.append(check("a3")["reason"])
    BEHAVIOUR = ("json", {"entitled_products": []})
    seen.append(check("a4")["reason"])
    seen.append(ent.perform_initial_entitlement_check(None)["reason"])
    os.environ.pop("ECM_DCM_PRODUCT_ENTITLEMENT_URL", None)
    seen.append(check("a5")["reason"])

    for reason in seen:
        assert reason in _STABLE_REASONS, f"{reason!r} is not a stable slug"


def test_response_body_never_leaks_into_the_reason():
    global BEHAVIOUR
    BEHAVIOUR = ("status", 500)
    res = check()
    blob = f"{res.get('reason')} {res.get('user_message')}"
    assert "html" not in blob.lower(), "the upstream body reached the agent"
    assert "gateway error" not in blob.lower()


# --------------------------------------------------------------------------
# contract preserved for the other callers of this function
# --------------------------------------------------------------------------

def test_feature_flag_off_grants_both_products():
    res = ent.perform_initial_entitlement_check("bk42867", entitlement_enabled=False)
    assert res["ok"] is True
    assert res["entitled_products"] == ["ECM", "DCM"]
    assert res["entitlement_check_skipped"] is True
    assert not CALLS, "the flag being off must not call the API"


def test_missing_soeid_is_refused():
    res = ent.perform_initial_entitlement_check("")
    assert res["ok"] is False and res["reason"] == "missing_soeid"
    assert not CALLS


def test_product_clause_shape_is_unchanged():
    global BEHAVIOUR
    assert check()["product_clause"] == "PRODUCT IN ('ECM', 'DCM')"
    ent.clear_entitlement_cache()
    BEHAVIOUR = ("json", {"entitled_products": ["DCM"]})
    assert check()["product_clause"] == "PRODUCT = 'DCM'"


def test_clause_shaped_response_still_parsed():
    global BEHAVIOUR
    BEHAVIOUR = ("json", {"whereClause": "PRODUCT IN ('ECM')"})
    res = check()
    assert res["entitled_products"] == ["ECM"]


# --------------------------------------------------------------------------
# the parser must stay NARROW — it decides what a person may see
# --------------------------------------------------------------------------

def test_clause_list_shape_is_parsed():
    global BEHAVIOUR
    BEHAVIOUR = ("json", {"sqlClauses": [{"sqlClause": "PRODUCT = 'DCM'"}]})
    assert check()["entitled_products"] == ["DCM"]


def test_genuinely_empty_is_a_denial():
    global BEHAVIOUR
    # Observed for real against QAT 2026-08-09: a SOEID with no ECM/DCM grant.
    # This must stay a denial no matter how forgiving the parser gets.
    BEHAVIOUR = ("json", {"soeid": "bk42867", "clauses": []})
    assert check()["reason"] == "no_ecm_dcm_entitlement"


def test_unknown_envelope_is_a_denial_not_a_guess():
    global BEHAVIOUR
    # A shape we do not recognise must DENY and log its shape — never go
    # hunting for an ECM/DCM token somewhere inside it.
    BEHAVIOUR = ("json", {"result": {"entitledProducts": ["ECM"]}})
    assert check()["reason"] == "no_ecm_dcm_entitlement", (
        "the parser is digging into unrecognised envelopes — that is how a "
        "grant gets read out of text that never granted anything"
    )


def test_top_level_array_is_a_denial_not_a_guess():
    global BEHAVIOUR
    BEHAVIOUR = ("json", ["PRODUCT IN ('ECM','DCM')"])
    assert check()["reason"] == "no_ecm_dcm_entitlement"


def test_unrelated_products_are_not_matched():
    global BEHAVIOUR
    BEHAVIOUR = ("json", {"products": ["FX", "RATES"]})
    assert check()["reason"] == "no_ecm_dcm_entitlement"


def test_shape_is_described_without_values():
    shape = ent._describe_shape(
        {"status": "OK", "data": [{"sqlClause": "PRODUCT = 'ECM'", "id": 7}]}
    )
    assert "status" in shape and "data" in shape
    assert "OK" not in shape, "a value leaked into the shape description"
    assert "ECM" not in shape, "a clause leaked into the shape description"


def test_session_is_built_once():
    ent._get_session = _ORIG_GET_SESSION
    built = []
    orig_build = ent._build_session
    ent._build_session = lambda: (built.append(1), _FakeSession())[1]
    ent._SESSION = None
    try:
        check("u1")
        check("u2")
        check("u3")
        assert len(built) == 1, f"built {len(built)} sessions — pooling is lost"
    finally:
        ent._build_session = orig_build
        ent._SESSION = None
        ent._get_session = lambda: _FakeSession()


CASES = [
    ("repeated queries hit the API once", test_repeated_queries_hit_the_api_once),
    ("second call reports source=cache", test_second_call_reports_source_cache),
    ("distinct SOEIDs cached separately", test_distinct_soeids_cached_separately),
    ("cache key is case-insensitive", test_cache_key_is_case_insensitive),
    ("TTL expiry re-fetches", test_ttl_expiry_refetches),
    ("TTL 0 disables the cache", test_ttl_zero_disables_the_cache),
    ("a denial is never cached", test_denial_is_not_cached),
    ("8 concurrent cold callers -> 1 API call", test_concurrent_cold_callers_make_one_api_call),
    ("transient failure -> last known-good", test_transient_failure_falls_back_to_last_known_good),
    ("transient + cold -> retryable denial", test_transient_failure_with_no_cache_denies_retryably),
    ("stale scope expires", test_stale_scope_expires_so_revocation_still_lands),
    ("misconfiguration is not retryable", test_misconfiguration_is_not_retryable),
    ("misconfiguration never serves stale", test_misconfiguration_never_serves_a_stale_scope),
    ("connection error does not escape", test_connection_error_does_not_escape),
    ("timeout does not escape", test_timeout_does_not_escape),
    ("unparseable 200 is transient", test_unparseable_200_is_transient_not_misconfigured),
    ("reason is always a stable slug", test_reason_is_always_a_stable_slug),
    ("response body never leaks", test_response_body_never_leaks_into_the_reason),
    ("flag off grants ECM+DCM", test_feature_flag_off_grants_both_products),
    ("missing soeid is refused", test_missing_soeid_is_refused),
    ("product_clause shape unchanged", test_product_clause_shape_is_unchanged),
    ("clause-shaped response parsed", test_clause_shaped_response_still_parsed),
    ("clause-list shape is parsed", test_clause_list_shape_is_parsed),
    ("genuinely empty is a denial", test_genuinely_empty_is_a_denial),
    ("unknown envelope denies, no guessing", test_unknown_envelope_is_a_denial_not_a_guess),
    ("top-level array denies, no guessing", test_top_level_array_is_a_denial_not_a_guess),
    ("unrelated products not matched", test_unrelated_products_are_not_matched),
    ("shape logged without values", test_shape_is_described_without_values),
    ("session is built once", test_session_is_built_once),
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
    if ent._get_session is not _ORIG_GET_SESSION:
        failures += 1
        print("  FAIL module left monkeypatched — later tests would see the fake")
    else:
        print("  ok   module restored (no leak into the rest of the suite)")
    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        sys.exit(1)
    print("The ECMO API is called once per SOEID per TTL, and every failure mode "
          "returns a governed answer.")
    sys.exit(0)
