import uvicorn
import os
import json
import threading
import time
import sys
from datetime import UTC, datetime
from pathlib import Path
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.responses import JSONResponse

# Keep app-local absolute imports (utils.*, middleware.*) working in both
# script mode and package-import test mode.
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

try:
    # Package import path (e.g., tests importing app.mcpserver).
    from .middleware.auth_middleware import AuthMiddleware
    from .middleware.metrics_middleware import PrometheusMetricsMiddleware
    from .middleware.tracing_middleware import TracingMiddleware
    from .utils.logger import logger_setup
    from .utils.tracing import setup_tracing
except ImportError:
    # Script import path (e.g., running python app/mcpserver.py).
    from middleware.auth_middleware import AuthMiddleware
    from middleware.metrics_middleware import PrometheusMetricsMiddleware
    from middleware.tracing_middleware import TracingMiddleware
    from utils.logger import logger_setup
    from utils.tracing import setup_tracing

logger_setup()

import logging

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="Capital Market MCP Server",
    # NOTE: this is still the template default. It is server-level text
    # some clients surface — worth replacing with a real description.
    instructions="Starter Helix server for MCP. Shows examples of MCP components: Tool, Resource and Prompt.",
)

mcp.add_middleware(PrometheusMetricsMiddleware(mcp))
mcp.add_middleware(AuthMiddleware())

setup_tracing(mcp)
mcp.add_middleware(TracingMiddleware())


# Tools are functions that the client can call to perform actions or access external systems.
@mcp.tool()
def tool_echo_user_context() -> dict:
    """Diagnostic tool: echoes back the SOEID resolved from request context."""
    user_id = _resolve_soeid() or ""
    logger.info("tool_echo_user_context: resolved user_id=%s", user_id)
    return {
        "received_user_id": user_id,
        "user_id_type": type(user_id).__name__,
        "user_id_length": len(user_id) if user_id else 0,
        "is_empty": not bool(user_id),
        "service": "mcp-server-core",
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# ECM/DCM (Capital Markets) BQS governed-SQL tools - V2 ontology text-to-SQL
# ---------------------------------------------------------------------------
# Two-tool contract backed by app/bqs/* + app/services/domain_query_service.py:
#   * discover_business_terms - lists the governed business metrics, dimensions
#     and filters for the capital_markets source (ALWAYS call first).
#   * run_bqs_query - the agent submits a structured Business Query
#     Specification (business names only); the server deterministically builds
#     read-only SQL and executes it via Starburst/Trino. The agent never writes
#     SQL.
try:
    from services.domain_query_service import get_service as _get_bqs_service

    _BQS_AVAILABLE = True
    logger.info(
        "Capital Markets BQS tools loaded - registering discover_business_terms + run_bqs_query."
    )
except Exception as _bqs_import_exc:  # noqa: BLE001 - optional module
    try:
        from app.services.domain_query_service import get_service as _get_bqs_service

        _BQS_AVAILABLE = True
        logger.info(
            "Capital Markets BQS tools loaded - registering discover_business_terms + run_bqs_query."
        )
    except Exception as _bqs_import_exc2:  # noqa: BLE001
        _BQS_AVAILABLE = False
        _bqs_import_error = _bqs_import_exc2
        logger.warning(
            "Capital Markets BQS tools unavailable; skipping registration. Reason: %s",
            _bqs_import_exc2,
        )


# ---------------------------------------------------------------------------
# ECM/DCM entitlement gate (Citi ECMO API) - enforced at the run_bqs_query
# boundary so the generic BQS engine stays domain-agnostic. Blocks callers with
# no ECM/DCM access and constrains every query to the caller's entitled
# product(s) via an injected `product` filter.
# ---------------------------------------------------------------------------
#
# Identity and entitlement are imported SEPARATELY and tracked by separate
# flags. They used to share one try block, which coupled two unrelated
# failures: if entitlement_service failed to import, `get_soeid` went with it,
# `_resolve_soeid()` returned None, and every query died with `missing_soeid` —
# sending whoever debugged it after a header that was there all along. The two
# also fail in OPPOSITE directions (identity closed, entitlement open), so
# merging them produced the worst combination: refuse everything, for the
# wrong stated reason.
try:
    from middleware.soeid_middleware import get_soeid as _get_soeid

    _SOEID_AVAILABLE = True
except Exception:  # noqa: BLE001
    try:
        from app.middleware.soeid_middleware import get_soeid as _get_soeid

        _SOEID_AVAILABLE = True
    except Exception as _soeid_import_exc:  # noqa: BLE001
        _SOEID_AVAILABLE = False
        logger.error(
            "IDENTITY: soeid middleware unavailable (%s) — no request can be "
            "attributed to a caller, so every data request will be refused",
            _soeid_import_exc,
        )

try:
    from services.entitlement_service import perform_initial_entitlement_check

    _ENTITLEMENT_AVAILABLE = True
except Exception:  # noqa: BLE001
    try:
        from app.services.entitlement_service import perform_initial_entitlement_check

        _ENTITLEMENT_AVAILABLE = True
    except Exception as _ent_import_exc:  # noqa: BLE001
        _ENTITLEMENT_AVAILABLE = False
        logger.warning("ECM/DCM entitlement gate unavailable: %s", _ent_import_exc)


_ALLOWED_PRODUCTS = ("ECM", "DCM")


def _ecm_entitlement_enabled() -> bool:
    """Whether the ECM/DCM entitlement gate should run.

    ONE switch: ECM_DCM_ENTITLEMENT_FEATURE_FLAG (default "true").

    There is deliberately no local bypass. RUN_MODE defaults to "local", so the
    old `if _is_local_mode(): return False` meant the gate was off unless a
    deployment explicitly set RUN_MODE to something else — an environment
    variable nobody had to remember, silently granting ECM+DCM. Worse, it made
    local behave differently from every other environment, so an entitlement
    bug could not be reproduced on a laptop.

    A developer without ECMO API access sets ECM_DCM_ENTITLEMENT_FEATURE_FLAG
    =false in their own .env — a decision they make explicitly, and one the
    startup log announces, rather than one the default quietly makes for them.
    """
    return os.getenv("ECM_DCM_ENTITLEMENT_FEATURE_FLAG", "true").strip().lower() == "true"


def _resolve_soeid() -> str | None:
    """Resolve the caller SOEID from the REQUEST only — no env, no default.

    Identity belongs to the caller. A server-side fallback attributes one
    person's queries AND one person's entitlements to everybody who arrives
    without a header, and it hides a broken identity chain behind an answer that
    looks correct — which is how a local default (`sr37832`) ended up scoping
    real query results. The middleware accepts the SOEID as `x-user-id` (plus
    documented aliases) or as `?user_id=` on the MCP URL; if neither is present
    the request has no identity and must be refused, in every environment.
    """
    if not _SOEID_AVAILABLE:
        return None
    try:
        return (_get_soeid() or "").strip() or None
    except Exception:  # noqa: BLE001
        return None


def _require_caller_soeid() -> dict | None:
    """Refuse a data request that carries no caller identity.

    Returns None when a SOEID is present, otherwise an agent-facing error. This
    runs BEFORE the entitlement gate and independently of
    ECM_DCM_ENTITLEMENT_FEATURE_FLAG: turning entitlement enforcement off is a
    decision about which products a known user may see, never a licence to run
    as nobody.
    """
    if _resolve_soeid():
        return None
    if not _SOEID_AVAILABLE:
        # Not the caller's fault and not fixable by adding a header — say so,
        # or the next person spends the afternoon on the wrong problem.
        logger.error(
            "IDENTITY: refusing data request — the soeid middleware failed to "
            "import at startup, so no request carries an identity. This is a "
            "server deployment fault, not a missing header."
        )
        return {
            "error": True,
            "code": "identity_unavailable",
            "message": (
                "This server cannot determine who is asking, because its identity "
                "component failed to load at startup. No data can be returned "
                "until it is fixed. This is a server fault — do not retry and do "
                "not reword the question; report it to the user plainly."
            ),
        }
    logger.warning(
        "ENTITLEMENT: refusing data request — no caller SOEID on the request "
        "(expected an 'x-user-id' header or ?user_id= on the MCP URL)"
    )
    return {
        "error": True,
        "code": "missing_soeid",
        "message": (
            "No user identity was supplied with this request, so your ECM/DCM "
            "entitlements cannot be checked and no data can be returned. The "
            "calling application must send the user's SOEID as an 'x-user-id' "
            "header (or ?user_id= on the MCP server URL). This is a client "
            "configuration problem — rewording the question will not fix it, so "
            "do not retry; report it to the user plainly."
        ),
    }



# ---------------------------------------------------------------------------
# Discovery-hop diagnostics.
#
# A catalog costs ~0.45s of server time but a whole LLM turn (5-10s) to fetch
# and read, so three discovery calls to answer one question is most of a minute.
# Both config layers already say "once you hold a source's catalog, never fetch
# it again" and the model does it anyway, so this measures it instead of
# assuming. Two different faults look the same from the outside and need
# different fixes:
#   same source twice   -> the once-per-conversation rule is being ignored
#   two sources at once -> the question named two grains and the routing table
#                          did not resolve it to one object
# There is no conversation id on a stateless request, so this keys on the SOEID
# over a short window — close enough to attribute a burst to one turn.
# ---------------------------------------------------------------------------
_DISCOVERY_WINDOW_SECONDS = 120.0
_DISCOVERY_LOG: dict[str, list[tuple[float, str]]] = {}
_DISCOVERY_LOG_LOCK = threading.Lock()


def _log_repeat_discovery(soeid: str | None, source: str | None) -> None:
    """Warn when one caller fetches catalogs more than once in a short window."""
    try:
        key = (soeid or "<anon>").lower()
        name = source or "<ALL FOUR>"
        now = time.monotonic()
        with _DISCOVERY_LOG_LOCK:
            recent = [
                (t, s) for t, s in _DISCOVERY_LOG.get(key, [])
                if now - t < _DISCOVERY_WINDOW_SECONDS
            ]
            recent.append((now, name))
            _DISCOVERY_LOG[key] = recent
            if len(_DISCOVERY_LOG) > 500:  # bounded; purely diagnostic
                for stale in [
                    k for k, v in _DISCOVERY_LOG.items()
                    if not v or now - v[-1][0] > _DISCOVERY_WINDOW_SECONDS
                ]:
                    _DISCOVERY_LOG.pop(stale, None)
        if len(recent) < 2:
            return
        names = [s for _t, s in recent]
        repeated = len(names) != len(set(names))
        logger.warning(
            "DISCOVERY HOPS: soeid=%s call #%d in %.0fs — sources=%s (%s). Each "
            "call costs a full LLM turn; the catalog does not change between "
            "them.",
            soeid or "<anon>",
            len(recent),
            _DISCOVERY_WINDOW_SECONDS,
            names,
            "SAME source re-fetched — the once-per-conversation rule is being "
            "ignored" if repeated else
            "DIFFERENT sources — the question spanned grains and the routing "
            "table did not resolve it to one object",
        )
    except Exception as exc:  # noqa: BLE001 - diagnostics must never break a tool
        logger.debug("discovery-hop diagnostics skipped: %s", exc)


def _entitlement_preflight() -> tuple[dict | None, list[str]]:
    """Identity + entitlement, without touching a BQS request.

    Returns (denial_or_None, entitled_products). Split out of
    `_entitlement_gate` so the FIRST tool the agent calls can fail as early as
    the last one: the checks are identical, only the product-filter injection is
    specific to a query.
    """
    denial = _require_caller_soeid()
    if denial is not None:
        return denial, []
    if not _ENTITLEMENT_AVAILABLE:
        if _ecm_entitlement_enabled():
            # FAIL-CLOSED (decided 2026-08-11): enforcement is ON but its
            # component failed to import at startup, so no caller's products can
            # be established. Running unscoped here would hand every caller
            # ECM+DCM data that entitlement was never checked for — the exact
            # outcome the gate exists to prevent. Mirror identity_unavailable:
            # a server fault the agent must report, not retry around.
            logger.error(
                "ENTITLEMENT: refusing data request — enforcement is enabled "
                "but the entitlement component failed to import at startup. "
                "This is a server deployment fault."
            )
            return {
                "error": True,
                "code": "entitlement_unavailable",
                "message": (
                    "This server cannot check entitlements because its "
                    "entitlement component failed to load at startup. No data "
                    "can be returned until it is fixed. This is a server fault "
                    "— do not retry and do not reword the question; report it "
                    "to the user plainly."
                ),
            }, []
        # Flag explicitly OFF: the developer opted out of enforcement (their
        # .env, announced at startup) — run unscoped as they asked.
        logger.warning(
            "ENTITLEMENT: gate unavailable (import failed) and enforcement "
            "flag is OFF — query runs unscoped by explicit configuration"
        )
        return None, []
    soeid = _resolve_soeid()
    gate = perform_initial_entitlement_check(
        soeid=soeid,
        entitlement_enabled=_ecm_entitlement_enabled(),
    )
    if not gate.get("ok"):
        logger.warning(
            "ENTITLEMENT: DENIED soeid=%s reason=%s",
            soeid or "<empty>",
            gate.get("reason", "entitlement_denied"),
        )
        return {
            "error": True,
            "code": gate.get("reason", "entitlement_denied"),
            "message": gate.get(
                "user_message", "Unable to verify your ECM/DCM entitlements."
            ),
        }, []
    entitled = [p for p in _ALLOWED_PRODUCTS if p in set(gate.get("entitled_products") or [])]
    if not entitled and _ecm_entitlement_enabled():
        # FAIL-CLOSED (decided 2026-08-11): the service said ok but named no
        # recognisable product. Unreachable today (the service denies first) —
        # kept defensive, because "ok with nothing" must never widen to
        # "everything" while enforcement is on.
        logger.error(
            "ENTITLEMENT: DENIED soeid=%s — gate passed with NO entitled "
            "products (raw=%s)",
            soeid or "<empty>",
            gate.get("entitled_products"),
        )
        return {
            "error": True,
            "code": "no_entitled_products",
            "message": (
                "Your entitlements could be checked but cover neither ECM nor "
                "DCM, so no Capital Markets data can be returned. Report this "
                "to the user plainly — rewording the question will not help."
            ),
        }, []
    if not entitled:
        logger.warning(
            "ENTITLEMENT: soeid=%s has no entitled products and enforcement "
            "flag is OFF — query runs unscoped by explicit configuration",
            soeid or "<empty>",
        )
    return None, entitled


def _attach_entitlement_scope(
    result: dict, entitled: list[str], note: bool = True
) -> dict:
    """Put the caller's entitled products INTO the discovery response.

    The skill has always said "scope to what the user is entitled to and never
    request the unentitled product" — but nothing told the agent what that set
    WAS, so it could only find out by paying a full LLM turn for a query the
    gate was guaranteed to deny. Observed in QA 2026-08-12: an ECM-only caller
    asked for top Healthcare deals, got a correct ECM answer, then the agent
    volunteered "the top DCM deals", ran the query, and closed the chat with an
    entitlement apology. With the scope in discovery the agent queries only
    entitled products from the start and never offers the others.

    Attached only when the gate is active (non-empty `entitled`); when
    enforcement is off the key is absent and the skill treats both products as
    queryable.

    ``note=False`` attaches the bare `entitled_products` key without the
    instruction text — used on EVERY query response, because a scope delivered
    once at session start does not survive a long conversation: observed
    2026-08-18, a 50+-event session drifted to DCM on an ECM-only login and
    failed, with the discovery payload (and its scope) buried dozens of turns
    back or evicted by context trimming. Ambient on every response, the scope
    is always within the most recent tool result.
    """
    if entitled and isinstance(result, dict) and not result.get("error"):
        result["entitled_products"] = list(entitled)
        if note:
            result["entitlement_note"] = (
                "These are the ONLY products this user may query — treat the "
                "list as complete, for the WHOLE session (entitlements never "
                "change mid-conversation). Scope every request to it from the "
                "start; never run a query for, offer, or suggest a product "
                "outside it. If the user explicitly names an unentitled "
                "product, say access does not cover it in one line — WITHOUT "
                "running the query — and answer with the entitled portion."
            )
    return result


_RELATIVE_TIME_RE = None


def _check_relative_date_mismatch(question: str | None, filters: list) -> dict | None:
    """Refuse a query whose ASK says now-relative time but whose WINDOW is stale.

    The date anchor arrives in the DISCOVERY RESPONSE — and QA 2026-08-18
    showed the model firing run_bqs_query in the same turn as discovery, before
    any response existed, so "this year" was anchored on the model's training
    cutoff: 2024, answered confidently as fact. A prompt rule already forbade
    that and lost; this guard is the deterministic backstop. The server knows
    today, the `question` field carries the ask, and the filters carry the
    window — when the ask contains a now-relative phrase and EVERY date bound
    lies before Jan 1 of the current year, the window cannot be what the user
    meant. Explicit historical asks ("deals in 2024") carry no relative phrase
    and are untouched; a correctly built "last 3 years" has an upper bound
    near tomorrow and passes.
    """
    global _RELATIVE_TIME_RE
    if not question:
        return None
    import re as _re
    from datetime import date as _date
    if _RELATIVE_TIME_RE is None:
        _RELATIVE_TIME_RE = _re.compile(
            r"(?i)\b(this (year|month|quarter|week)|ytd|year.to.date|"
            r"(last|past|previous|trailing) \d+ (day|week|month|year)s?|"
            r"(last|past) (few|couple)|recent|latest|newest|today|yesterday|"
            r"so far)\b"
        )
    if not _RELATIVE_TIME_RE.search(question):
        return None
    bounds = []
    for f in filters or []:
        if str(f.get("op", "")).strip().lower() not in (
            "gt", "gte", "lt", "lte", "between", "eq"
        ):
            continue
        vals = f.get("value")
        vals = vals if isinstance(vals, (list, tuple)) else [vals]
        for v in vals:
            m = _re.match(r"^\s*(\d{4})-(\d{2})-(\d{2})", str(v or ""))
            if m:
                bounds.append(_date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if not bounds:
        return None
    today = _date.today()
    if max(bounds) >= _date(today.year, 1, 1):
        return None
    return {
        "error": True,
        "code": "stale_relative_window",
        "message": (
            f"The question says a NOW-relative period but every date bound in "
            f"the request is before {today.year}-01-01 — the window was built "
            f"from a guessed 'today'. TODAY IS {today.isoformat()}; you do not "
            f"know the date without the discovery response's date_anchor. "
            f"Rebuild the window from today (e.g. 'this year' = >= "
            f"{today.year}-01-01 AND < {today.year + 1}-01-01) and resend."
        ),
    }


def _entitlement_gate(request: dict) -> dict | None:
    """Enforce ECM/DCM entitlement on a BQS request (mutates it in place).

    Returns None when the request is allowed (and product-scoped to the caller's
    entitled products); returns an agent-facing error dict when access is denied.
    """
    denial, entitled = _entitlement_preflight()
    if denial is not None:
        return denial
    if not entitled:
        return None
    # Read again for the log lines below. Cheap — it is a ContextVar get, not
    # the entitlement call — and it keeps the preflight's return a 2-tuple.
    soeid = _resolve_soeid()

    # Products the user explicitly asked for (via a product filter).
    #
    # Only eq/in count as "asking for a product". Anything else is rejected
    # HERE, before the strip-and-inject below, because the gate rewrites
    # product filters before the planner's operator allow-list ever sees them:
    # left alone, `product ne 'ECM'` would collect requested=["ECM"] and be
    # rewritten to `product eq 'ECM'` — the exact opposite of the ask. An
    # unrecognised value ("EMC", "equity") must also stop the request: stripping
    # it and injecting the full entitlement answers a product-scoped question
    # with ALL the caller's data and no sign anything went wrong.
    requested: list[str] = []
    for f in request.get("filters") or []:
        if str(f.get("field", "")).strip().lower() != "product":
            continue
        op = str(f.get("op", "eq")).strip().lower()
        if op not in ("eq", "in"):
            return {
                "error": True,
                "code": "operator_not_allowed",
                "message": (
                    f"Filter 'product' supports only eq or in — got '{op}'. "
                    "There are exactly two products, ECM and DCM: to exclude "
                    "one, filter eq to the other."
                ),
            }
        val = f.get("value")
        vals = val if isinstance(val, (list, tuple)) else [val]
        for raw in vals:
            v = str(raw or "").strip().upper()
            if v not in _ALLOWED_PRODUCTS:
                return {
                    "error": True,
                    "code": "invalid_product_value",
                    "message": (
                        f"'{str(raw or '').strip()}' is not a product. The only "
                        "product values are ECM and DCM. Words like equity, "
                        "convertible or bond are equity_type/product_type/"
                        "product_class values, not products — re-check the "
                        "catalog and re-send."
                    ),
                }
            if v not in requested:
                requested.append(v)

    if requested and not any(p in entitled for p in requested):
        blocked = ", ".join(requested)
        logger.warning(
            "ENTITLEMENT: DENIED soeid=%s requested=%s entitled=%s "
            "reason=product_not_entitled",
            soeid or "<empty>",
            requested,
            entitled,
        )
        return {
            "error": True,
            "code": "product_not_entitled",
            "message": (
                f"You are not entitled to {blocked} data. Your access covers: "
                f"{', '.join(entitled)}. Ask about an entitled product instead."
            ),
        }

        # Bound the query to the INTERSECTION of what the caller asked
    # for and what they are entitled to — not to the full entitlement.
    #
    # The previous code dropped every product filter and injected `entitled`
    # wholesale. For a caller entitled to BOTH products that silently rewrote
    # "ECM deals in 2025" into "ECM and DCM deals in 2025", so any size /
    # allocation / demand metric summed ECM SHARE COUNTS with DCM NOTIONAL
    # MONEY. The agent could neither detect nor prevent it, and the ontology's
    # `requires_filters: [product]` guard still passed because a product filter
    # WAS present — just not the one the agent asked for.
    #
    # `requested` has already been validated against `entitled` above, so the
    # intersection is always non-empty when `requested` is non-empty; an empty
    # `requested` still falls back to the caller's full entitlement.
    scope = [p for p in requested if p in entitled] or entitled

    filters = [
        f for f in (request.get("filters") or [])
        if str(f.get("field", "")).strip().lower() != "product"
    ]
    if len(scope) == 1:
        filters.append({"field": "product", "op": "eq", "value": scope[0]})
    else:
        filters.append({"field": "product", "op": "in", "value": scope})
    request["filters"] = filters
    # The success path used to be silent, so nothing in the logs said which
    # products a caller was entitled to or what scope the gate injected — you
    # could only infer it from the `product` predicate in the generated SQL.
    # `agent_scoped=False` means the agent set NO product filter and the gate
    # chose for it; with two entitled products that also silently satisfies
    # `requires_filters: [product]`, so those lines are the ones to grep when a
    # size/allocation total looks like it mixed ECM shares with DCM money.
    logger.info(
        "ENTITLEMENT: soeid=%s entitled=%s requested=%s scope=%s agent_scoped=%s",
        soeid or "<empty>",
        entitled,
        requested or [],
        scope,
        bool(requested),
    )
    return None


if _BQS_AVAILABLE:

    @mcp.tool()
    def discover_business_terms(source: str | None = None) -> dict:
        """Discover the governed business metrics, dimensions, and filters.

        ALWAYS call this first. It returns, per source: 'how_to_use' (step-by-step
        instructions for building a run_bqs_query body), 'usage_notes', worked
        'examples' (question -> ready-to-run request), and the catalogs of valid
        'metrics', 'dimensions', 'filters' (with allowed operators) and
        'computed_filters'. The domain-specific guidance (which source and metrics
        to use, mandatory scoping filters, gotchas) lives in each source's
        'how_to_use'/'usage_notes'/'examples' — follow them. Use ONLY names returned
        here for the source you query — never invent names or pass physical column
        names.

        Args:
            source: Optional business data source name. If omitted, returns a
                compact ROUTING INDEX (per source: grain, purpose, metric
                names) plus the date anchor — NOT the full catalogs. Pick one
                source from the index and call again with it.
                PREFER passing one name: the four ECM/DCM objects are
                'capital_markets_deal', 'capital_markets_tranche', 'capital_markets_order' and
                'capital_markets_entity'; only the single-source call returns
                the full catalog (operators, values, examples) you need to
                build a request.
        """
        # Entitlement is checked HERE, on the first tool the agent calls, not
        # only on run_bqs_query. An unentitled or unidentified caller used to
        # get all the way through transfer -> load_skill -> discover -> build a
        # request -> run_bqs_query before hearing "no" — four LLM turns spent to
        # produce a refusal we could have given on the first one. It also warms
        # the entitlement cache, so the check inside run_bqs_query is a cache
        # hit and costs nothing.
        denial, entitled = _entitlement_preflight()
        if denial is not None:
            logger.info(
                "discover_business_terms: refused early (code=%s)", denial.get("code")
            )
            return denial
        _log_repeat_discovery(_resolve_soeid(), source)
        logger.info("discover_business_terms: source=%s entitled=%s", source, entitled)
        # The agent learns its product scope HERE, with the catalog — so it can
        # scope multi-product asks to entitled products from the first request
        # instead of discovering the boundary through a denied query.
        return _attach_entitlement_scope(_get_bqs_service().discover(source), entitled)

    @mcp.tool()
    def run_bqs_query(
        metric: str,
        source: str | None = None,
        dimensions: list[str] | None = None,
        filters: list[dict] | None = None,
        computed_filters: list[dict] | None = None,
        derived_filters: list[str] | None = None,
        having: list[dict] | None = None,
        time_grain: str | None = None,
        time_dimension: str | None = None,
        order: list[dict] | None = None,
        partition_by: list[str] | None = None,
        per_partition_limit: int | None = None,
        limit: int | None = None,
        offset: int | None = None,
        question: str | None = None,
    ) -> dict:
        """Run a governed Business Query Specification (BQS) against the database.

        You never write SQL. Fill out this structured request using ONLY business
        names from discover_business_terms for the source you are querying. Call
        discover_business_terms FIRST and follow that source's 'how_to_use',
        'usage_notes' and 'examples' — they carry all domain-specific guidance
        (which source/metrics to use, mandatory scoping filters, gotchas). The
        server matches names exactly, deterministically builds read-only SQL, and
        returns rows. Unknown names or a bad request shape fail with a clear
        'message' telling you exactly what to fix — read it and retry.

        If a query returns 0 rows because a filter VALUE didn't match the data
        (wrong case/spelling), the response includes a 'suggestions' block with
        'did_you_mean' real values — retry using one of those exact values.

        If a NON-empty result came from an entity-name filter that matched multiple
        distinct entities, the response includes a 'disambiguation' block listing
        the matched entities; re-run with one exact name to isolate a single entity.

        General patterns (always defer to the source's own examples):
          - Pick ONE metric (the number to compute) from the chosen source.
          - "top N": order=[{"field": <metric>, "direction": "desc"}], limit=N,
            and add a dimension to see the ranked entities.
          - "top X in EACH Y" (per-group winners): partition_by=[Y] with
            per_partition_limit=N — see the partition_by arg below.
          - A full calendar year: two date filters, op "gte" on Jan 1 and op "lt"
            on Jan 1 of the next year.
          - Apply any mandatory scoping filters the source's usage_notes call out.

        Args:
            metric: Business metric name to aggregate (from discovery).
            source: Business data source name from discovery. May be omitted only
                when a single source is enabled; pass the exact source name when
                discovery returns more than one.
            dimensions: Business dimension names to group by.
            filters: List of {"field", "op", "value"} filter objects.
            computed_filters: List of {"name", "token"} governed computed filters.
                Pass a business token like "citi"; omit token for token-less
                filters. (Only available on sources that declare computed_filters.)
                Add "negate": true to match rows that do NOT satisfy it - e.g.
                "non-B&D" = bill_and_deliver with negate, "Citi non-B&D" =
                syndicate_member "citi" plus bill_and_deliver with negate.
            derived_filters: List of governed derived-predicate NAMES (strings)
                from discovery, e.g. ["settlement_currency_mismatch"]. Token-less -
                the server owns the SQL (used for column-vs-column conditions).
            having: List of {"metric", "op", "value"} post-aggregation thresholds
                (SQL HAVING), e.g. {"metric": "deal_count", "op": "gt", "value": 5}
                for investors in >5 deals, or currency_count gt 1 for multi-currency
                deals. Comparison operators only; use a count/sum metric.
            time_grain: Optional time bucket (day/week/month/quarter/year).
            time_dimension: Date dimension to bucket for time_grain (defaults to the
                source's default date dimension).
            order: List of {"field", "direction"} sort objects.
            partition_by: TOP-N-PER-GROUP ("biggest deal in EACH sector", "top
                3 investors per deal"): the dimension(s) defining the groups —
                a subset of `dimensions`. Each group keeps its top
                `per_partition_limit` rows, ranked by `order` (default: the
                metric descending), and every returned row carries its
                rank_in_group. Keep identifying dimensions (names, ids) OUT of
                partition_by. Cannot be combined with offset.
            per_partition_limit: Rows kept per group (default 1). Only valid
                with partition_by.
            limit: Max rows to return. Omitting it gives a small default page
                (50), NOT everything — ask for more rows with `offset`, never by
                raising the limit. The response is capped independently of this,
                so a large limit costs warehouse time and returns no more rows
                than the cap allows.
            offset: Rows to skip — the paging cursor. Omit for the first page.
                When a response comes back with "truncated": true it carries a
                "next_offset"; to show the next page, repeat the SAME request
                with offset set to that value and EVERY other field identical.
                Changing a filter mid-page means paging through a different
                result set. If the user wants a TOTAL rather than more rows, use
                a count metric — that is one row instead of thousands.
            question: The user's ask, verbatim (or a close paraphrase), that
                this query answers. ALWAYS pass it. It is logged server-side so
                a query in the logs can be traced back to the question that
                produced it; it never affects the query.
        """
        request = {
            "source": source,
            "metric": metric,
            "dimensions": dimensions or [],
            "filters": filters or [],
            "computed_filters": computed_filters or [],
            "derived_filters": derived_filters or [],
            "having": having or [],
            "time_grain": time_grain,
            "time_dimension": time_dimension,
            "order": order or [],
            "partition_by": partition_by or [],
            "per_partition_limit": per_partition_limit,
            "limit": limit,
            "offset": offset,
        }
        # The ASK, first, so every line of this query's log group reads in
        # context. Debugging QA meant matching "which query was which question"
        # by timestamp alone — the prompt lives in the ADK layer and never
        # reaches this server except through this field.
        logger.info(
            "run_bqs_query: ask=%r",
            (question or "<not provided>")[:300],
        )
        # Deterministic date-anchor backstop: an ask that says "this year"
        # with a window entirely in a past year was anchored on a guessed
        # today — refuse with the real date before wasting the round-trip.
        denial = _check_relative_date_mismatch(question, request.get("filters"))
        if denial is not None:
            logger.warning(
                "run_bqs_query: stale relative window refused (ask=%r)",
                (question or "")[:120],
            )
            return denial
        # Identity first: no caller SOEID, no data. Checked before the
        # entitlement gate so it applies even when the gate is flagged off.
        denial = _require_caller_soeid()
        if denial is not None:
            return denial
        # Entitlement gate: block unentitled callers and scope the query to the
        # caller's entitled ECM/DCM product(s) before any SQL is built/run.
        denial = _entitlement_gate(request)
        if denial is not None:
            logger.info("run_bqs_query: entitlement denied (code=%s)", denial.get("code"))
            return denial
        logger.info("run_bqs_query: source=%s metric=%s", source, metric)
        # The caller's product scope AND today's date ride on EVERY response —
        # facts stated once at session start get buried or trimmed in long
        # conversations. The gate just ran, so the preflight is a cache hit.
        _, _entitled_now = _entitlement_preflight()
        result = _attach_entitlement_scope(
            _get_bqs_service().run(request), _entitled_now, note=False
        )
        if isinstance(result, dict) and not result.get("error"):
            from datetime import date as _date
            result["current_date"] = _date.today().isoformat()
        return result


# ---------------------------------------------------------------------------
# Activism / Ownership: top institutional holders REST tool + analysis.
# Registered from its own module (app/tools/top_holders_tool.py) so the tool's
# agent-facing contract and the REST/analysis logic stay out of this file.
# ---------------------------------------------------------------------------
try:
    try:
        from tools.top_holders_tool import register_top_holders_tools
    except ImportError:
        from app.tools.top_holders_tool import register_top_holders_tools
    register_top_holders_tools(mcp, resolve_soeid=_resolve_soeid)
    logger.info("Activism top-holders tool registered (get_top_holders).")
except Exception as _th_exc:  # noqa: BLE001 - optional tool must not break startup
    logger.warning("Top-holders tool unavailable; skipping registration. Reason: %s", _th_exc)


# Resource templates are parameterized resources that allow the client to request specific data.
@mcp.resource("users://{user_id}/profile")
def get_user_profile(user_id: int) -> str:
    """
    This Resource Component retrieves a user's profile by ID.
    """
    # The {user_id} in the URI is extracted and passed to this function
    return json.dumps({"id": user_id, "name": f"User {user_id}", "status": "active"})


# Prompts are reusable message templates for guiding the LLM.
@mcp.prompt
def analyze_data(data_points: list[float]) -> str:
    """
    This Prompt component creates a prompt asking for analysis of numerical data.
    """
    formatted_data = ", ".join(str(point) for point in data_points)
    return f"Please analyze these data points: {formatted_data}"


class _HealthAccessLogFilter(logging.Filter):
    """Drop uvicorn access-log lines for health probes ("GET /health HTTP/1.1"
    200 OK every few seconds) so real requests stay visible in the log."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/health" not in record.getMessage()


# Attached at import time so it applies however the server is launched
# (python mcpserver.py OR uvicorn app.mcpserver:app). uvicorn's own logging
# setup replaces handlers, not logger filters, so this survives uvicorn.run().
logging.getLogger("uvicorn.access").addFilter(_HealthAccessLogFilter())


async def health_check(request):
    """
    Health check endpoint.

    Returns:
        JSONResponse: A simple JSON response indicating server health.
    """
    return JSONResponse({"status": "ok"})


async def actuator_health_check(request):
    """Legacy health endpoint used by older tests/clients."""
    return JSONResponse("All ok")


def _log_entitlement_config() -> None:
    """State the effective entitlement posture ONCE, at startup.

    Turning the gate on takes three settings that live in two places, and the
    partial states fail in opposite directions:

        ECM_DCM_ENTITLEMENT_FEATURE_FLAG    chart default "false" => gate OFF
        ECM_DCM_PRODUCT_ENTITLEMENT_URL     chart default ""  } REQUIRED when
        ECM_DCM_ENTITLEMENT_POLICY_ID       chart default ""  } the flag is on

    Flip the flag alone and `get_entitled_products` raises on the empty URL, so
    EVERY query is refused with `entitlement_misconfigured` — a total outage
    from a one-word values-file edit. Leave the flag off and every caller is
    granted ECM+DCM. Neither state announced itself anywhere before this line.

    RUN_MODE is NOT consulted: the gate behaves identically in every
    environment, so a local run reproduces what QA does.
    """
    try:
        flag = os.getenv("ECM_DCM_ENTITLEMENT_FEATURE_FLAG", "true").strip().lower()
        url = os.getenv("ECM_DCM_PRODUCT_ENTITLEMENT_URL", "").strip()
        policy = os.getenv("ECM_DCM_ENTITLEMENT_POLICY_ID", "").strip()

        if flag != "true":
            logger.warning(
                "ENTITLEMENT CONFIG: gate OFF "
                "(ECM_DCM_ENTITLEMENT_FEATURE_FLAG=%s). Every caller is granted "
                "ECM+DCM without a check.",
                flag,
            )
            return
        missing = [
            name
            for name, val in (
                ("ECM_DCM_PRODUCT_ENTITLEMENT_URL", url),
                ("ECM_DCM_ENTITLEMENT_POLICY_ID", policy),
            )
            if not val
        ]
        if missing:
            logger.error(
                "ENTITLEMENT CONFIG: gate is ENABLED but %s %s empty — EVERY query "
                "will be refused with `entitlement_misconfigured`. Set %s, or set "
                "ECM_DCM_ENTITLEMENT_FEATURE_FLAG=false.",
                " and ".join(missing),
                "is" if len(missing) == 1 else "are",
                "it" if len(missing) == 1 else "them",
            )
            return
        logger.info(
            "ENTITLEMENT CONFIG: gate ENFORCED (url set, policy set, cache ttl=%ss).",
            os.getenv("ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS", "300"),
        )
    except Exception as exc:  # noqa: BLE001 - logging must never break startup
        logger.debug("Entitlement config summary skipped: %s", exc)


def _log_startup_summary() -> None:
    """Log which tools are registered and note the optional stdio server.

    Best-effort: never raise from logging. FastMCP exposes tools via the async
    ``list_tools()`` API, but at import time we may not be in an event loop, so
    we fall back to the internal registry when available.
    """
    try:
        tool_names: list[str] = []
        # FastMCP exposes tools via async list_tools(). At import/startup time we
        # are not inside a running loop, so it is safe to drive it with asyncio.run.
        try:
            import asyncio

            tools = asyncio.run(mcp.list_tools())
            tool_names = sorted(getattr(t, "name", str(t)) for t in tools)
        except RuntimeError:
            # Already inside an event loop (e.g. imported by ASGI) - skip enumeration.
            tool_names = []
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not enumerate tools via list_tools(): %s", exc)

        if tool_names:
            logger.info("Registered MCP tools (%d): %s", len(tool_names), ", ".join(tool_names))
        else:
            logger.info("MCP tools registered (names enumerated at request time).")

        if _BQS_AVAILABLE:
            logger.info(
                "Capital Markets BQS tools are ACTIVE on this HTTP server "
                "(discover_business_terms, run_bqs_query)."
            )
        else:
            logger.warning("Capital Markets BQS tools are NOT active on this HTTP server.")

        _log_entitlement_config()
    except Exception as exc:  # noqa: BLE001 - logging must never break startup
        logger.debug("Startup tool summary logging skipped: %s", exc)


def create_http_app():
    """Create and configure the HTTP app once for import and runtime use."""
    # SESSION MODE. Streamable HTTP uses POST for JSON-RPC and GET to open an
    # SSE stream. The two modes trade different failures:
    #
    #   stateless=True   Every POST is self-contained, so ANY replica can serve
    #                    ANY request and a restart is invisible. GET /mcp is not
    #                    supported and returns a bare 405, so a client that
    #                    opens its session over SSE gets nothing.
    #   stateless=False  GET/SSE works (v1 builds its app this way), but session
    #                    state lives in POD MEMORY keyed by Mcp-Session-Id. With
    #                    more than one replica, or after a restart, a POST whose
    #                    session the pod has never seen gets 404 Not Found.
    #
    # Measured in QA 2026-08-09: stateful produced a storm of
    # `POST /mcp -> 404`. The trigger was a REDEPLOY, not a second replica. The
    # platform opens its MCP connection ONCE at agent bootstrap and holds it, so
    # a new chat is NOT a new MCP session: after the pod was replaced, the
    # client kept posting a session id no server had ever seen, and did not
    # re-initialize. In stateful mode every deploy therefore breaks the agent
    # until someone restarts the agent runtime — on top of the multi-replica
    # problem. Stateless has no session to lose, so a redeploy is invisible.
    # The ADK client POSTs and never opens a GET stream, so it loses nothing.
    # Set MCP_STATELESS_HTTP=false only if a client genuinely needs SSE, and
    # only alongside session affinity or a single replica.
    stateless = os.getenv("MCP_STATELESS_HTTP", "true").strip().lower() in {
        "1", "true", "yes",
    }
    logger.info(
        "MCP HTTP app: stateless_http=%s (%s)",
        stateless,
        "any replica can serve any request; GET /mcp returns 405"
        if stateless
        else "GET/SSE supported; REQUIRES session affinity or a single replica",
    )
    app = mcp.http_app(stateless_http=stateless)
    app.add_route("/health", health_check, methods=["GET"])
    app.add_route("/actuator/health", actuator_health_check, methods=["GET"])
    # Extract the caller SOEID (x-user-id + fallbacks) from inbound requests into
    # a ContextVar so BQS tools can read it via get_soeid() during a request.
    try:
        try:
            from .middleware.soeid_middleware import SoeidHeaderMiddleware
        except ImportError:
            from middleware.soeid_middleware import SoeidHeaderMiddleware
        app.add_middleware(SoeidHeaderMiddleware)
    except Exception as exc:  # noqa: BLE001 - never block app creation
        logger.warning("SoeidHeaderMiddleware not attached: %s", exc)
    _log_startup_summary()
    return app


app = create_http_app()


if __name__ == "__main__":
    # This runs the server, defaulting to STDIO transport. Use it only, if MCP server is run on the same machine as the client.
    # mcp.run()

    # Otherwise use HTTP transport and specify a port.:
    # Use run_async() in async contexts
    run_mode = os.getenv("RUN_MODE", "local").strip().lower()
    if run_mode == "local":
        os.environ.setdefault("LOCALHOST_MODE", "true")

    # When deployed behind OpenShift HAProxy (edge TLS termination), uvicorn must:
    #  - trust the X-Forwarded-* / Forwarded headers from the router
    #  - allow the router's pod CIDR as a trusted proxy so it doesn't reject
    #    the forwarded Host header with a 421 Misdirected Request.
    # "0.0.0.0/0" trusts all upstream IPs - safe because the pod is inside the cluster.
    forwarded_allow_ips = os.getenv("UVICORN_FORWARDED_ALLOW_IPS", "*")

    logger.info("Starting Capital Market MCP HTTP server on 0.0.0.0:8080 (run_mode=%s)", run_mode)

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8080,
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
    )
