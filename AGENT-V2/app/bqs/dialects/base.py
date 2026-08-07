"""Base dialect interface.

A dialect knows how to quote identifiers, render placeholders, apply row
limits, and open a read-only connection/session. The SQL builder never
concatenates agent-supplied values — only validated identifiers (from the
ontology) and bound parameters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseDialect(ABC):
    name: str

    @abstractmethod
    def quote_ident(self, ident: str) -> str:
        """Quote a possibly schema-qualified identifier safely."""

    @abstractmethod
    def placeholder(self, index: int, name: str) -> str:
        """Return a bind placeholder for the given 0-based index/name."""

    @abstractmethod
    def limit_clause(self, limit: int) -> str:
        """Return a row-limit clause appended after ORDER BY."""

    @abstractmethod
    def connect(self, conn_spec: Any, password: str | None):
        """Open a READ-ONLY connection for this dialect."""

    @abstractmethod
    def regexp_predicate(self, col_sql: str, pattern_placeholder: str) -> str:
        """Return a case-insensitive regex-match predicate for this dialect.

        `col_sql` is an already-quoted column expression; `pattern_placeholder`
        is a bind placeholder holding the (server-composed) regex pattern. The
        pattern is always parameter-bound — never concatenated into the SQL.
        """

    @abstractmethod
    def date_trunc(self, grain: str, col_sql: str) -> str:
        """Return an expression truncating `col_sql` to `grain`.

        `grain` is one of day/week/month/quarter/year (already validated).
        """

    def numeric_cast(self, col_sql: str) -> str:
        """Cast a (possibly VARCHAR) column expression to a numeric type.

        Some governed views store numeric measures as strings. Dialects that
        do not implicitly coerce (e.g. Trino) override this to emit an explicit
        cast so aggregations like SUM/AVG work. Default is a no-op.
        """
        return col_sql

    def list_count(self, col_sql: str, delimiter: str = " | ") -> str:
        """Return an expression counting elements in a delimited-list column.

        Governed pipe-delimited columns (e.g. the syndicate member list) encode
        several values in one string. This counts them (0 for NULL/empty) so a
        metric like ``syndicate_size`` can threshold "deals with N+ members".
        Dialects override with their native split/count; no generic default.
        """
        raise NotImplementedError(
            f"{self.name} dialect does not support list_count"
        )

    def render_literal(self, name: str, value: Any) -> str:
        """Render a bound value as a safe inline SQL literal.

        Only needed by dialects (e.g. Trino) executed via a string-only
        connector. Parameter-binding dialects never call this.
        """
        raise NotImplementedError(
            f"{self.name} dialect does not support literal rendering"
        )

    def _quote_qualified(self, ident: str, q: str) -> str:
        parts = ident.split(".")
        for p in parts:
            if not p or q in p or not _is_safe_ident(p):
                raise ValueError(f"Unsafe identifier: {ident!r}")
        return ".".join(f"{q}{p}{q}" for p in parts)


def _is_safe_ident(part: str) -> bool:
    """Physical identifiers come from governed YAML, but validate anyway."""
    return part.replace("_", "").replace("$", "").isalnum()
