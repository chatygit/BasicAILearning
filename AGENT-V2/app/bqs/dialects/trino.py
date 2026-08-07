"""Trino / Starburst dialect.

Executes through the portable `starburst_connector.execute_starburst_query`,
which accepts a plain read-only SQL string (no bound parameters). To keep the
deterministic builder unchanged (it always binds parameters), this dialect
emits named placeholders and additionally knows how to render each bound value
as a SAFE inline SQL literal. The executor substitutes the placeholders with
those literals just before calling the connector. Agent-supplied values are
still never trusted as SQL — they are escaped/quoted here.
"""

from __future__ import annotations

import datetime as _dt
import re as _re
from typing import Any

from .base import BaseDialect

# Date-like string values the agent commonly passes for date/timestamp filters.
# Rendered as typed DATE/TIMESTAMP literals so comparisons against timestamp(3)
# columns don't fail with "Cannot apply operator: timestamp <= varchar".
_DATE_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIMESTAMP_RE = _re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?$")


class TrinoDialect(BaseDialect):
    name = "trino"

    def quote_ident(self, ident: str) -> str:
        return self._quote_qualified(ident, '"')

    def placeholder(self, index: int, name: str) -> str:
        # A unique, easily-substituted token. Not a real bind — the executor
        # replaces it with a rendered literal (see render_literal).
        return f"__P_{name}__"

    def limit_clause(self, limit: int) -> str:
        return f"LIMIT {int(limit)}"

    def regexp_predicate(self, col_sql: str, pattern_placeholder: str) -> str:
        # Trino: regexp_like(value, pattern). Case-insensitivity is baked into
        # the composed pattern via a leading '(?i)' (added by render for these).
        # The COALESCE to a space is what makes NOT(...) well-defined on NULLs:
        # a row with no B&D flag correctly satisfies a negated B&D filter.
        return f"regexp_like(COALESCE({col_sql}, ' '), {pattern_placeholder})"

    def date_trunc(self, grain: str, col_sql: str) -> str:
        # grain validated (day/week/month/quarter/year) — safe to inline.
        return f"date_trunc('{grain}', {col_sql})"

    def numeric_cast(self, col_sql: str) -> str:
        # Governed numeric measures are stored as VARCHAR in the view; Trino
        # does not implicitly coerce strings for SUM/AVG. TRY_CAST returns NULL
        # for non-numeric text instead of failing the whole query.
        return f"TRY_CAST({col_sql} AS DOUBLE)"

    def list_count(self, col_sql: str, delimiter: str = " | ") -> str:
        d = delimiter.replace("'", "''")
        return (
            f"(CASE WHEN {col_sql} IS NULL OR {col_sql} = '' THEN 0 "
            f"ELSE CARDINALITY(SPLIT({col_sql}, '{d}')) END)"
        )

    # -- literal rendering (Trino-specific, injection-safe) ------------------
    def render_literal(self, name: str, value: Any) -> str:
        """Render a bound value as a safe Trino SQL literal."""
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (int, float)):
            return repr(value)
        if isinstance(value, _dt.datetime):
            return f"TIMESTAMP '{value.isoformat(sep=' ')}'"
        if isinstance(value, _dt.date):
            return f"DATE '{value.isoformat()}'"
        # Everything else -> single-quoted string with quote escaping.
        text = str(value).replace("'", "''")
        # Regex patterns for computed filters are case-insensitive via (?i).
        if name.startswith("cf"):
            text = "(?i)" + text
            return f"'{text}'"
        # Date/timestamp-like strings from date filters must be typed literals so
        # they compare cleanly against DATE/timestamp(3) columns. Only applied to
        # value filters (f*), never to computed-filter regex patterns above.
        if name.startswith("f"):
            raw = str(value).strip()
            if _TIMESTAMP_RE.match(raw):
                return f"TIMESTAMP '{raw.replace('T', ' ')}'"
            if _DATE_RE.match(raw):
                return f"DATE '{raw}'"
        return f"'{text}'"

    def connect(self, conn_spec: Any, password: str | None):
        # Not used — Starburst executor path calls the portable connector.
        raise NotImplementedError(
            "TrinoDialect uses the starburst_connector executor, not connect()."
        )


# NOTE (security): `render_literal` is the only place an agent-supplied value
# becomes SQL text rather than a bound parameter, and it is sound for Trino.
# Trino string literals process NO escape sequences — a backslash is a literal
# backslash — so doubling the single quote ("'" -> "''") is the complete escape,
# and the surrounding quotes are added here rather than coming from the value.
# Identifiers never take this path; they go through _quote_qualified, which
# validates against _is_safe_ident. Worth a unit test pinning the quote-doubling
# behaviour, since assert_read_only runs on the PRE-substitution SQL and nothing
# re-validates the rendered string.
#
# NOTE (correctness): TRY_CAST silently yields NULL for a value that will not
# parse as DOUBLE, and SUM/AVG skip NULLs. So a size/allocation column holding
# any non-numeric text produces a total that is quietly short — no error, no
# warning, and nothing the agent can detect from the response. If the governed
# measures are ever suspected of carrying junk, that is a view-side data-quality
# check, not something this layer can surface.
