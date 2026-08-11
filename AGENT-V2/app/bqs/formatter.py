"""Result formatter — shapes DB rows into the agent-facing response.

Returns only business names (column aliases), never physical schema.

THIS IS THE LAST PLACE BEFORE AN LLM CONTEXT. Whatever `rows` holds here gets
serialised into a tool result and read by the model, so the caps below are a
hard bound on the tokens one query can cost. They are not the same bound as the
SQL `limit`: that one decides how much work the warehouse does, these decide
how much the model reads. A listing with no explicit limit used to resolve to
the source's max_limit (5000 rows) and ended the turn with RESOURCE_EXHAUSTED at
roughly 300k tokens.

There are TWO caps, and both are needed. Rows bound the count; characters bound
the SIZE. A row cap alone does not bound the payload because row width is not
bounded — see _DEFAULT_MAX_RESPONSE_CHARS. Whichever binds first wins, and
either one sets the same `truncated` / `next_offset` / `paging` contract, so
the agent pages identically no matter which limit it hit.
"""

from __future__ import annotations

import os
from typing import Any

# Rows put in front of the model per call. Tune with BQS_MAX_RESPONSE_ROWS.
_DEFAULT_MAX_RESPONSE_ROWS = 100

# Characters put in front of the model per call. Tune with BQS_MAX_RESPONSE_CHARS.
#
# WHY A SECOND BOUND. The row cap alone does not bound the payload, because row
# WIDTH is unbounded. The tranche object exposes nine VARCHAR2(32767) columns —
# SYNDICATE_MEMBER_NAME, SYNDICATE_ROLE, BROKER_CODE, BND_BROKER,
# IDENTIFIER_TYPE, IDENTIFIER_VALUE, DELIVERY_TYPE, ISSUER_RATINGS, DEAL_NAME —
# so ONE legal row can carry ~250k characters and 100 of them are unbounded in
# practice. Symptom reported from local runs: "when the SQL response is too
# large the LLM fails to parse". That is a byte problem being measured in rows.
#
# ~120k chars is roughly 30k tokens — large enough that no ordinary listing is
# affected, small enough that a pathological wide result degrades into a paged
# answer instead of an unparseable one.
_DEFAULT_MAX_RESPONSE_CHARS = 120_000

# A single cell that alone would blow the budget is truncated rather than
# dropping the whole row: losing one long pipe-list is recoverable, losing the
# row's ids is not.
#
# ZIP-ALIGNMENT HAZARD. Several columns are pipe lists that pair BY POSITION —
# identifier_type/identifier_value, and syndicate_member_name/syndicate_role/
# broker_code/bnd_broker. Clipping is per-cell, so the LONGER of a pair hits
# the budget first and loses more elements, which silently misaligns the pairs.
# The budget is far above the measured maximum (531 chars) so this should never
# fire in practice, but when it does the marker below is the agent's signal to
# STOP ZIPPING that row rather than pair the lists wrongly. The marker is
# declared in SKILL.md and in the tranche ontology so the agent can recognise it.
_DEFAULT_MAX_CELL_CHARS = 4_000

_TRUNCATION_MARK = "…[truncated]"


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def max_response_rows() -> int:
    return _env_int("BQS_MAX_RESPONSE_ROWS", _DEFAULT_MAX_RESPONSE_ROWS)


def max_response_chars() -> int:
    return _env_int("BQS_MAX_RESPONSE_CHARS", _DEFAULT_MAX_RESPONSE_CHARS)


def max_cell_chars() -> int:
    return _env_int("BQS_MAX_CELL_CHARS", _DEFAULT_MAX_CELL_CHARS)


def _clip_cell(value: Any, budget: int) -> Any:
    """Shorten one over-long string cell, leaving non-strings untouched."""
    if isinstance(value, str) and len(value) > budget:
        return value[: budget - len(_TRUNCATION_MARK)] + _TRUNCATION_MARK
    return value


def _rows_within_budget(
    columns: list[str], rows: list[tuple], row_cap: int
) -> list[dict[str, Any]]:
    """Take rows up to BOTH the row cap and the character budget.

    Always yields at least one row when any exist: a single row over budget is
    clipped cell-wise and returned, because handing the model zero rows plus
    `truncated` reads as "no data" and it will not page.
    """
    char_budget = max_response_chars()
    cell_budget = max_cell_chars()
    records: list[dict[str, Any]] = []
    used = 0
    for row in rows[:row_cap]:
        record = {c: _clip_cell(v, cell_budget) for c, v in zip(columns, row)}
        size = sum(len(c) + len(str(v)) + 4 for c, v in record.items())
        if records and used + size > char_budget:
            break
        records.append(record)
        used += size
    return records


def format_result(columns: list[str], rows: list[tuple], *, source: str,
                  metric: str, sql_audit: str, row_count: int,
                  as_of_date: str | None = None,
                  offset: int = 0, limit: int = 0) -> dict:
    cap = max_response_rows()
    records = _rows_within_budget(columns, rows, cap)

    result = {
        "error": False,
        "source": source,
        "metric": metric,
        "columns": columns,
        # Rows the QUERY returned. May exceed len(rows) below — see returned_rows.
        "row_count": row_count,
        "returned_rows": len(records),
        "rows": records,
        # SQL text is safe to surface for transparency; contains no secrets.
        "generated_sql": sql_audit,
    }

    # More rows exist when we clipped the response, or when the query came back
    # exactly full — a result that fills its limit is indistinguishable from one
    # that was cut off by it, so treat both as "there may be more".
    clipped = len(rows) > len(records)
    filled_limit = bool(limit) and row_count >= limit
    if offset:
        result["offset"] = offset
    if clipped or filled_limit:
        result["truncated"] = True
        result["next_offset"] = offset + len(records)
        result["paging"] = (
            f"Showing rows {offset + 1}-{offset + len(records)}. More rows exist. "
            f"To continue, repeat this EXACT request with offset="
            f"{offset + len(records)} — every other field identical, or you are "
            f"paging through a different result set. Keep numbering the rows "
            f"from where this page ended; do not restart at 1. Never ask for a "
            f"bigger limit instead: that is what exhausts the context. If the "
            f"user wants a TOTAL rather than more rows, use a count metric."
        )

    # Latest date the data is available till — drives the agent's
    # "Data as of: <Month YYYY>" header and absolute-year period labels.
    if as_of_date is not None:
        result["as_of_date"] = as_of_date
    return result

# NOTE: the response key the agent sees is `generated_sql`; `sql_audit` is only
# the parameter name. "Safe to surface" here means it leaks no credentials — it
# still exposes physical table/column names, which is why the ECM/DCM skill
# forbids showing it to a user. Both statements are true; don't reconcile them
# by relaxing the skill.
#
# NOTE: `row_count` is what the QUERY returned and `returned_rows` is what the
# model was given; they differ exactly when the response was clipped. Neither is
# the number of rows that MATCH — a limited query cannot know that. An agent
# that wants a total must ask for a count metric, which is one row instead of
# thousands. The skill says the same thing from the other direction: a list
# request returns rows, never a count.
