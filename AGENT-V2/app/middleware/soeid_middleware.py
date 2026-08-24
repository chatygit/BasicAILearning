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

# There is deliberately NO server-side fallback identity. A fallback attributes
# one person's queries AND one person's entitlements to every caller that
# arrives without identity, and it hides a broken identity chain behind answers
# that look correct — that is how a local default SOEID once scoped real query
# results. An unidentified request must be refused (mcpserver returns
# missing_soeid), never silently impersonated. If the old env var is still set
# in a deployment, say so loudly and ignore it.
if os.getenv("MCP_FALLBACK_USER_ID", "").strip():
    logger.error(
        "MCP_FALLBACK_USER_ID is set but IGNORED — server-side identity "
        "fallbacks are forbidden. Identity must arrive on the request "
        "(x-user-id header or ?user_id=). Remove the env var."
    )


def _resolve_user_id(request: Request) -> tuple[str, str]:
    """Return (user_id, source). Both empty when the request carries no identity."""
    for name in CANDIDATE_ID_HEADERS:
        val = request.headers.get(name, "")
        if val:
            return val.strip(), name
    for name in CANDIDATE_ID_QUERY_PARAMS:
        val = request.query_params.get(name, "")
        if val:
            return val.strip(), f"?{name}"
    return "", ""


# Probe endpoints are hit every few seconds by the platform and never carry
# identity — logging them drowns real traffic. Identity is still resolved and
# set for these requests; only the log line is suppressed.
QUIET_PATH_PREFIXES = ("/health", "/actuator/health")


class SoeidHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        soeid, src = _resolve_user_id(request)
        token = _current_soeid.set(soeid)
        if not request.url.path.startswith(QUIET_PATH_PREFIXES):
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
                "SoeidHeaderMiddleware: %s path=%s user_id=%s (via=%s)",
                request.method,
                request.url.path,
                soeid or "<empty>",
                src or "<none>",
            )
        try:
            response = await call_next(request)
            return response
        finally:
            _current_soeid.reset(token)


def get_soeid() -> str:
    """Return the SOEID resolved from the current request (header or query)."""
    return _current_soeid.get()
