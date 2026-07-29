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

# AS SHIPPED (2026-07-30): entitlement_service exposes
#   get_entitled_products(soeid) -> list[str]   (HTTP POST to entitlement API)
# so no clause parsing is needed. 5-min TTL cache keeps the API off the
# per-query hot path; fail-open keeps a broken API from locking users out
# (the query_context preflight remains the hard gate).
import time as _time
from .entitlement_service import get_entitled_products

_CACHE: dict = {}
_CACHE_TTL_SECONDS = 300


def entitled_products(soeid: str) -> set:
    now = _time.time()
    hit = _CACHE.get(soeid)
    if hit and now - hit[1] < _CACHE_TTL_SECONDS:
        return hit[0]
    try:
        products = {p.upper() for p in get_entitled_products(soeid)}
    except Exception:
        return set()  # fail open -> pre_execute passes through
    _CACHE[soeid] = (products, now)
    return products

def pre_execute(sql_query: str, soeid: str):
    """Return an error dict to block execution, or None to proceed."""
    entitled = entitled_products(soeid)
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


# --- Integration (2026-07-29, now EXACT - the convention already exists) ----
# _run_query_context_preflight resolves a per-domain hook via
# _resolve_query_context_preflight_hook(config) and no-ops ({"ok": True})
# when a domain registers none. Mirror that for the executor:
#
#   def _resolve_pre_execute_hook(config):
#       # same registry/config mechanism as the preflight hook resolver
#       return getattr(config, "get_pre_execute_hook", lambda: None)()
#
# In tool_query_executor, in the marked CHANGE E SLOT (after
# validate_sql_query, before execute_query):
#
#       pre_hook = _resolve_pre_execute_hook(config)
#       if pre_hook:
#           err = pre_hook(sql_query=sql_query, soeid=soeid)
#           if isinstance(err, dict) and err:
#               return err
#
# Contract mirrors the preflight's lenient conventions: None = proceed,
# error dict = returned verbatim. Only ecm_dcm registers a hook, so every
# other domain resolves None and stays byte-identical to today.
# The SAME entitled_products() feeds CHANGE I1 (entity_search template
# entitlement) - one cache, one review.


# =============================================================================
# CHANGE F (SPEED: kill the data_context hop for standard listings)
#
# NOTE: written against the CURRENT server code (which has evolved past the
# local text2sql.py copy - it now builds `safe_rows` via CHANGE C's safe
# serialization). Anchors below are semantic, not line numbers.
# =============================================================================

# --- F1: executor sample guard (the [:20] line is already applied) --------
# Baseline: text2sql-current.py (verbatim server code, 2026-07-29).
# REPLACE the line:      sample = safe_rows[:20]
# WITH the block below. Battery-tested: normal rows keep 20; monster rows
# (pipe-list members, identifier chains) shrink to a ~9k-char budget and
# never below 5; oversize cells are capped with an explicit marker the
# agent recognizes.

SAMPLE_MAX_ROWS = 20          # chat display cap - listings answer from executor
SAMPLE_CELL_CHARS = 400       # one pipe-list cell can be 1000s of chars
SAMPLE_CHAR_BUDGET = 9000     # ~2.2k tokens; speed win must not become prefill loss

def _cap_cells(row):
    return {k: (v[:SAMPLE_CELL_CHARS] + " ...(truncated)")
               if isinstance(v, str) and len(v) > SAMPLE_CELL_CHARS else v
            for k, v in row.items()}

def build_sample(safe_rows):
    sample = [_cap_cells(r) for r in safe_rows[:SAMPLE_MAX_ROWS]]
    while len(sample) > 5 and len(json.dumps(sample, default=str)) > SAMPLE_CHAR_BUDGET:
        sample = sample[:len(sample) - 5]
    return sample

#   sample = build_sample(safe_rows)
#
# row_count stays the TRUE total. Agent configs are already env-agnostic
# (they compare row_count to len(sample_data), not to a hardcoded 5) and
# know that a cell ending "...(truncated)" means: full value via data_context.

# --- F2: query_context - stop shipping validation_rules (CHANGE A re-affirm)
# In tool_query_context's return dict, drop the "validation_rules" key
# (~6.4k tokens of prefill per query). The executor validates server-side and
# returns the fired rule's error_message - the LLM never needs the rule list.
# If other domains depend on it, gate per domain:
#   if config.get("ship_validation_rules", True): payload["validation_rules"] = ...


# =============================================================================
# CHANGE G (SPEED: stop double-shipping the schema context)  ** NEW, BIGGEST **
#
# In the CURRENT tool_query_context (transcribed 2026-07-29):
#     context = _compact_schema_context(config.get_schema_context())
#     ...
#     domain_variables["input_context"] = context          # copy #1
#     ...
#     return { ..., "schema_context": context,             # copy #2
#              "domain_config": domain_variables, ... }
#
# The ~7k-token schema context is returned TWICE in one payload. Tool
# responses persist in the conversation, so the duplicate is re-paid in the
# prefill of every later hop and every later turn of the session.
#
# FIX (gate per domain to keep other domains untouched):
#
#     if config.get_domain_name() == "ecm_dcm":   # or a config flag:
#         domain_variables["input_context"] = ""  # schema ships ONCE,
#                                                 # in "schema_context"
#
# PRE-CHECK before landing: grep the ecm_dcm prompt/domain templates for
# "{input_context}" - if any template interpolates it, point that template
# at schema_context instead (the agent instruction already reads
# schema_context as the schema authority).
#
# Minor extras in the same payload (small, optional):
#   - "user_query_with_context" duplicates user_prompt + filter_instruction
#   - "accepted_input_params" is static boilerplate per call
#
# ALSO CONFIRMED in this method (no action):
#   - CHANGE A landed: validation_rules = [] (empty) - 6.4k/query saved
#   - current_date is injected server-side into domain_config (date anchor)
#   - prefetch pool timeout is 120s (TEXT2SQL_PREFETCH_TIMEOUT_SECONDS):
#     for ecm_dcm the load_ids / as_of_date branches look inert, but a slow
#     entitlement API can block query_context up to 120s - worth a lower
#     env value (e.g. 15s) once [perf] logs confirm typical latency.
#
# CHANGE E wiring note: the preflight (_run_query_context_preflight) is where
# effective_clause is resolved. The executor hook needs soeid->products WITHOUT
# a second API call: cache it at preflight time in a module-level TTL dict
# keyed by soeid. CAVEAT: query_context and query_executor may hit DIFFERENT
# PODS - on cache miss the hook must fall back to calling entitlement_service
# directly (same code path the preflight uses). Need the preflight /
# entitlement_service internals to write this exactly.
# =============================================================================


# =============================================================================
# CHANGE H (SPEED: data_context payload diet - rows ship up to 3x)
#
# Current tool_data_context (transcribed 2026-07-29) returns the SAME rows in:
#   1. "markdown_table"        - display_df rendered to markdown
#   2. "raw_results_markdown"  - _build_raw_results_markdown(df|head(threshold))
#      The ecm_dcm agent is INSTRUCTED to never use this field - it is pure
#      prefill waste for this domain, up to <threshold> rows of markdown.
#   3. "summary_context"       - _build_summary_context(markdown_table=...) is
#      HANDED the table; if it embeds it (verify internals), that's copy #3.
#
# H1. Gate raw_results_markdown off for ecm_dcm:
#         if config.get_domain_name() == "ecm_dcm":
#             raw_results_markdown = ""
#     (other domains unchanged)
# H2. RESOLVED (source reviewed 2026-07-29): _build_summary_context accepts
#     markdown_table as a parameter and NEVER uses it - no third row copy.
#     No gate needed. Optional cleanups found in it:
#       a) drop the unused markdown_table param (dead signature)
#       b) ctx["columns_retrieved"] duplicates the response's top-level
#          "columns" key (metadata, not rows - small; dedupe if convenient)
#       c) NON-large path runs intelligent_data_reduction(include_full_data=
#          True) and ctx["analysis_summary"] ships that whole analysis dict -
#          if it embeds full rows, results 21..threshold ship twice. Closed
#          automatically if H4 sets threshold=20 (band becomes empty);
#          otherwise set include_full_data=False for ecm_dcm.
# H3. Dead code cleanup (CHANGE B remnant): the final
#         domain_variables = config.get_prompt_variables(platform)
#         domain_variables.update(config.get_text_to_sql_prompt_kwargs())
#     block is computed but never returned - delete both lines.
# H4. RESOLVED (2026-07-29): get_large_dataset_threshold defaults to 20
#     (_platform_threshold(default=20, platform)) - already aligned with the
#     20-row executor sample and the 20-row display cap. No change. (Verify
#     no per-platform override diverges, e.g. mobile.) Consequence: with F1,
#     data_context is only ever called when row_count > 20, i.e.
#     is_large_dataset is ALWAYS true on ecm_dcm calls - the non-large
#     DataAnalyzer/include_full_data branch is dead for this domain, which
#     also closes H2(c) without any code change.
#
# Also inert-but-wasted for ecm_dcm (cleanup, not speed):
#   _build_credit_facility_verified_section(df) runs for every domain;
#   wallet-only constant_filters block is correctly gated by domain name.
# =============================================================================


# =============================================================================
# CHANGE I (tool_entity_search: close the entitlement leak + cap the payload)
#
# Current code (transcribed 2026-07-29): the generic path calls
#     _execute_sql_entity_search(config, entity_name, gfcid, cagid,
#                                entity_type, deal_id)
# with NO soeid - the ecm_dcm search templates (hardcoded
# PRODUCT IN ('ECM','DCM')) run with zero user context. An ECM-only user
# receives DCM deal names/counts in candidate lists. CONFIRMED at code level.
#
# I1 (SECURITY - same family as CHANGE E): mirror the in-house
#     _credit_facility_entity_search "persona-aware search with inline
#     entitlement" pattern:
#       - pass soeid into _execute_sql_entity_search for ecm_dcm
#       - at template render time, AND the resolved entitlement clause into
#         the innermost WHERE (same cached soeid->products lookup CHANGE E
#         uses; cross-pod fallback = direct entitlement_service call)
#     Result: candidate names, deal_counts, last_active and PRODUCTS labels
#     all reflect entitled rows only - nothing to scrub downstream.
#
# I2 (SPEED): the ambiguous branch returns the FULL results list (templates
#     fetch up to 50 enriched candidates); the agent displays at most 10.
#       "results": results[:12],
#       "count": len(results),          # true total - agent says "and N more"
#     Config-gated per domain if preferred. With exact-first tier gating,
#     multi-candidate lists only occur on substring/soundex matches, but 50
#     enriched rows there is 3-4k of prefill for 10 displayed options.
# =============================================================================


# =============================================================================
# CHANGE J (tool_entity_search: rows are not entities - collapse before the
#           ambiguity check)
#
# QAT trace 2026-07-30: a deal-name search returned 50 rows that were ALL
# deal_id 25246247 (one row per investor - a template grain bug, fixed in
# domain.yaml, but old envs / future template bugs can recur). The ambiguity
# branch tests len(results) > 1, so ONE deal presented as "Multiple matches
# found" and the agent asked the user for a Deal ID it already had 50 times.
#
# In tool_entity_search, immediately BEFORE:  if len(results) > 1:
#
#     def _entity_key(r):
#         return (r.get("deal_id") or r.get("gpnum") or r.get("gfcid")
#                 or r.get("DEAL_ID") or r.get("GPNUM") or r.get("GFCID") or "")
#     distinct = {k for k in (_entity_key(r) for r in results) if k}
#     if len(results) > 1 and len(distinct) == 1:
#         results = results[:1]   # one distinct entity -> resolved, not ambiguous
#
# (adjust key names to the mapped result field names). Belt to the domain.yaml
# braces: by_identifier/gfcid/gpnum/deal_id templates are now entity-grain
# (GROUP BY the entity), so this collapse should rarely fire - it exists so a
# grain regression degrades to "resolved" instead of "stupid question".
# =============================================================================
