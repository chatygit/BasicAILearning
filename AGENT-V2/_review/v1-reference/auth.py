from __future__ import annotations

import contextvars
from dataclasses import dataclass, field

from starlette.types import ASGIApp, Receive, Scope, Send

# Re-export the canonical ContextVar-backed accessors from the new
# middleware module so legacy ``from ..auth import get_soeid`` imports
# transparently read whatever ``SoeidHeaderMiddleware`` populated.
from .middleware.soeid_middleware import (  # noqa: F401  (re-export)
    _current_soeid as _soeid_var,
)
from .middleware.soeid_middleware import (
    get_soeid,
    set_soeid,
)


@dataclass
class AuthConfig:

    fallback_soeid: str = ""
    header_name: str = "x-citiportal-loginid"
    skip_auth_paths: frozenset[str] = field(
        default_factory=lambda: frozenset({"/health", "/ready", "/metrics"})
    )


class SoeidAuthMiddleware:

    def __init__(self, app: ASGIApp, config: AuthConfig | None = None) -> None:
        self.app = app
        self.config = config or AuthConfig()
        # Pre-encode the header name for fast byte-level comparison
        # against ``scope["headers"]``.
        self._header_bytes = self.config.header_name.encode("latin-1").lower()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in self.config.skip_auth_paths:
            await self.app(scope, receive, send)
            return

        soeid = self._extract_soeid(scope) or self.config.fallback_soeid
        token: contextvars.Token = set_soeid(soeid)
        try:
            await self.app(scope, receive, send)
        finally:
            _soeid_var.reset(token)

    def _extract_soeid(self, scope: Scope) -> str:
        headers = scope.get("headers") or []
        for raw_name, raw_value in headers:
            if raw_name.lower() == self._header_bytes:
                try:
                    return raw_value.decode("latin-1").strip()
                except (UnicodeDecodeError, AttributeError):
                    return ""
        return ""


__all__ = [
    "AuthConfig",
    "SoeidAuthMiddleware",
    "get_soeid",
    "set_soeid",
]
