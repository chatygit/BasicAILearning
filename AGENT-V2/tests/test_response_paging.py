"""Response size is bounded, and paging is real.

Rows returned by run_bqs_query go straight into an LLM context. An omitted
`limit` used to resolve to the source's max_limit — 5000 rows — and a listing
that hit it ended the turn with RESOURCE_EXHAUSTED at roughly 300k tokens.

Two independent bounds, because they are two different concerns:
  planner   — the SQL limit: how much work the warehouse does
  formatter — the response cap: how much the model reads

And the fix is only half a fix without paging: capping rows while `offset` does
not exist makes rows 51+ permanently unreachable, which is exactly what the
skill promises the user ("ask for the next 50"). These cases pin both.

Runs under pytest, or standalone (`python3 tests/test_response_paging.py`).
No third-party packages — pydantic and yaml are stubbed if absent.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

APP = Path(__file__).parent.parent / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from bqs.formatter import (  # noqa: E402
    format_result,
    max_cell_chars,
    max_response_chars,
    max_response_rows,
)

_ENV = [
    "BQS_MAX_RESPONSE_ROWS",
    "BQS_DEFAULT_LIMIT",
    # The char/cell budgets are env-tunable too; without save/restore a
    # budget test would leak its tiny cap into every later test.
    "BQS_MAX_RESPONSE_CHARS",
    "BQS_MAX_CELL_CHARS",
]
_SAVED: dict[str, str | None] = {}


def setup_function(func=None) -> None:
    for k in _ENV:
        _SAVED[k] = os.environ.get(k)
        os.environ.pop(k, None)


def teardown_function(func=None) -> None:
    for k, v in _SAVED.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


COLS = ["deal_name", "deal_id", "total_deal_size"]


def make_rows(n: int, start: int = 0):
    return [(f"Deal {i}", f"D{i:05d}", i * 1000) for i in range(start, start + n)]


def fmt(rows, **kw):
    kw.setdefault("source", "capital_markets_deal")
    kw.setdefault("metric", "total_deal_size")
    kw.setdefault("sql_audit", "SELECT ...")
    kw.setdefault("row_count", len(rows))
    return format_result(COLS, rows, **kw)


# --------------------------------------------------------------------------
# the response cap
# --------------------------------------------------------------------------

def test_response_is_capped():
    res = fmt(make_rows(5000), limit=5000)
    assert len(res["rows"]) == max_response_rows() == 100, (
        f"{len(res['rows'])} rows reached the model — this is the "
        f"RESOURCE_EXHAUSTED path"
    )


def test_cap_is_tunable():
    os.environ["BQS_MAX_RESPONSE_ROWS"] = "10"
    assert len(fmt(make_rows(500), limit=500)["rows"]) == 10


def test_bad_cap_falls_back_to_default():
    os.environ["BQS_MAX_RESPONSE_ROWS"] = "not-a-number"
    assert max_response_rows() == 100
    os.environ["BQS_MAX_RESPONSE_ROWS"] = "0"
    assert max_response_rows() == 100, "0 would mean an empty response, not 'no cap'"


def test_small_result_is_untouched():
    res = fmt(make_rows(7), limit=50)
    assert len(res["rows"]) == 7
    assert "truncated" not in res
    assert "paging" not in res


def test_row_count_stays_truthful_when_clipped():
    res = fmt(make_rows(500), limit=5000)
    assert res["row_count"] == 500, "row_count must be what the QUERY returned"
    assert res["returned_rows"] == 100, "returned_rows is what the MODEL got"


# --------------------------------------------------------------------------
# knowing there is more
# --------------------------------------------------------------------------

def test_clipped_result_is_flagged_and_pageable():
    res = fmt(make_rows(500), limit=5000)
    assert res["truncated"] is True
    assert res["next_offset"] == 100
    assert "offset=100" in res["paging"]


def test_exactly_full_result_is_treated_as_more():
    # 50 rows against limit=50 is indistinguishable from "cut off at 50".
    res = fmt(make_rows(50), limit=50)
    assert res.get("truncated") is True
    assert res["next_offset"] == 50


def test_partial_page_is_the_end():
    res = fmt(make_rows(23), limit=50)
    assert "truncated" not in res, "23 of a possible 50 means the data ran out"


def test_second_page_continues_the_numbering():
    res = fmt(make_rows(50, start=50), limit=50, offset=50)
    assert res["offset"] == 50
    assert res["next_offset"] == 100
    assert "rows 51-100" in res["paging"]


def test_paging_text_forbids_raising_the_limit():
    text = fmt(make_rows(500), limit=5000)["paging"]
    assert "never ask for a bigger limit" in text.lower(), (
        "the agent's instinct on a truncated result is to re-run with a bigger "
        "limit, which is precisely what exhausts the context"
    )
    assert "count metric" in text.lower(), "a total should cost one row, not a page"


# --------------------------------------------------------------------------
# the character budget — the SECOND, independent bound (added 2026-08-11)
#
# The row cap does not bound the PAYLOAD, because row width is not bounded:
# the tranche object exposes nine VARCHAR2(32767) columns, so one legal row
# can carry ~250k characters. Reported before the budget existed: "when the
# SQL response is too large the LLM fails to parse" — a byte problem being
# measured in rows.
# --------------------------------------------------------------------------

def wide_rows(n: int, width: int = 5000):
    return [(f"Deal {i}", f"D{i:05d}", "x" * width) for i in range(n)]


def test_char_budget_binds_before_row_cap():
    os.environ["BQS_MAX_RESPONSE_CHARS"] = "20000"
    res = fmt(wide_rows(50), limit=50)
    assert 0 < res["returned_rows"] < 50, (
        f"{res['returned_rows']} wide rows reached the model — the char "
        f"budget never bound, which is the unparseable-response path"
    )
    # Whichever cap binds, the paging contract is IDENTICAL — the agent pages
    # the same way and the withheld rows stay reachable.
    assert res["truncated"] is True
    assert res["next_offset"] == res["returned_rows"]
    assert f"offset={res['returned_rows']}" in res["paging"]


def test_single_over_budget_row_is_still_returned():
    # The at-least-one-row rule (`if records and used + size > ...`). Without
    # `records and`, one wide row yields ZERO rows plus truncated=True, which
    # the agent reads as "no data" and reports "nothing found" to the banker —
    # while claiming there is more.
    os.environ["BQS_MAX_RESPONSE_CHARS"] = "1000"
    res = fmt(wide_rows(1, width=50_000), limit=50)
    assert res["returned_rows"] == 1, (
        "a single row over the whole budget must be clipped and returned, "
        "never dropped to zero"
    )


def test_over_long_cell_is_clipped_with_marker():
    os.environ["BQS_MAX_CELL_CHARS"] = "200"
    res = fmt(wide_rows(1, width=50_000), limit=50)
    cell = res["rows"][0]["total_deal_size"]
    assert len(cell) == 200, f"cell is {len(cell)} chars, budget is 200"
    assert cell.endswith("…[truncated]"), (
        "the marker is the agent's signal to stop zipping pipe-list pairs "
        "(declared in SKILL.md and the tranche ontology)"
    )
    # Non-string cells pass through untouched — clipping is for text only.
    assert res["rows"][0]["deal_name"] == "Deal 0"


def test_row_count_stays_truthful_under_char_clipping():
    os.environ["BQS_MAX_RESPONSE_CHARS"] = "20000"
    res = fmt(wide_rows(50), limit=50)
    assert res["row_count"] == 50, "row_count is what the QUERY returned"
    assert res["returned_rows"] == len(res["rows"]), (
        "returned_rows is what the MODEL got"
    )


def test_bad_char_budgets_fall_back_to_defaults():
    os.environ["BQS_MAX_RESPONSE_CHARS"] = "not-a-number"
    os.environ["BQS_MAX_CELL_CHARS"] = "-5"
    assert max_response_chars() == 120_000
    assert max_cell_chars() == 4_000


# --------------------------------------------------------------------------
# planner: the SQL side (pydantic/yaml stubbed when absent)
# --------------------------------------------------------------------------

SKIPPED: list[str] = []


def _load_planner():
    """planner imports models, which imports pydantic. Absent here, present in
    the repo — so this must SKIP LOUDLY rather than pass by doing nothing."""
    try:
        import pydantic  # noqa: F401
        import yaml  # noqa: F401
    except ImportError:
        SKIPPED.append("planner limit default (pydantic/yaml not installed)")
        return None
    from bqs.planner import _default_row_limit
    return _default_row_limit


def test_omitted_limit_is_a_small_page_not_max_limit():
    fn = _load_planner()
    if fn is None:
        return  # reported as SKIPPED, and covered textually by ontology_check
    assert fn() == 50, (
        "an omitted limit must resolve to a small page — resolving it to "
        "spec.max_limit (5000) is what put 300k tokens in a context"
    )
    os.environ["BQS_DEFAULT_LIMIT"] = "25"
    assert fn() == 25
    os.environ["BQS_DEFAULT_LIMIT"] = "junk"
    assert fn() == 50


def test_offset_clause_is_inherited_and_coerced():
    # Every dialect gets offset_clause from the base, so a dialect added later
    # cannot page-crash for want of an override. Called unbound to avoid
    # implementing the whole abstract surface just to read one string.
    from bqs.dialects.base import BaseDialect

    assert BaseDialect.offset_clause(None, 50) == "OFFSET 50"
    assert BaseDialect.offset_clause(None, "50") == "OFFSET 50", (
        "offset must be coerced to int, never interpolated raw into SQL"
    )
    try:
        BaseDialect.offset_clause(None, "50; DROP TABLE x")
    except ValueError:
        pass
    else:
        raise AssertionError("a non-numeric offset must raise, not reach the SQL")


def test_trino_inherits_offset_clause():
    from bqs.dialects.base import BaseDialect
    from bqs.dialects.trino import TrinoDialect

    assert TrinoDialect.offset_clause is BaseDialect.offset_clause


CASES = [
    ("response is capped", test_response_is_capped),
    ("cap is tunable", test_cap_is_tunable),
    ("bad cap falls back", test_bad_cap_falls_back_to_default),
    ("small result untouched", test_small_result_is_untouched),
    ("row_count stays truthful", test_row_count_stays_truthful_when_clipped),
    ("clipped result is pageable", test_clipped_result_is_flagged_and_pageable),
    ("exactly-full means more", test_exactly_full_result_is_treated_as_more),
    ("partial page is the end", test_partial_page_is_the_end),
    ("page 2 continues numbering", test_second_page_continues_the_numbering),
    ("paging text forbids bigger limit", test_paging_text_forbids_raising_the_limit),
    ("char budget binds before row cap", test_char_budget_binds_before_row_cap),
    ("single over-budget row still returned", test_single_over_budget_row_is_still_returned),
    ("over-long cell clipped with marker", test_over_long_cell_is_clipped_with_marker),
    ("row_count truthful under char clipping", test_row_count_stays_truthful_under_char_clipping),
    ("bad char budgets fall back", test_bad_char_budgets_fall_back_to_defaults),
    ("omitted limit is a small page", test_omitted_limit_is_a_small_page_not_max_limit),
    ("OFFSET is coerced, not interpolated", test_offset_clause_is_inherited_and_coerced),
    ("trino inherits offset_clause", test_trino_inherits_offset_clause),
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
    for note in SKIPPED:
        print(f"  SKIP {note} — asserted textually by _review/ontology_check.py")
    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        sys.exit(1)
    print("One query cannot blow the context, and the rows it withheld are reachable.")
    sys.exit(0)
