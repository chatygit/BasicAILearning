"""Entity-search helper utilities for text2sql tools."""

from __future__ import annotations

import hashlib
import json
from typing import Optional


def _sanitize_sql_input(value: str) -> str:
    """Escape SQL metacharacters in user input for safe string interpolation."""
    return value.replace("'", "''")


def _resolve_named_entity_search_template(config, entity_type: str = "") -> str:
    """Resolve SQL template for name-based entity search."""
    fallback = config.get_entity_search_query_template()
    strategy = (config.get_entity_search_strategy() or "").strip().lower()
    if strategy != "intent_sql":
        return fallback

    templates = config.get_entity_search_query_templates() or {}
    if not isinstance(templates, dict):
        return fallback

    raw_type = (entity_type or "").strip().lower()
    aliases = {
        "investor": "investor_name",
        "investor_name": "investor_name",
        "issuer": "issuer_name",
        "issuer_name": "issuer_name",
        "deal": "deal_name",
        "deal_name": "deal_name",
    }
    routed_key = aliases.get(raw_type, raw_type)
    candidate = templates.get(routed_key) if routed_key else None
    if isinstance(candidate, str) and candidate.strip():
        return candidate

    default_template = templates.get("default")
    if isinstance(default_template, str) and default_template.strip():
        return default_template

    return fallback


def _execute_sql_entity_search(
    config,
    entity_name: str = "",
    gfcid: str = "",
    cagid: str = "",
    entity_type: str = "",
    deal_id: str = "",
) -> list:
    from ..text2sql.utilities.db_adapter import execute_query

    env = config.get_deployment_env()
    db_type = config.get_db_type()
    mapper = config.get_entity_search_result_mapper()
    params: dict | None = None

    # Explicit identifiers take precedence over free-text names (most precise
    # wins). deal_id is checked FIRST so an ask that includes both a deal name
    # and an explicit deal id resolves by DEAL_ID and never falls into the
    # GFCID path.
    if deal_id:
        templates = config.get_entity_search_query_templates() or {}
        by_identifier = (
            templates.get("by_identifier", {}) if isinstance(templates, dict) else {}
        )
        routed = by_identifier.get("deal_id") if isinstance(by_identifier, dict) else ""
        if not (isinstance(routed, str) and routed.strip()):
            raise ValueError(
                "deal_id lookup is not configured for this domain "
                "(missing entity_search.query_templates.by_identifier.deal_id)."
            )
        query = routed
        params = {"deal_id": deal_id}
    elif gfcid:
        query_template = config.get_entity_search_by_gfcid_query_template()
        strategy = (config.get_entity_search_strategy() or "").strip().lower()
        if strategy == "intent_sql":
            templates = config.get_entity_search_query_templates() or {}
            by_identifier = (
                templates.get("by_identifier", {}) if isinstance(templates, dict) else {}
            )
            routed = by_identifier.get("gfcid") if isinstance(by_identifier, dict) else ""
            if isinstance(routed, str) and routed.strip():
                query_template = routed
        if ":gfcid" in query_template:
            query = query_template
            params = {"gfcid": gfcid}
        else:
            query = query_template.format(gfcid=_sanitize_sql_input(gfcid))
    elif cagid:
        query_template = config.get_entity_search_query_template()
        if ":entity_name" in query_template:
            query = query_template
            params = {
                "entity_name": cagid,
                "entity_name_pattern": f"%{cagid}%",
            }
        else:
            query = query_template.replace("{entity_name}", _sanitize_sql_input(cagid))
    elif entity_name:
        query_template = _resolve_named_entity_search_template(config, entity_type)
        if ":entity_name" in query_template:
            query = query_template
            params = {
                "entity_name": entity_name,
                "entity_name_pattern": f"%{entity_name}%",
            }
        else:
            query = query_template.format(entity_name=_sanitize_sql_input(entity_name))
    else:
        return []

    raw_results = execute_query(sql_query=query, env=env, db_type=db_type, params=params)
    return mapper(raw_results) if raw_results else []


def _extract_resolution_metadata(entity: dict, entity_type_hint: str = "") -> dict:
    """Build normalized identifier metadata for orchestrator hand-off."""
    if not isinstance(entity, dict):
        return {
            "entity_type": "unknown",
            "resolved_name": "",
            "resolved_identifier_type": "",
            "resolved_identifier_value": "",
            "confidence": "high",
            "user_confirmation_required": False,
            "filter_criteria": {},
        }

    candidates = [
        ("GPNUM", "investor", ["investor_name", "INVESTOR_NAME"]),
        ("GFCID", "issuer", ["issuer_name", "ISSUER_NAME"]),
        ("DEAL_ID", "deal", ["deal_name", "DEAL_NAME"]),
        ("TRANCHE_ID", "order", ["tranche_name", "TRANCHE_NAME"]),
        ("ORDER_ID", "order", ["order_id", "ORDER_ID"]),
    ]

    hint_map = {
        "investor": "GPNUM",
        "investor_name": "GPNUM",
        "issuer": "GFCID",
        "issuer_name": "GFCID",
        "deal": "DEAL_ID",
        "deal_name": "DEAL_ID",
        "tranche": "TRANCHE_ID",
        "tranche_name": "TRANCHE_ID",
        "order": "ORDER_ID",
        "order_id": "ORDER_ID",
    }

    def _pick(keys: list[str]) -> str:
        for key in keys:
            value = entity.get(key)
            if value is not None and str(value).strip() != "":
                return str(value).strip()
        return ""

    preferred_key = hint_map.get((entity_type_hint or "").strip().lower(), "")

    if preferred_key:
        preferred_identifier = _pick([preferred_key, preferred_key.lower()])
        if preferred_identifier:
            preferred_entity_type = next(
                (
                    entity_type
                    for id_key, entity_type, _ in candidates
                    if id_key == preferred_key
                ),
                "unknown",
            )
            preferred_name_keys = next(
                (
                    name_keys
                    for id_key, _, name_keys in candidates
                    if id_key == preferred_key
                ),
                [],
            )
            return {
                "entity_type": preferred_entity_type,
                "resolved_name": _pick(preferred_name_keys),
                "resolved_identifier_type": preferred_key,
                "resolved_identifier_value": preferred_identifier,
                "confidence": "high",
                "user_confirmation_required": False,
                "filter_criteria": {preferred_key: preferred_identifier},
            }

        return {
            "entity_type": (entity_type_hint or "unknown").replace("_name", ""),
            "resolved_name": _pick(
                [
                    "deal_name",
                    "DEAL_NAME",
                    "investor_name",
                    "INVESTOR_NAME",
                    "issuer_name",
                    "ISSUER_NAME",
                ]
            ),
            "resolved_identifier_type": "",
            "resolved_identifier_value": "",
            "preferred_identifier_type": preferred_key,
            "missing_preferred_identifier": True,
            "confidence": "medium",
            "user_confirmation_required": True,
            "filter_criteria": {},
        }

    for id_key, entity_type, name_keys in candidates:
        identifier = _pick([id_key, id_key.lower()])
        if identifier:
            return {
                "entity_type": entity_type,
                "resolved_name": _pick(name_keys),
                "resolved_identifier_type": id_key,
                "resolved_identifier_value": identifier,
                "confidence": "high",
                "user_confirmation_required": False,
                "filter_criteria": {id_key: identifier},
            }

    return {
        "entity_type": "unknown",
        "resolved_name": _pick(
            [
                "deal_name",
                "DEAL_NAME",
                "investor_name",
                "INVESTOR_NAME",
                "issuer_name",
                "ISSUER_NAME",
            ]
        ),
        "resolved_identifier_type": "",
        "resolved_identifier_value": "",
        "confidence": "high",
        "user_confirmation_required": False,
        "filter_criteria": {},
    }


def _build_entity_snapshot(entity: dict, context_mapping: dict | None) -> dict:
    """Build a domain-aware entity snapshot from context_mapping only."""
    snapshot: dict[str, str] = {}

    if not isinstance(context_mapping, dict):
        return snapshot

    for target, aliases in context_mapping.items():
        if not isinstance(aliases, list):
            continue
        value = ""
        for alias in aliases:
            if (
                alias in entity
                and entity.get(alias) is not None
                and str(entity.get(alias)).strip() != ""
            ):
                value = str(entity.get(alias)).strip()
                break
        if value:
            snapshot[str(target)] = value

    return snapshot


def _infer_entity_snapshot_source(entity_snapshot: dict) -> str:
    if not isinstance(entity_snapshot, dict):
        return "empty"
    has_mapped_keys = any(str(value).strip() != "" for value in entity_snapshot.values())
    return "context_mapping" if has_mapped_keys else "empty"


def _build_entity_selection_token(entity_snapshot: dict, resolution: dict) -> str:
    payload = {
        "entity_snapshot": dict(entity_snapshot or {}),
        "resolved_identifier_type": str(resolution.get("resolved_identifier_type") or ""),
        "resolved_identifier_value": str(resolution.get("resolved_identifier_value") or ""),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()