"""Surgical changes for the text2sql MCP server - v2 batch.

v1 (text2sql_surgical_changes.py) is the earlier batch (E, F, G, H, I, J-spec)
and is left untouched as the historical handoff record. This file carries the
AS-SHIPPED versions that superseded v1 specs after code review on the live
server code. Apply from THIS file; where a change appears in both, v2 wins.
"""

# =============================================================================
# CHANGE J (AS SHIPPED 2026-07-31): tool_entity_search - rows are not entities
#
# WHY: a deal-name search against a grain-buggy template returned 50 rows that
# were ALL deal_id 25246247 (one row per investor). len(results) > 1 made it
# "ambiguous" and the agent asked the user for a Deal ID it already had 50
# times. The collapse below resolves such degenerate sets; genuinely distinct
# candidates (e.g. Suneel999 vs TESTSUNEEL999) are untouched.
#
# PLACEMENT: in tool_entity_search, AFTER the entity filter processor
# (filter_proc) block and BEFORE the  `if len(results) > 1:`  disambiguation
# branch.
#
# Two refinements vs the v1 spec:
#   1. entity_type-aware key: when the caller declared the search type, the
#      entity key is that type's id field by definition (deal_name->deal_id,
#      investor_name->gpnum, issuer_name->gfcid); the or-chain is only the
#      unknown-type fallback.
#   2. MERGE instead of results[:1]: row[0] of an exploded set carries
#      artifact fields from the explosion dimension (investor_name="PUBLICIS"
#      on a DEAL entity). Keeping them lets _extract_resolution_metadata
#      mis-resolve the identifier type. Fields that vary across rows are
#      blanked; fields all rows agree on are the true entity data.
# =============================================================================

_KEY_FIELDS = {"deal_name": "deal_id", "investor_name": "gpnum",
               "issuer_name": "gfcid"}


def collapse_degenerate_results(results, entity_type):
    """One distinct entity exploded across rows -> one merged row.

    Paste-ready inline form (matching the shipped code):

        kf = _KEY_FIELDS.get(entity_type)

        def _entity_key(r):
            if kf:
                return r.get(kf) or r.get(kf.upper()) or ""
            return (r.get("deal_id") or r.get("gpnum") or r.get("gfcid")
                    or r.get("DEAL_ID") or r.get("GPNUM") or r.get("GFCID") or "")

        distinct = {k for k in (_entity_key(r) for r in results) if k}
        if len(results) > 1 and len(distinct) == 1:
            merged = dict(results[0])
            for r in results[1:]:
                for k, v in r.items():
                    if merged.get(k) != v:
                        merged[k] = ""
            results = [merged]
    """
    kf = _KEY_FIELDS.get(entity_type)

    def _entity_key(r):
        if kf:
            return r.get(kf) or r.get(kf.upper()) or ""
        return (r.get("deal_id") or r.get("gpnum") or r.get("gfcid")
                or r.get("DEAL_ID") or r.get("GPNUM") or r.get("GFCID") or "")

    distinct = {k for k in (_entity_key(r) for r in results) if k}
    if len(results) > 1 and len(distinct) == 1:
        merged = dict(results[0])
        for r in results[1:]:
            for k, v in r.items():
                if merged.get(k) != v:
                    merged[k] = ""
        results = [merged]
    return results


# -----------------------------------------------------------------------------
# TEST PROMPTS (run each in a FRESH session; QAT with the old exploded
# templates is the ideal test bed - the collapse only has work where the
# template explodes):
#
# 1. POSITIVE - "Show me the details of deal RM_Automation"
#    Before: 50-row "ambiguous" -> "please provide the specific Deal ID".
#    After:  proceeds to deal 25246247, no question. Trace fingerprints:
#    entity_search status "success", resolved entity has deal_id/deal_name
#    populated and investor_name/gpnum BLANK (merge stripped artifacts),
#    next_action present.
#
# 2. NEGATIVE CONTROL - "What are the security identifiers for deal Suneel999"
#    Must STILL show numbered options (Suneel999 / TESTSUNEEL999 = two
#    distinct deal_ids). If this auto-resolves, the collapse over-fires.
#
# 3. TYPED-KEY PATH - "Show me all order details for investor PUBLICIS"
#    One investor exploded across deals -> resolves via investor_name->gpnum
#    key. A real multi-entity name ("Blackrock") must still disambiguate on
#    this env.
#
# After the domain.yaml promote (entity-grain templates), prompt 1's collapse
# becomes a silent no-op - prompt 2 is then the only visible evidence the
# safety net exists, which is correct behavior for a safety net.
# -----------------------------------------------------------------------------


# =============================================================================
# CHANGE K (tool_entity_search: suggested_args must match the tool contract)
#
# QAT trace 2026-07-31: after a successful resolution, next_action.suggested_args
# included  "filter_criteria": resolution.get("filter_criteria", {})  - a DICT.
# tool_query_context declares filter_criteria: str, so the agent passing the
# suggestion through verbatim died on pydantic ("Input should be a valid
# string, input_value={'DEAL_ID': ...}"), and the model's recovery attempt
# degenerated into code-style calling (MALFORMED_FUNCTION_CALL), killing the
# turn. The server must never suggest arguments its own tools reject.
#
# In tool_entity_search's single-result return, replace:
#
#         "filter_criteria": resolution.get("filter_criteria", {}),
#
# with:
#
#         "filter_criteria": (
#             json.dumps(fc) if isinstance((fc := resolution.get("filter_criteria")), dict) and fc
#             else (fc if isinstance(fc, str) else "")
#         ),
#
# (or the expanded equivalent if walrus reads poorly in the codebase:
#         fc = resolution.get("filter_criteria")
#         if isinstance(fc, dict):
#             fc = json.dumps(fc) if fc else ""
#         suggested_filter_criteria = fc or ""
# )
# Contract: filter_criteria in suggested_args is ALWAYS a string - a JSON
# object serialized, or "" - exactly what tool_query_context accepts.
#
# TEST: "Show me the details of deal RM_Automation" (fresh session) - the
# resolution should flow into query_context with no pydantic error and no
# MALFORMED_FUNCTION_CALL; trace shows filter_criteria as a JSON STRING.
# =============================================================================


# =============================================================================
# CHANGE L (entity search must honour the user's product entitlement)
#   supersedes the literal string-replace shipped as CHANGE I1
#
# WHY (user, 2026-08-04): "our entity search queries are not using the product
# entitlement in domain yaml - we search both ECM/DCM irrespective of the user."
# Correct: domain.yaml defines DOMAIN_PRODUCT_ENTITLEMENT_CLAUSE and the
# query_context preflight overrides it per user - but that override lands in
# `domain_variables` (the LLM's prompt variables) only. _execute_sql_entity_search
# renders template text straight from config, so all TEN template sites keep the
# hardcoded PRODUCT IN ('ECM','DCM'):  3 named-entity templates, 4 tiered
# sub-selects, 3 by_identifier templates. Result: an ECM-only user sees DCM deal
# names, deal counts and PRODUCTS labels in candidate lists.
#
# I1 patched this post-render with query.replace("PRODUCT IN ('ECM', 'DCM')", ...)
# - exact-spacing dependent, silently no-ops on template drift, and fails OPEN
# (i.e. leaks) when it misses. L fixes all three.
#
# In text2sql_entity_helpers.py, REPLACE the CHANGE I1 block (the
# `if soeid and config.get_domain_name() == "ecm_dcm":` ... query.replace(...))
# with:
#
#     import re as _re
#
#     _BOTH_PRODUCT_CLAUSE = _re.compile(
#         r"(?i)(?:__PRODUCT_CLAUSE__"
#         r"|\bPRODUCT\s+IN\s*\(\s*'ECM'\s*,\s*'DCM'\s*\)"
#         r"|\bPRODUCT\s+IN\s*\(\s*'DCM'\s*,\s*'ECM'\s*\))"
#     )
#
#     if soeid and config.get_domain_name() == "ecm_dcm":
#         from ..text2sql.domains.ecm_dcm.components.entitlement_service import (
#             perform_initial_entitlement_check,
#         )
#         result = perform_initial_entitlement_check(soeid)     # cached: no extra API call
#         clause = result.get("product_clause") if result.get("ok") else ""
#         if clause:
#             query, n = _BOTH_PRODUCT_CLAUSE.subn(clause, query)
#             logger.info(
#                 "ecm_dcm entity-search scope for soeid=%s: %s (%d site(s))",
#                 soeid, clause, n,
#             )
#             if n == 0:
#                 logger.warning(
#                     "ecm_dcm entity-search: NO product-clause site found in the "
#                     "template - candidates are UNSCOPED and may leak cross-product "
#                     "rows. Template drift? (expected PRODUCT IN ('ECM','DCM') or "
#                     "__PRODUCT_CLAUSE__)"
#                 )
#
# Why this shape:
#   - uses the SAME clause the preflight/LLM use (product_clause from
#     entitlement_service) instead of rebuilding one -> one source of truth,
#     and dual-entitled users get PRODUCT IN ('ECM','DCM') = today's behavior;
#   - tolerant of spacing/case/order drift (battery-tested);
#   - also accepts an explicit __PRODUCT_CLAUSE__ token, so domain.yaml can
#     migrate to a placeholder later IN EITHER DEPLOY ORDER (this code handles
#     both spellings - no coupling between the config promote and the deploy);
#   - logs the applied scope and SHOUTS on a zero-site miss, so a silent leak
#     becomes a visible log line.
#
# TEST: as an ECM-only soeid, entity_search a mixed investor (e.g. Blackrock).
#   log shows: entity-search scope for soeid=...: PRODUCT = 'ECM' (1 site(s))
#   candidates show ECM-only deal counts and PRODUCTS = 'ECM' (never 'ECM+DCM').
#   As a dual-entitled soeid: PRODUCT IN ('ECM', 'DCM') - identical to today.
# =============================================================================
