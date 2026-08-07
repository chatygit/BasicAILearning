from __future__ import annotations

import logging

if __package__ in (None, ""):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.config import settings  # type: ignore[no-redef]
    from app.middleware.soeid_middleware import (  # type: ignore[no-redef]
        SoeidHeaderMiddleware,
    )
    from app.server import mcp  # type: ignore[no-redef]
else:
    from .config import settings
    from .middleware.soeid_middleware import SoeidHeaderMiddleware
    from .server import mcp

from starlette.middleware import Middleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# One line between the logger and the app line was cut off in the screenshot.
app = mcp.http_app(middleware=[Middleware(SoeidHeaderMiddleware)])


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting MCP NL2SQL Server")
    uvicorn.run(app, host="0.0.0.0", port=settings.service_port)
