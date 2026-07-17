from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


def _load_yaml_config(file_path: str) -> Dict[str, Any]:
    try:
        with open(file_path, "r") as f:
            return yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        logger.error("Failed to load YAML config from %s: %s", file_path, exc)
        raise


def _check_entitlement(
    gfcid: str,
    soeid: str,
    entitlement_query_template: str,
    deployment_env: str,
    db_type: str,
) -> Optional[str]:
    if not gfcid or not entitlement_query_template:
        return None
    from ..text2sql.utilities.db_adapter import execute_query

    query = entitlement_query_template.replace(":gfcid", f"'{gfcid}'").replace(
        ":soeid", f"'{soeid.lower()}'"
    )
    result = execute_query(sql_query=query, env=deployment_env, db_type=db_type)
    if not result:
        raise PermissionError(
            f"Access denied: You do not have the required entitlement for identifier {gfcid}"
        )
    first_row = result[0]
    if isinstance(first_row, dict):
        return next(iter(first_row.values()))
    return first_row[0]


def _format_filter_criteria_for_prompt(filter_criteria: Any) -> str:
    """Convert JSON/dict filter criteria into mandatory-filter prompt text."""
    if not filter_criteria:
        return ""

    if isinstance(filter_criteria, str):
        stripped = filter_criteria.strip()
        if not stripped:
            return ""
        if "Apply these mandatory filters to the WHERE clause:" in stripped:
            return stripped
        try:
            filter_criteria = json.loads(stripped)
        except json.JSONDecodeError:
            return f"Apply these mandatory filters to the WHERE clause: {stripped}"

    if not isinstance(filter_criteria, dict):
        return f"Apply these mandatory filters to the WHERE clause: {filter_criteria}"

    conditions = []
    for column, value in filter_criteria.items():
        if value is None or value == "":
            continue

        column_name = str(column).upper()
        if isinstance(value, (list, tuple, set)):
            values = list(value)
        elif isinstance(value, str) and "," in value:
            values = [part.strip() for part in value.split(",") if part.strip()]
        else:
            values = [value]

        escaped_values = [str(item).replace("'", "''") for item in values]
        if len(escaped_values) > 1:
            quoted = ", ".join(f"'{item}'" for item in escaped_values)
            conditions.append(f"{column_name} IN ({quoted})")
        else:
            conditions.append(f"{column_name} = '{escaped_values[0]}'")

    if not conditions:
        return ""
    return "Apply these mandatory filters to the WHERE clause: " + ", ".join(conditions)


def _upsert_filter_criteria_value(
    filter_criteria: Any,
    column_name: str,
    value: str,
) -> Any:
    """Add ``column_name=value`` to filter_criteria when missing."""
    if not value:
        return filter_criteria

    normalized_column = str(column_name).upper()

    if not filter_criteria:
        return {normalized_column: value}

    if isinstance(filter_criteria, dict):
        if any(str(k).upper() == normalized_column for k in filter_criteria.keys()):
            return filter_criteria
        merged = dict(filter_criteria)
        merged[normalized_column] = value
        return merged

    if isinstance(filter_criteria, str):
        stripped = filter_criteria.strip()
        if not stripped:
            return {normalized_column: value}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return filter_criteria
        if isinstance(parsed, dict):
            return _upsert_filter_criteria_value(parsed, normalized_column, value)
        return filter_criteria

    return filter_criteria


def _initialize_load_ids_for_domain(config) -> List[str]:
    load_id_path = config.get_load_id_config_path()
    if not load_id_path or not os.path.exists(load_id_path):
        return []
    try:
        cfg = _load_yaml_config(load_id_path)
        query = cfg.get("query")
        if not query:
            return []
        from ..text2sql.utilities.db_adapter import execute_query

        rows = execute_query(
            sql_query=query,
            env=config.get_deployment_env(),
            db_type=config.get_db_type(),
        )
        if rows and isinstance(rows[0], dict):
            return [str(next(iter(r.values()))) for r in rows]
        return [str(r[0]) for r in rows] if rows else []
    except Exception as exc:
        logger.error("Error initializing load IDs: %s", exc, exc_info=True)
        return []


def _initialize_as_of_date_for_domain(config) -> Optional[str]:
    path = config.get_as_of_date_config_path()
    if not path or not os.path.exists(path):
        return None
    try:
        cfg = _load_yaml_config(path)
        query = cfg.get("query")
        if not query:
            return None
        from ..text2sql.utilities.db_adapter import execute_query

        rows = execute_query(
            sql_query=query,
            env=config.get_deployment_env(),
            db_type=config.get_db_type(),
        )
        if rows:
            val = (
                rows[0]
                if not isinstance(rows[0], dict)
                else next(iter(rows[0].values()))
            )
            if isinstance(val, (list, tuple)):
                val = val[0]
            return str(val) if val else None
        return None
    except Exception as exc:
        logger.error("Error initializing as_of_date: %s", exc, exc_info=True)
        return None


def _resolve_query_context_preflight_hook(config) -> Optional[Any]:
    hook_getter = getattr(config, "get_query_context_preflight_hook", None)
    if not callable(hook_getter):
        return None
    try:
        hook = hook_getter()
    except Exception as exc:
        logger.warning("Failed to resolve query-context preflight hook: %s", exc)
        return None
    return hook if callable(hook) else None


def _run_query_context_preflight(
    config,
    domain: str,
    soeid: str,
    gfcid: str,
    gpnum: str,
    client_level: str,
    filter_criteria: str,
) -> Dict[str, Any]:
    hook = _resolve_query_context_preflight_hook(config)
    if not hook:
        return {"ok": True}

    result = hook(
        domain=domain,
        soeid=soeid,
        gfcid=gfcid,
        gpnum=gpnum,
        client_level=client_level,
        filter_criteria=filter_criteria,
        entitlement_enabled=config.get_entitlement_enabled(),
    )
    if not isinstance(result, dict):
        logger.warning("Ignoring invalid query-context preflight result: %r", result)
        return {"ok": True}

    if "ok" not in result:
        # Lenient mode: keep backward compatibility, but do not pass malformed
        # failure-like responses silently.
        has_failure_intent = bool(result.get("reason") or result.get("user_message"))
        logger.warning(
            "Preflight hook returned dict without required 'ok' key; "
            "defaulting ok=%s. Result=%r",
            not has_failure_intent,
            result,
        )
        result = dict(result)
        result["ok"] = not has_failure_intent
    return result


def _apply_prompt_variable_overrides(
    domain_variables: Dict[str, Any],
    overrides: Dict[str, Any],
) -> None:
    for key, value in overrides.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        domain_variables[key] = value