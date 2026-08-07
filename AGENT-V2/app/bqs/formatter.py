"""Result formatter — shapes DB rows into the agent-facing response.

Returns only business names (column aliases), never physical schema.
"""

from __future__ import annotations

from typing import Any


def format_result(columns: list[str], rows: list[tuple], *, source: str,
                  metric: str, sql_audit: str, row_count: int,
                  as_of_date: str | None = None) -> dict:
    records: list[dict[str, Any]] = [dict(zip(columns, r)) for r in rows]
    result = {
        "error": False,
        "source": source,
        "metric": metric,
        "columns": columns,
        "row_count": row_count,
        "rows": records,
        # SQL text is safe to surface for transparency; contains no secrets.
        "generated_sql": sql_audit,
    }
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
# NOTE: the response carries no `limit` echo and no `truncated` flag, and
# row_count == len(rows). So a result clipped by `limit` (or by the source's
# max_limit, which is what an omitted limit resolves to) is indistinguishable
# from a result that happened to have exactly that many rows. The agent has to
# infer it: if row_count equals the limit it asked for, more rows may exist.
