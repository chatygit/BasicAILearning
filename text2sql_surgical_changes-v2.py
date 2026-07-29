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
