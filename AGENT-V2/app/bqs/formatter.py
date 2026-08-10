"""Result formatter — shapes DB rows into the agent-facing response.

Returns only business names (column aliases), never physical schema.

THIS IS THE LAST PLACE BEFORE AN LLM CONTEXT. Whatever `rows` holds here gets
serialised into a tool result and read by the model, so the row cap below is a
hard bound on the tokens one query can cost. It is not the same bound as the
SQL `limit`: that one decides how much work the warehouse does, this one decides
how much the model reads. A listing with no explicit limit used to resolve to
the source's max_limit (5000 rows) and ended the turn with RESOURCE_EXHAUSTED at
roughly 300k tokens.
"""

from __future__ import annotations

import os
from typing import Any

# Rows put in front of the model per call. Tune with BQS_MAX_RESPONSE_ROWS.
_DEFAULT_MAX_RESPONSE_ROWS = 100


def max_response_rows() -> int:
    try:
        value = int(os.getenv("BQS_MAX_RESPONSE_ROWS", str(_DEFAULT_MAX_RESPONSE_ROWS)))
    except ValueError:
        return _DEFAULT_MAX_RESPONSE_ROWS
    return value if value > 0 else _DEFAULT_MAX_RESPONSE_ROWS


def format_result(columns: list[str], rows: list[tuple], *, source: str,
                  metric: str, sql_audit: str, row_count: int,
                  as_of_date: str | None = None,
                  offset: int = 0, limit: int = 0) -> dict:
    cap = max_response_rows()
    returned = rows[:cap]
    records: list[dict[str, Any]] = [dict(zip(columns, r)) for r in returned]

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
