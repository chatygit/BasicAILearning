"""The 0-row suggestion probes are cached — the retry must not re-pay them.

Observed in the 2026-08-11 warrants MCP log: a 0-row deal query paid
enrich=49.00s for two DISTINCT probes (equity_type, deal_status), the agent
retried with a widened status a minute later — the did_you_mean flow working
exactly as designed — and paid enrich=42.99s for the IDENTICAL probes again.
~92s of a ~110s double-round-trip was probe re-execution.

These cases pin the _cached_probe contract in bqs/suggestions.py:
  - identical (sql, params) within the TTL executes ONCE;
  - a different sql or params is a different entry;
  - TTL expiry re-executes;
  - ECM_DCM_SUGGESTION_CACHE_TTL_SECONDS <= 0 disables caching entirely;
  - the cache is bounded (no unbounded growth across a pod's lifetime).

Runs under pytest, or standalone. No third-party packages.
"""

from __future__ import annotations

import os
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
_stub("trino", __path__=[])
_stub("trino.dbapi", connect=lambda **_kw: None, Connection=object)
_stub("trino.auth", BasicAuthentication=object)
_stub("trino.exceptions", TrinoQueryError=type("TrinoQueryError", (Exception,), {}),
      TrinoUserError=type("TrinoUserError", (Exception,), {}))
_stub("rapidfuzz", fuzz=types.SimpleNamespace(WRatio=lambda *a, **k: 100,
                                              token_set_ratio=lambda *a, **k: 100))

from bqs import suggestions  # noqa: E402


class _FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


class _CountingExecute:
    def __init__(self):
        self.calls = 0

    def __call__(self, spec, built, dialect):
        self.calls += 1
        return ["value"], [("REAL VALUE %d" % self.calls,)]


def _fresh(ttl: str | None = "300"):
    """Reset cache/env/clock; return (counting_execute, fake_clock)."""
    suggestions._PROBE_CACHE.clear()
    if ttl is None:
        os.environ.pop("ECM_DCM_SUGGESTION_CACHE_TTL_SECONDS", None)
    else:
        os.environ["ECM_DCM_SUGGESTION_CACHE_TTL_SECONDS"] = ttl
    counting = _CountingExecute()
    clock = _FakeClock()
    suggestions.execute = counting
    suggestions.time = clock  # module read time.monotonic() at call time
    return counting, clock


def test_identical_probe_executes_once():
    counting, _clock = _fresh()
    r1 = suggestions._cached_probe(None, "SELECT 1", {"stem": "%WARRANT%"}, None)
    r2 = suggestions._cached_probe(None, "SELECT 1", {"stem": "%WARRANT%"}, None)
    assert counting.calls == 1, "identical probe re-executed within TTL"
    assert r1 == r2, "cache hit returned different rows"


def test_different_key_is_different_entry():
    counting, _clock = _fresh()
    suggestions._cached_probe(None, "SELECT 1", {"stem": "%WARRANT%"}, None)
    suggestions._cached_probe(None, "SELECT 1", {"stem": "%PRICED%"}, None)
    suggestions._cached_probe(None, "SELECT 2", {"stem": "%WARRANT%"}, None)
    assert counting.calls == 3, "distinct sql/params keys collided"


def test_ttl_expiry_reexecutes():
    counting, clock = _fresh(ttl="300")
    suggestions._cached_probe(None, "SELECT 1", {"stem": "%X%"}, None)
    clock.now += 301
    suggestions._cached_probe(None, "SELECT 1", {"stem": "%X%"}, None)
    assert counting.calls == 2, "expired entry served from cache"


def test_ttl_zero_disables():
    counting, _clock = _fresh(ttl="0")
    suggestions._cached_probe(None, "SELECT 1", {"stem": "%X%"}, None)
    suggestions._cached_probe(None, "SELECT 1", {"stem": "%X%"}, None)
    assert counting.calls == 2, "TTL<=0 must disable the cache"
    assert not suggestions._PROBE_CACHE, "disabled cache stored entries"


def test_cache_is_bounded():
    counting, _clock = _fresh()
    for i in range(suggestions._PROBE_CACHE_MAX + 40):
        suggestions._cached_probe(None, f"SELECT {i}", {}, None)
    assert len(suggestions._PROBE_CACHE) <= suggestions._PROBE_CACHE_MAX, (
        "probe cache grew past its bound"
    )


CASES = [
    test_identical_probe_executes_once,
    test_different_key_is_different_entry,
    test_ttl_expiry_reexecutes,
    test_ttl_zero_disables,
    test_cache_is_bounded,
]

if __name__ == "__main__":
    failed = 0
    for case in CASES:
        try:
            case()
            print(f"PASS {case.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {case.__name__}: {e}")
    sys.exit(1 if failed else 0)
