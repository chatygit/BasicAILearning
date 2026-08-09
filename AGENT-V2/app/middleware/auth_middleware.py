import os
import logging

from fastmcp.server.middleware import Middleware, MiddlewareContext
from starlette.requests import Request

from utils.auth import extract_token, validate_token
from utils.exceptions import (
    CitiMCPAuthenticationError,
    CitiMCPAuthTokenMissingError,
    CitiMCPAuthTokenValidationError,
)

logger = logging.getLogger(__name__)

_TRUTHY = ("true", "1", "yes")


def _coin_disabled() -> bool:
    """Whether COIN token validation is skipped.

    Read per call so it can be flipped without a restart. Normalised, because
    the raw comparison this replaces was case- and whitespace-sensitive:
    `DISABLE_COIN=True` did not match `"true"`, so a capital letter silently
    turned authentication back ON and every tool call started failing.
    """
    return os.getenv("DISABLE_COIN", "true").strip().lower() in _TRUTHY


def _run_mode() -> str:
    return os.getenv("RUN_MODE", "local").strip().lower()


# Announced ONCE at import, at WARNING, because the default is the permissive
# one: an unset DISABLE_COIN means no token is validated at all. That is the
# right default for local work and the wrong one for a deployed environment,
# and until now nothing in the logs distinguished "auth is off because we chose
# that" from "auth is off because nobody set the variable".
if _coin_disabled() and _run_mode() != "local":
    logger.warning(
        "AUTH: COIN token validation is DISABLED (DISABLE_COIN=%s, RUN_MODE=%s). "
        "Tool calls are NOT authenticated. Set DISABLE_COIN=false to enforce.",
        os.getenv("DISABLE_COIN", "<unset — defaults to true>"),
        _run_mode(),
    )
else:
    logger.info(
        "AUTH: COIN token validation %s (DISABLE_COIN=%s, RUN_MODE=%s)",
        "disabled" if _coin_disabled() else "ENFORCED",
        os.getenv("DISABLE_COIN", "<unset>"),
        _run_mode(),
    )


class AuthMiddleware(Middleware):
    async def on_call_tool(self, context: MiddlewareContext, call_next):
        return await self._handle_auth(context, call_next)

    async def on_read_resource(self, context: MiddlewareContext, call_next):
        return await self._handle_auth(context, call_next)

    async def on_get_prompt(self, context: MiddlewareContext, call_next):
        return await self._handle_auth(context, call_next)

    async def _handle_auth(self, context: MiddlewareContext, call_next):
        """
        Middleware to handle authentication for each tool call.

        Args:
            context (MiddlewareContext): The middleware context containing the request and response.
            call_next (Callable): The next middleware or endpoint to call.

        Returns:
            Response: The HTTP response after processing the request.

        Raises:
            CitiMCPAuthenticationError: If an unexpected error occurs during authentication.
        """
        # Check if this is a test environment and skip auth in tests
        if _coin_disabled():
            # DEBUG, not INFO: this fired on every single tool call and the
            # startup line above already says whether auth is on.
            logger.debug("Skipping authentication (DISABLE_COIN)")
            return await call_next(context)

        try:
            logger.debug("Token validation starts")
            request: Request = context.fastmcp_context.request_context.request

            # Extract token from Authorization header
            token = extract_token(request.headers.get("Authorization", ""))
            if not token:
                raise CitiMCPAuthTokenMissingError()

            # Validate the token
            await validate_token(token, os.getenv("COIN_ROLE", ""))

        except (CitiMCPAuthTokenMissingError, CitiMCPAuthTokenValidationError) as e:
            logger.error(f"Error: {e.error.message}, type(e): {type(e).__name__}")
            raise e

        except Exception as e:
            # Log and raise a generic authentication error for unexpected exceptions
            logger.error(f"Unexpected error during token validation: {e}")
            raise CitiMCPAuthenticationError(message=f"Authentication error: {e}")

        # Proceed with the request
        return await call_next(context)
