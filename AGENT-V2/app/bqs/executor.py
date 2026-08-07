"""Oracle/Postgres executor — runs the built query on a read-only connection.

Credentials are fetched via CyberArk (on Linux/OpenShift) or from environment
variables for local development, mirroring the existing DB access pattern.
"""

from __future__ import annotations

import logging
import os

from config import settings
from .dialects.base import BaseDialect
from .models import BQSError
from .ontology import ConnectionSpec, Dialect, OntologySpec
from .sql_builder import BuiltQuery

logger = logging.getLogger(__name__)


def _resolve_cyberark_fid(conn: ConnectionSpec) -> str | None:
    """CyberArk nickname for the Oracle password — never stored in the ontology.

    Sourced from config/env only: BQS_ORACLE_CYBERARK_FID (env) or the
    ``bqs_oracle_cyberark_fid`` setting (.env). ``conn.cyberark_fid`` is honored
    only as a legacy fallback for any ontology that still carries it.
    """
    return (
        os.getenv("BQS_ORACLE_CYBERARK_FID")
        or settings.bqs_oracle_cyberark_fid
        or conn.cyberark_fid
    )


def _resolve_password(conn: ConnectionSpec) -> str | None:
    # 1) CyberArk nickname (Linux/OpenShift) — FID from config/env, not ontology.
    fid = _resolve_cyberark_fid(conn)
    if fid:
        try:
            from utils.cyberark_integration.cyberark_db_integration import (
                fetch_key_with_fid,
            )

            pw = fetch_key_with_fid(fid)
            if pw:
                return pw
        except Exception as e:  # noqa: BLE001
            logger.warning("CyberArk lookup failed, falling back: %s", e)

    # 2) BQS-specific password from .env (read via settings so it works under
    #    uvicorn where .env is loaded into settings but not os.environ).
    if settings.bqs_db_password:
        logger.info("BQS using DB password from .env (BQS_DB_PASSWORD).")
        return settings.bqs_db_password
    env_pw = os.getenv("BQS_DB_PASSWORD")
    if env_pw:
        return env_pw

    # 3) Reuse the central credential resolution used by the startup check.
    #    This covers the platform-injected POSTGRES_KEY (ECS O2C), the local
    #    .env DB_PASSWORD, and the legacy CyberArk subprocess fallback.
    try:
        from db import resolve_db_credentials

        creds = resolve_db_credentials()
        if creds.password:
            logger.info(
                "BQS using DB password from central resolver (source=%s).",
                creds.credential_source,
            )
            return creds.password
    except Exception as e:  # noqa: BLE001
        logger.warning("Central credential resolution failed: %s", e)

    # 4) Final env fallback (legacy): DB_PASSWORD shared with the Postgres path.
    return os.getenv("BQS_DB_PASSWORD") or os.getenv("DB_PASSWORD")


def _resolve_user(conn: ConnectionSpec) -> str | None:
    """Resolve the DB user from config/env — the ontology carries no user.

    Precedence: BQS_DB_USER (env) > bqs_db_user (.env via settings) >
    ORACLE_USER (env) > ontology connection.user (legacy fallback only).
    """
    return (
        os.getenv("BQS_DB_USER")
        or settings.bqs_db_user
        or os.getenv("ORACLE_USER")
        or conn.user
    )


def fetch_as_of_date(spec: OntologySpec, dialect: BaseDialect) -> str | None:
    """Return the source's latest as_of_date (ISO string) or None.

    Runs the governed ``as_of_date.query`` on the same read-only connection.
    Best-effort: any failure returns None so the main query response is never
    broken by an unavailable availability view.
    """
    if spec.as_of_date is None or spec.dialect == Dialect.TRINO:
        # Trino sources have no availability-view wiring here; skip.
        # CONSEQUENCE: every ECM/DCM object is Trino, so as_of_date can never be
        # populated for them — declaring `as_of_date` in those ontologies would
        # be inert until this path is wired. The agent therefore has no
        # "data as of" date to show.
        return None
    password = _resolve_password(spec.connection)
    if not password:
        return None
    conn_spec = spec.connection
    resolved_user = _resolve_user(conn_spec)
    if resolved_user and resolved_user != conn_spec.user:
        conn_spec = conn_spec.model_copy(update={"user": resolved_user})
    conn = None
    try:
        conn = dialect.connect(conn_spec, password)
        _apply_oracle_call_timeout(conn, spec)
        with conn.cursor() as cur:
            _apply_timeout(cur, spec)
            cur.execute(spec.as_of_date.query)
            row = cur.fetchone()
        conn.rollback()
        if not row or row[0] is None:
            return None
        value = row[0]
        # Normalize date/datetime to an ISO date string; leave strings as-is.
        return value.date().isoformat() if hasattr(value, "date") else str(value)
    except Exception as e:  # noqa: BLE001 - never break the main response
        logger.warning("as_of_date fetch failed for source %s: %s", spec.source, e)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def execute(spec: OntologySpec, built: BuiltQuery, dialect: BaseDialect) -> tuple[list[str], list[tuple]]:
    # Trino/Starburst is executed via the portable connector (no raw DBAPI
    # connection / password handling here).
    if spec.dialect == Dialect.TRINO:
        return _execute_trino(built, dialect)

    password = _resolve_password(spec.connection)
    if not password:
        raise BQSError(
            "No database password available for BQS. Set DB_PASSWORD (or "
            "POSTGRES_KEY) in your local .env, or configure the ontology "
            "connection.cyberark_fid / CYBERARK_DB_PASSWORD_FID on the cluster.",
            code="execution_error",
        )
    conn_spec = spec.connection
    resolved_user = _resolve_user(conn_spec)
    if resolved_user and resolved_user != conn_spec.user:
        conn_spec = conn_spec.model_copy(update={"user": resolved_user})
    conn = None
    try:
        conn = dialect.connect(conn_spec, password)
        _apply_oracle_call_timeout(conn, spec)
        with conn.cursor() as cur:
            _apply_timeout(cur, spec)
            cur.execute(built.sql, built.params)
            columns = [d[0] for d in cur.description]
            rows = cur.fetchall()
        # Read-only session: nothing to commit; rollback to release.
        conn.rollback()
        return columns, rows
    except BQSError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("Query execution failed for source %s: %s", spec.source, e)
        raise _classify_execution_error(e) from e
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass


def _apply_timeout(cur, spec: OntologySpec) -> None:
    try:
        if spec.dialect == Dialect.POSTGRES:
            cur.execute(
                f"SET statement_timeout = {int(spec.query_timeout_seconds) * 1000}"
            )
        # Oracle timeout is set on the connection (see _apply_oracle_call_timeout).
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to set statement timeout: %s", e)


def _apply_oracle_call_timeout(conn, spec: OntologySpec) -> None:
    """Bound each Oracle round-trip so a slow query stops instead of hanging.

    oracledb enforces the timeout per round-trip via ``connection.call_timeout``
    (milliseconds); on expiry it raises DPI-1067, mapped to a query_timeout
    BQSError so the agent is told to narrow and retry.
    """
    if spec.dialect != Dialect.ORACLE:
        return
    try:
        conn.call_timeout = int(spec.query_timeout_seconds) * 1000
    except Exception as e:  # noqa: BLE001
        logger.warning("Failed to set Oracle call_timeout: %s", e)


# NOTE: neither timeout helper covers TRINO. `query_timeout_seconds` in the
# ontology is therefore INERT for the ECM/DCM objects — whatever bound exists
# comes from the Starburst connector or the Trino cluster, not from us.


def _render_trino_sql(built: BuiltQuery, dialect: BaseDialect) -> str:
    """Substitute placeholder tokens with safe Trino literals.

    The builder always binds params; the Starburst connector takes a plain SQL
    string. We replace each unique '__P_<name>__' token with the dialect's
    injection-safe literal rendering of the bound value.
    """
    sql = built.sql
    # Replace longer names first to avoid partial-token collisions.
    for name in sorted(built.params, key=len, reverse=True):
        token = dialect.placeholder(0, name)
        literal = dialect.render_literal(name, built.params[name])
        sql = sql.replace(token, literal)
    return sql

# NOTE: this is the ONE place agent-supplied values stop being bound parameters
# and become SQL text. On the ECM/DCM (Trino) path every filter value goes
# through it. The safety of the whole read-only story rests on
# `dialect.render_literal` escaping correctly — that function is worth a
# dedicated test, since nothing downstream re-validates the rendered string
# (assert_read_only runs on built.sql, BEFORE substitution).


def _execute_trino(built: BuiltQuery, dialect: BaseDialect) -> tuple[list[str], list[tuple]]:
    # This repo ships its own Starburst/Trino client (app/utils/starburst.py),
    # which resolves local dev defaults (STARBURST_* + CA bundle) internally, so
    # no separate local-values loader is required here.
    try:
        from utils.starburst import execute_starburst_query
    except ImportError:  # package-import path (e.g. app.bqs.executor)
        from ..utils.starburst import execute_starburst_query

    sql = _render_trino_sql(built, dialect)
    logger.info("BQS(trino) executing: %s", sql)
    # The connector enforces read-only and appends a LIMIT if missing; our SQL
    # already carries LIMIT. Pass a high limit so we never truncate governed
    # results below the builder's clamp.
    try:
        result = execute_starburst_query(sql=sql, limit=100000)
    except Exception as e:  # noqa: BLE001
        # Log the ORIGINAL driver/connector error (type + message) before it is
        # mapped to a generic agent-facing message. Without this, connectivity
        # failures (DNS, TLS/cert mismatch, 401 auth, timeout) are indistinguishable
        # in the logs — you only see "failed after 1 attempts".
        logger.error(
            "BQS(trino) execution failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise _classify_execution_error(e) from e
    columns = result.get("columns", [])
    rows = [tuple(r) for r in result.get("rows", [])]
    return columns, rows


def _classify_execution_error(e: Exception) -> BQSError:
    """Turn a raw driver/connector error into an agent-actionable BQSError.

    Distinguishes three cases so the agent knows whether retrying helps:
      - timeout          -> narrow the query and retry (request-fixable)
      - operational      -> infra/connection/permission issue; do NOT keep
                            retrying the same request; report it (not fixable
                            by rewriting the BQS body)
      - execution_error  -> generic fallback
    """
    msg = str(e)
    low = msg.lower()
    if (
        "EXCEEDED_TIME_LIMIT" in msg
        or "maximum time limit" in low
        or "dpi-1067" in low
        or "call timeout" in low
    ):
        return BQSError(
            "The query took too long and was stopped. Please narrow it — add "
            "more filters, reduce dimensions (avoid high-cardinality ones), or "
            "apply the source's recommended scoping filters — and try again.",
            code="query_timeout",
        )
    # Infra/connectivity/permission problems the agent cannot fix by changing
    # the request. Tell it to stop retrying the same body and surface the issue.
    operational_markers = (
        "missing required environment variable",
        "starburst_host",
        "connection refused",
        "could not connect",
        "timed out",
        "authentication",
        "unauthorized",
        "access denied",
        "permission denied",
        "certificate",
        "ssl",
    )
    if any(m in low for m in operational_markers):
        return BQSError(
            "The data service is temporarily unavailable (connection/"
            "configuration issue). This is not a problem with your request — "
            "do not retry the same query repeatedly. Tell the user the data "
            "backend is unavailable and to try again later.",
            code="service_unavailable",
        )
    return BQSError(f"Query execution failed: {e}", code="execution_error")
