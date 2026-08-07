"""Starlette middleware — extracts the caller identity from inbound MCP HTTP
requests and stores it in a ContextVar for tool functions to read."""

from __future__ import annotations

import logging
import os
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

_current_soeid: ContextVar[str] = ContextVar("_current_soeid", default="")

SOEID_HEADER = "x-user-id"

# The agent runtime / API gateway may forward the caller's identity under a
# variety of header names depending on the channel (CitiPortal, COIN, direct
# MCP). We accept any of them, in priority order, so identity is resolved no
# matter which one is present. Extend via MCP_USER_ID_HEADERS (comma-separated).
_DEFAULT_ID_HEADERS = [
    "x-user-id",
    "x-citiportal-loginid",
    "x-citi-soeid",
    "x-soeid",
    "soeid",
    "x-authenticated-userid",
    "x-forwarded-user",
    "x-remote-user",
]
_EXTRA_HEADERS = [
    h.strip().lower()
    for h in os.getenv("MCP_USER_ID_HEADERS", "").split(",")
    if h.strip()
]
CANDIDATE_ID_HEADERS = _EXTRA_HEADERS + _DEFAULT_ID_HEADERS

# Some callers pass identity on the URL instead of in a header — the nl2sql
# server is reachable as `/mcp?user_id=<soeid>`. Headers are still preferred and
# are checked first; this is the fallback that keeps parity with that channel.
# Override the accepted names with MCP_USER_ID_QUERY_PARAMS (comma-separated);
# set it to a single space to disable query-param identity entirely.
_QUERY_PARAM_ENV = os.getenv("MCP_USER_ID_QUERY_PARAMS")
CANDIDATE_ID_QUERY_PARAMS = [
    q.strip()
    for q in (_QUERY_PARAM_ENV if _QUERY_PARAM_ENV is not None else "user_id,soeid").split(",")
    if q.strip()
]

# Optional fallback user identifier. When the inbound request carries none of
# the identity headers above, the server falls back to this value so downstream
# entitlement checks ("no user identifier was provided") do not hard-fail.
# Set MCP_FALLBACK_USER_ID to enable it (empty = disabled, original behaviour).
FALLBACK_USER_ID = os.getenv("MCP_FALLBACK_USER_ID", "").strip()


def _resolve_user_id(request: Request) -> tuple[str, str]:
    """Return (user_id, source). source is '' when the fallback was used."""
    for name in CANDIDATE_ID_HEADERS:
        val = request.headers.get(name, "")
        if val:
            return val.strip(), name
    for name in CANDIDATE_ID_QUERY_PARAMS:
        val = request.query_params.get(name, "")
        if val:
            return val.strip(), f"?{name}"
    return FALLBACK_USER_ID, ""


class SoeidHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        soeid, src = _resolve_user_id(request)
        token = _current_soeid.set(soeid)
        if request.url.path != "/health/ready":
            # Debug aid: when identity can't be resolved, dumping the inbound
            # header names reveals which header the agent runtime actually sends
            # so it can be added to MCP_USER_ID_HEADERS. Enable with
            # MCP_DEBUG_HEADERS=true (never logs header VALUES, only names).
            if os.getenv("MCP_DEBUG_HEADERS", "").strip().lower() in {
                "1",
                "true",
                "yes",
            }:
                logger.info(
                    "SoeidHeaderMiddleware DEBUG inbound header names: %s | query keys: %s",
                    sorted(request.headers.keys()),
                    sorted(request.query_params.keys()),
                )
            logger.info(
                "SoeidHeaderMiddleware: %s path=%s user_id=%s (via=%s, "
                "used_fallback=%s)",
                request.method,
                request.url.path,
                soeid or "<empty>",
                src or "<none>",
                bool(soeid) and not src,
            )
        try:
            response = await call_next(request)
            return response
        finally:
            _current_soeid.reset(token)


def get_soeid() -> str:
    """Return the SOEID resolved from the current request (header or query)."""
    return _current_soeid.get()
