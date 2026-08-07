"""SQL validator — read-only guardrail.

Final defense-in-depth check on the deterministically built SQL before it is
executed. Even though the builder only emits SELECTs, we assert it here so any
future change cannot silently introduce a write.
"""

from __future__ import annotations

import re

from .models import BQSError

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|"
    r"CALL|EXEC|EXECUTE|COMMIT|ROLLBACK|SAVEPOINT|INTO|COPY)\b",
    re.IGNORECASE,
)


def assert_read_only(sql: str) -> None:
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise BQSError("Multiple statements are not allowed.", code="unsafe_sql")
    if not stripped.upper().startswith("SELECT"):
        raise BQSError("Only SELECT statements are permitted.", code="unsafe_sql")
    if _FORBIDDEN.search(stripped):
        raise BQSError("SQL contains a forbidden write keyword.", code="unsafe_sql")
    if "--" in stripped or "/*" in stripped:
        raise BQSError("SQL comments are not allowed.", code="unsafe_sql")

# NOTE: _FORBIDDEN matches whole words anywhere in the statement, including
# quoted identifiers and output aliases. Underscores are word characters, so
# CREATE_DATE / merge_count are safe — but a business name or physical column
# containing a bare forbidden word (e.g. an alias "Paid Into Escrow") would be
# rejected as unsafe SQL. Keep ontology business names snake_case.
#
# NOTE: this is called explicitly by domain_query_service.run() before execute().
# The suggestion/disambiguation DISTINCT probes in suggestions.py call execute()
# directly and therefore do NOT pass through here — those statements are
# server-authored with bound parameters, so the risk is low, but the module
# docstring in suggestions.py claims it "reuses the existing executor/read-only
# validator", which is only half true. Worth reconciling.
