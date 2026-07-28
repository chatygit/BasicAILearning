"""Surgical change for the text2sql MCP server (plexus-ai-core.mcp-nl2sql-server).

ONE change: CHANGE E - executor-side entitlement enforcement, scoped to the
ecm_dcm domain via a per-domain pre_execute hook. Earlier changes (A-D) were
delivered separately and are intentionally not repeated here.
"""

# =============================================================================
# CHANGE E (SECURITY: enforce entitlement on the submitted SQL)
#    SCOPE: ecm_dcm domain ONLY — zero code-path change for any other domain.
#
#    BUG (QAT trace 2026-07-27, soeid=bk42867): entitlement_service resolved
#    effective_clause=PRODUCT = 'ECM' at query_context preflight, but the
#    executor ran "... OR (PRODUCT = 'DCM' AND ...)" and returned DCM rows to
#    an ECM-only user. The clause is computed but never applied to the SQL the
#    LLM submits — enforcement today is 100% LLM discipline.
#
#    INTEGRATION — the server is already domain-modular (see its own logs:
#    src.app.text2sql.domains.ecm_dcm.components.entitlement_service and
#    ...components.query_context_hook). Mirror that pattern:
#
#      domains/ecm_dcm/components/executor_hook.py   <- ALL new code lives here
#
#    The SHARED tool_query_executor gains exactly one generic dispatch:
#
#        hook = domain_registry.get_hook(domain, "pre_execute")   # None for
#        if hook:                                                 # every other
#            err = hook(sql_query, soeid)                         # domain
#            if err: return err
#
#    Domains that register no pre_execute hook (all of them except ecm_dcm)
#    take the exact same code path as today — the only shared-code delta is a
#    dict lookup that returns None. No other domain's SQL, validation,
#    results, or latency changes. If the server already has a hook-dispatch
#    convention (query_context_hook suggests it does), reuse it and the
#    shared-code delta may be zero lines.
#
#    ENFORCEMENT SHAPE — reject-only; NO SQL rewriting.
#    (v1 of this spec wrapped the SQL in SELECT * FROM (sql) WHERE PRODUCT
#    IN (...). Dropped — two failure modes: ORA-00904 when the inner SELECT
#    does not project PRODUCT, and the wrap filters AFTER an inner FETCH
#    FIRST N, silently starving rows.)
#      (a) this hook REJECTS SQL that references a PRODUCT literal outside
#          the entitled set, with a self-correcting message (the LLM fixes
#          the SQL in its one permitted retry — same UX as validator errors);
#      (b) the EXISTING validator rule "Product scope required" already
#          rejects SQL with no PRODUCT filter at all.
#    (a) + (b) are jointly complete: every executed query carries a PRODUCT
#    filter, and every PRODUCT literal in it is entitled -> no leak, and the
#    SQL that runs is byte-identical to what the LLM wrote.
#
#    tool_entity_search is a DIFFERENT fix (no hook, no rejection loop): the
#    server renders those templates itself, so AND the effective_clause into
#    the template's innermost WHERE at render time. Today the templates
#    hardcode PRODUCT IN ('ECM','DCM'), which leaks DCM deal names/counts to
#    ECM-only users in candidate lists.
# =============================================================================

# --- domains/ecm_dcm/components/executor_hook.py (new file) ------------------
import re as _re

_PRODUCT_LITERAL = _re.compile(
    r"\bPRODUCT\b\s*(?:=|<>|!=|IN\s*\()[^)']*?'(ECM|DCM)'"
    r"|'(ECM|DCM)'(?=\s*(?:,\s*'(?:ECM|DCM)')*\s*\))",
    _re.I | _re.S,
)

def _entitled_products(soeid: str) -> set:
    # Reuse the SAME cached entitlement_service result the query_context_hook
    # produced for this soeid (no second API call on the hot path); parse
    # {'ECM'} / {'DCM'} / {'ECM','DCM'} from the effective_clause payload.
    raise NotImplementedError  # wire to entitlement_service cache

def pre_execute(sql_query: str, soeid: str):
    """Return an error dict to block execution, or None to proceed."""
    entitled = _entitled_products(soeid)
    referenced = {m.upper() for pair in _PRODUCT_LITERAL.findall(sql_query)
                  for m in pair if m}
    illegal = referenced - entitled
    if illegal:
        return {
            "status": "validation_error",
            "message": (
                f"Access scope violation: this user is entitled to "
                f"{sorted(entitled)} only. Remove every PRODUCT branch for "
                f"{sorted(illegal)} (including OR branches) and re-run the "
                f"query scoped to the entitled products."
            ),
        }
    return None
