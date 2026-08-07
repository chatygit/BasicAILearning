"""Caller-identity resolution: header first, then query param, then fallback.

QA showed `user_id=<empty> (via=<none>)` on every inbound /mcp request while the
same platform reaches the nl2sql server as `/mcp?user_id=<soeid>`. Header-only
resolution can never see that, and an empty SOEID makes the entitlement gate
deny with `missing_soeid`.

These cases pin the contract:
  - a header ALWAYS wins over a query param (headers are the trusted channel)
  - the documented header aliases still resolve, in priority order
  - `?user_id=` / `?soeid=` resolve when no header is present
  - values are trimmed
  - nothing present -> empty (or the explicit MCP_FALLBACK_USER_ID)

Runs under pytest, or standalone (`python3 tests/test_soeid_resolution.py`).
Starlette is stubbed so this runs with no third-party packages installed.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

APP = Path(__file__).parent.parent / "app"


def _load_middleware():
    """Import soeid_middleware with starlette stubbed out."""
    if "starlette" not in sys.modules:
        starlette = types.ModuleType("starlette")
        mw = types.ModuleType("starlette.middleware")
        base = types.ModuleType("starlette.middleware.base")
        requests = types.ModuleType("starlette.requests")

        class BaseHTTPMiddleware:  # minimal stand-in
            def __init__(self, app=None, **kwargs):
                self.app = app

        class Request:  # only used as a type annotation
            pass

        base.BaseHTTPMiddleware = BaseHTTPMiddleware
        requests.Request = Request
        mw.base = base
        starlette.middleware = mw
        starlette.requests = requests
        sys.modules.update({
            "starlette": starlette,
            "starlette.middleware": mw,
            "starlette.middleware.base": base,
            "starlette.requests": requests,
        })

    if str(APP) not in sys.path:
        sys.path.insert(0, str(APP))
    from middleware import soeid_middleware  # noqa: E402
    return soeid_middleware


class FakeRequest:
    """Just enough Request surface for _resolve_user_id."""

    def __init__(self, headers=None, query=None):
        self.headers = dict(headers or {})
        self.query_params = dict(query or {})


# (label, headers, query, expected_user_id, expected_source)
CASES = [
    ("header x-user-id",
     {"x-user-id": "bk42867"}, {}, "bk42867", "x-user-id"),
    ("header beats query param",
     {"x-user-id": "hdr001"}, {"user_id": "qry001"}, "hdr001", "x-user-id"),
    ("header alias x-citi-soeid",
     {"x-citi-soeid": "aa11111"}, {}, "aa11111", "x-citi-soeid"),
    ("header priority: x-user-id before alias",
     {"x-user-id": "first", "x-soeid": "second"}, {}, "first", "x-user-id"),
    ("query ?user_id= (the nl2sql channel)",
     {}, {"user_id": "bk42867"}, "bk42867", "?user_id"),
    ("query ?soeid=",
     {}, {"soeid": "zz11111"}, "zz11111", "?soeid"),
    ("query ?user_id= wins over ?soeid=",
     {}, {"soeid": "second", "user_id": "first"}, "first", "?user_id"),
    ("whitespace trimmed (header)",
     {"x-user-id": "  bk1  "}, {}, "bk1", "x-user-id"),
    ("whitespace trimmed (query)",
     {}, {"user_id": " bk1 "}, "bk1", "?user_id"),
    ("empty header falls through to query",
     {"x-user-id": ""}, {"user_id": "bk42867"}, "bk42867", "?user_id"),
    ("nothing present -> empty, no source",
     {}, {}, "", ""),
    ("unrelated query params ignored",
     {}, {"limit": "10"}, "", ""),
]


def run():
    sm = _load_middleware()
    results = []
    for label, headers, query, want_id, want_src in CASES:
        got_id, got_src = sm._resolve_user_id(FakeRequest(headers, query))
        results.append((label, got_id, got_src, want_id, want_src,
                        got_id == want_id and got_src == want_src))
    return results


def test_soeid_resolution():
    for label, got_id, got_src, want_id, want_src, ok in run():
        assert ok, f"{label}: got ({got_id!r}, {got_src!r}), want ({want_id!r}, {want_src!r})"


def test_header_list_still_complete():
    """The documented aliases must not be dropped while adding query support."""
    sm = _load_middleware()
    for name in ("x-user-id", "x-citiportal-loginid", "x-citi-soeid", "x-soeid",
                 "soeid", "x-authenticated-userid", "x-forwarded-user",
                 "x-remote-user"):
        assert name in sm.CANDIDATE_ID_HEADERS, f"lost header alias: {name}"
    assert sm.CANDIDATE_ID_HEADERS.index("x-user-id") < len(sm.CANDIDATE_ID_HEADERS)
    assert "user_id" in sm.CANDIDATE_ID_QUERY_PARAMS


if __name__ == "__main__":
    rows = run()
    print()
    print(f"{'case':<44} {'user_id':<12} {'via':<16} {'verdict'}")
    print("-" * 88)
    failures = 0
    for label, got_id, got_src, want_id, want_src, ok in rows:
        failures += not ok
        verdict = "ok" if ok else f"FAIL want ({want_id!r}, {want_src!r})"
        print(f"{label[:43]:<44} {(got_id or '<empty>'):<12} "
              f"{(got_src or '<none>'):<16} {verdict}")
    try:
        test_header_list_still_complete()
        print(f"\n{'header alias list intact':<44} {'':<12} {'':<16} ok")
    except AssertionError as exc:
        failures += 1
        print(f"\nFAIL {exc}")
    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        sys.exit(1)
    print("Identity resolves from header first, then ?user_id=/?soeid=, "
          "then the explicit fallback.")
    sys.exit(0)
