"""
NL2SQL MCP Server — FastMCP-based tool server.

Exposes text-to-SQL tools via the MCP protocol over streamable HTTP.
Migrated from mcp-server-core to provide a dedicated NL2SQL microservice.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastmcp import FastMCP
from starlette.responses import JSONResponse

from .auth import get_soeid
from .tools.text2sql import (
    tool_data_context as _data_context,
)
from .tools.text2sql import (
    tool_entity_search as _entity_search,
)
from .tools.text2sql import (
    tool_fuzzy_resolve as _fuzzy_resolve,
)
from .tools.text2sql import (
    tool_query_context as _query_context,
)
from .tools.text2sql import (
    tool_query_executor as _query_executor,
)
from .tools.text2sql import (
    tool_validate_sql as _validate_sql,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_VERSION = "1.1.0"

# ---------------------------------------------------------------------------
# Create the FastMCP server instance
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="mcp-nl2sql-server",
    instructions=(
        "NL2SQL tool server (api_version=1.1.0). "
        "Provides text-to-SQL tools for entity search, "
        "query generation context, SQL validation, query execution, "
        "fuzzy resolution, and data analysis context. "
        "Supported domains: credit_facility, wallet, revenue_returns, capital_markets. "
        "Tools: text2sql_capabilities, text2sql_entity_search, text2sql_query_context, text2sql_query_generator, "
        "text2sql_validate_sql, text2sql_query_executor, text2sql_data_context, "
        "text2sql_fuzzy_resolve. "
        "Do not call ADK agent names as MCP tools; use transfer_to_agent() for agent hops. "
        "Use text2sql_capabilities to retrieve the full contract/parameter spec at runtime."
    ),
)


# ---------------------------------------------------------------------------
# Text-to-SQL MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool(output_schema=None)
def text2sql_capabilities() -> dict:
    """Return MCP text2sql contract details for runtime compatibility checks."""
    return {
        "api_version": API_VERSION,
        "not_available_tools": [
            "text2sql_query_generator_agent",
            "text2sql_data_presenter",
            "text2sql_data_presenter_agent",
        ],
        "agent_guidance": (
            "SQL generation and narrative presentation are performed by the calling "
            "ADK agent, not by MCP tools. Use transfer_to_agent() for agent hops; "
            "only call MCP tools that appear under capabilities.tools at runtime."
        ),
        "contract_notes": {
            "entity_search_response": {
                "preferred_fields": [
                    "status",
                    "entity_type",
                    "resolved_identifier_type",
                    "resolved_identifier_value",
                    "resolution",
                    "entity_snapshot",
                    "selection_token",
                    "next_action",
                ],
                "legacy_compatibility": {
                    "status_aliases": {
                        "legacy_status": "disambiguation",
                    },
                },
                "deprecation_notice": (
                    "ADK should not rely on fixed entity_snapshot keys. "
                    "Prefer resolved_identifier_type/resolved_identifier_value and "
                    "domain-driven entity_snapshot fields."
                ),
            }
        },
        "tools": {
            "text2sql_entity_search": {
                "supported_params": [
                    "domain",
                    "entity_name",
                    "gfcid",
                    "cagid",
                    "entity_type",
                    "deal_id",
                ]
            },
            "text2sql_query_context": {
                "supported_params": [
                    "domain",
                    "user_query",
                    "gfcid",
                    "gpnum",
                    "client_level",
                    "filter_criteria",
                    "platform",
                ]
            },
            "text2sql_query_generator": {
                "description": "Alias for text2sql_query_context. Returns schema context and domain rules so the calling agent can generate SQL.",
                "supported_params": [
                    "domain",
                    "user_query",
                    "gfcid",
                    "gpnum",
                    "client_level",
                    "filter_criteria",
                    "platform",
                ]
            },
            "text2sql_query_executor": {
                "supported_params": [
                    "domain",
                    "sql_query",
                    "result_headers",
                    "columns",
                    "user_question",
                    "aggregation_columns",
                    "conversation_id",
                ]
            },
            "text2sql_validate_sql": {
                "supported_params": ["domain", "sql_query"]
            },
            "text2sql_fuzzy_resolve": {
                "supported_params": ["domain", "column_name", "fuzzy_input", "top_k"]
            },
            "text2sql_data_context": {
                "supported_params": [
                    "domain",
                    "execution_key",
                    "user_question",
                    "columns",
                    "aggregation_columns",
                    "as_of_date",
                    "client_identifier",
                    "client_level",
                    "gfcid_name",
                    "platform",
                ]
            },
        },
        "domains": [
            "credit_facility",
            "wallet",
            "revenue_returns",
            "capital_markets",
        ],
    }


@mcp.tool(output_schema=None)
def text2sql_entity_search(
    domain: str,
    entity_name: str = "",
    gfcid: str = "",
    cagid: str = "",
    entity_type: str = "",
    deal_id: str = "",
) -> dict:
    """Search for an entity (company, deal, client) by name or identifier.

    Supports SQL-based and API-based search depending on the domain.
    Includes disambiguation when multiple results found and entitlement checking.

    Args:
        domain: Domain identifier (credit_facility, revenue_returns, wallet, capital_markets).
        entity_name: Entity/company name to search for.
        gfcid: Direct GFCID (issuer) identifier lookup. Do NOT pass a DEAL_ID here.
        cagid: Direct CAGID lookup (credit_facility only).
        entity_type: Optional intent hint (investor_name, issuer_name, deal_name).
        deal_id: Direct DEAL_ID lookup (capital_markets). Use this — not gfcid — when the
            user gives an explicit deal id. Takes precedence over entity_name.
    """
    user_id = get_soeid()
    return _entity_search(
        domain,
        entity_name,
        gfcid,
        cagid,
        entity_type,
        deal_id=deal_id,
        user_id=user_id,
    )


@mcp.tool(output_schema=None)
def text2sql_query_executor(
    domain: str,
    sql_query: str,
    result_headers: str = "",
    columns: str = "",
    user_question: str = "",
    aggregation_columns: str = "",
    conversation_id: str = "",
) -> dict:
    """Execute a validated SQL query and store results for analysis.

    Runs the query via database adapter, applies domain-specific
    post-query calculations, stores results keyed by execution_key.

    Args:
        domain: Domain identifier (credit_facility, revenue_returns, wallet, capital_markets).
        sql_query: Validated SQL query to execute.
        result_headers: Comma-separated expected column headers.
        columns: JSON-encoded column metadata.
        user_question: Original user question for context.
        aggregation_columns: Comma-separated aggregation column names.
        conversation_id: Conversation ID for tracking.
    """
    user_id = get_soeid()
    return _query_executor(
        domain,
        sql_query,
        result_headers,
        columns,
        user_question,
        aggregation_columns,
        conversation_id,
        user_id=user_id,
    )


@mcp.tool(output_schema=None)
def text2sql_fuzzy_resolve(
    domain: str,
    column_name: str,
    fuzzy_input: str,
    top_k: int = 5,
) -> dict:
    """Resolve a fuzzy/approximate value against a domain column.

    Only active for domains with fuzzy config (currently credit_facility).
    Calls ingestion API for vector similarity candidates and returns ranked matches.

    Args:
        domain: Domain identifier (credit_facility, revenue_returns, wallet, capital_markets).
        column_name: Column to resolve against (e.g. COMPANY_NAME).
        fuzzy_input: Approximate value to resolve.
        top_k: Maximum candidates to return.
    """
    # Resolve SOEID from the request-scoped ContextVar populated by
    # SoeidHeaderMiddleware so the downstream call inherits the same
    # identity used by the other text2sql_* tools.
    user_id = get_soeid()
    return _fuzzy_resolve(
        domain, column_name, fuzzy_input, top_k, user_id=user_id
    )


# ---------------------------------------------------------------------------
# Text-to-SQL context tools (provide data for ADK sub-agents to drive LLM)
# ---------------------------------------------------------------------------


@mcp.tool(output_schema=None)
def text2sql_query_context(
    domain: str,
    user_query: str,
    gfcid: str = "",
    gpnum: str = "",
    client_level: str = "",
    filter_criteria: str = "",
    platform: str = "desktop",
) -> dict:
    """Return schema context, domain configuration, and entitlement status for
    SQL generation — without making LLM calls or external prompt API calls.

    Performs entitlement checks, fetches load-IDs and as-of-date, loads the
    domain schema.
    """
    user_id = get_soeid()
    return _query_context(
        domain=domain,
        user_query=user_query,
        gfcid=gfcid,
        gpnum=gpnum,
        client_level=client_level,
        filter_criteria=filter_criteria,
        platform=platform,
        user_id=user_id,
    )


@mcp.tool(output_schema=None)
def text2sql_query_generator(
    domain: str,
    user_query: str,
    gfcid: str = "",
    gpnum: str = "",
    client_level: str = "",
    filter_criteria: str = "",
    platform: str = "desktop",
) -> dict:
    """Alias for text2sql_query_context."""
    user_id = get_soeid()
    return _query_context(
        domain=domain,
        user_query=user_query,
        gfcid=gfcid,
        gpnum=gpnum,
        client_level=client_level,
        filter_criteria=filter_criteria,
        platform=platform,
        user_id=user_id,
    )


@mcp.tool(output_schema=None)
def text2sql_validate_sql(
    domain: str,
    sql_query: str,
) -> dict:
    """Validate a SQL query against the domain's validation rules."""
    return _validate_sql(domain, sql_query)


@mcp.tool(output_schema=None)
def text2sql_data_context(
    domain: str,
    execution_key: str,
    user_question: str = "",
    columns: str = "",
    aggregation_columns: str = "",
    as_of_date: str = "",
    client_identifier: str = "",
    client_level: str = "",
    gfcid_name: str = "",
    platform: str = "desktop",
) -> dict:
    """Return stored query results plus analysis context for presentation."""
    user_id = get_soeid()
    return _data_context(
        domain,
        execution_key,
        user_question,
        columns,
        aggregation_columns,
        as_of_date,
        client_identifier,
        client_level,
        gfcid_name,
        platform,
        user_id=user_id,
    )


# ---------------------------------------------------------------------------
# Health check endpoints
# ---------------------------------------------------------------------------


@mcp.custom_route("/capabilities", methods=["GET"])
async def capabilities_endpoint(request):
    """Return MCP text2sql contract details as a plain HTTP response.

    Mirrors the ``text2sql_capabilities`` MCP tool so that clients that
    cannot invoke MCP tools directly (e.g. ADK orchestrators) can still
    retrieve the contract via a simple GET request.
    """
    return JSONResponse(status_code=200, content=text2sql_capabilities())


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Basic health check endpoint for liveness probe."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "timestamp": datetime.now(UTC).isoformat(),
            "service": "mcp-nl2sql-server",
        },
    )


@mcp.custom_route("/health/ready", methods=["GET"])
async def readiness_check(request):
    """Readiness check endpoint - checks if service is ready to accept traffic."""
    try:
        if mcp is None:
            raise Exception("MCP server not initialized")

        try:
            tools = await mcp.list_tools()
            if hasattr(tools, "tools") and tools.tools is not None:
                tools_count = len(tools.tools)
            elif tools is not None and hasattr(tools, "__len__"):
                tools_count = len(tools)
            else:
                tools_count = 0
            logger.info(f"Tools registered: {tools_count}")
        except Exception as e:
            logger.error(f"Failed to count tools: {e}")
            tools_count = 0

        return JSONResponse(
            status_code=200,
            content={
                "status": "ready",
                "timestamp": datetime.now(UTC).isoformat(),
                "service": "mcp-nl2sql-server",
                "tools_registered": tools_count,
            },
        )
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready",
                "timestamp": datetime.now(UTC).isoformat(),
                "service": "mcp-nl2sql-server",
                "error": str(e),
            },
        )


# End of file. This module builds NO HTTP app: no http_app(), no uvicorn.run(),
# no __main__ block. It only defines `mcp`, the tools, and the custom routes.
# The ASGI app, the transport flags and the middleware registration all live in
# utils/main.py.
