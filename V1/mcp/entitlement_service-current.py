"""VERBATIM transcription of src/app/text2sql/domains/ecm_dcm/components/
entitlement_service.py (shared by bk42867 via screenshots, 2026-07-30).

ARCHITECTURE (the important part):
  - get_entitled_products(soeid)          RAW API fetch - NO cache. POST every call.
  - perform_initial_entitlement_check()   THE cached entry point (19 usages):
        fresh cache hit  -> source="cache"
        API success      -> _cache_put + source="api"
        API transient    -> last-known-good stale fallback, source="cache_fallback"
        misconfig        -> ok=False, retryable=False (never stale-falls-back)
        no entitlements  -> ok=False, reason="no_ecm_dcm_entitlement"
  - _SCOPE_CACHE = TTLScopeCache("ecm_dcm_entitlement"), TTL env-tunable
    (ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS, default 300).

=> executor_hook must call perform_initial_entitlement_check, NOT
   get_entitled_products - that is what shares the cache with the preflight.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ....utilities.entitlement_cache import TTLScopeCache

logger = logging.getLogger(__name__)

_ALLOWED_PRODUCTS: tuple[str, ...] = ("ECM", "DCM")

# Per-SOEID entitlement cache: TTL + last-known-good fallback via the shared,
# domain-agnostic TTLScopeCache.
_SCOPE_CACHE: TTLScopeCache[List[str]] = TTLScopeCache(name="ecm_dcm_entitlement")


def _cache_ttl_seconds() -> float:
    try:
        return float(os.getenv("ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS", "300"))
    except ValueError:
        return 300.0


def _cache_get(soeid: str) -> Optional[List[str]]:
    """Return cached products if a fresh entry exists, else None."""
    return _SCOPE_CACHE.get(soeid)


def _cache_get_stale(soeid: str) -> Optional[List[str]]:
    """Return cached products regardless of expiry (last known-good)."""
    return _SCOPE_CACHE.get_stale(soeid)


def _cache_put(soeid: str, products: List[str]) -> None:
    _SCOPE_CACHE.put(soeid, list(products), _cache_ttl_seconds())


def clear_entitlement_cache() -> None:
    """Test/ops helper to reset the entitlement cache."""
    _SCOPE_CACHE.clear()


def _build_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(total=2, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(pool_connections=5, pool_maxsize=10, max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _resolve_ssl_verify() -> Any:
    ssl_cert = os.getenv("SSL_CERT_FILE")
    if ssl_cert:
        return ssl_cert
    if os.getenv("DISABLE_SSL_VERIFY", "").lower() == "true":
        return False
    return True


def _normalize_products(raw: Any) -> list[str]:
    values: list[str] = []
    if isinstance(raw, str):
        values = [p.strip().upper() for p in raw.replace("'", "").split(",") if p.strip()]
    elif isinstance(raw, list):
        values = [str(p).strip().upper() for p in raw if str(p).strip()]
    deduped: list[str] = []
    for candidate in values:
        if candidate in _ALLOWED_PRODUCTS and candidate not in deduped:
            deduped.append(candidate)
    return deduped


def _extract_products_from_clause(clause: str) -> list[str]:
    if not clause:
        return []
    # Clause shapes vary by policy backend. Token extraction keeps parsing robust.
    candidates = re.findall(r"\b(ECM|DCM)\b", clause.upper())
    products: list[str] = []
    for value in candidates:
        if value not in products:
            products.append(value)
    return products


def build_product_in_clause(products: list[str]) -> str:
    entitled = [p for p in _ALLOWED_PRODUCTS if p in set(products)]
    if not entitled:
        return ""
    if len(entitled) == 1:
        return f"PRODUCT = '{entitled[0]}'"
    values = ", ".join(f"'{p}'" for p in entitled)
    return f"PRODUCT IN ({values})"


def get_entitled_products(soeid: str) -> list[str]:
    """RAW fetch - no caching here. Callers wanting the cache go through
    perform_initial_entitlement_check."""
    url = os.getenv("ECM_DCM_PRODUCT_ENTITLEMENT_URL", "").strip()
    policy_id = os.getenv("ECM_DCM_ENTITLEMENT_POLICY_ID", "").strip()

    if not url or not policy_id:
        raise ValueError(
            "Missing ECM/DCM entitlement API settings. "
            "Ensure ECM_DCM_PRODUCT_ENTITLEMENT_URL and "
            "ECM_DCM_ENTITLEMENT_POLICY_ID are configured."
        )

    payload = {"policyId": policy_id, "soeid": soeid}
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-citiportal-loginid": soeid,
    }

    logger.info(
        "ECM/DCM entitlement API request -> POST %s (policyId=%s, soeid=%s)",
        url, policy_id, soeid,
    )
    response = _build_session().post(
        url, json=payload, headers=headers, timeout=30, verify=_resolve_ssl_verify(),
    )
    logger.info(
        "ECM/DCM entitlement API response <- HTTP %s (soeid=%s)",
        response.status_code, soeid,
    )

    if response.status_code != 200:
        raise RuntimeError(
            "ECM/DCM entitlement API request failed "
            f"(HTTP {response.status_code}): {response.text[:500]}"
        )

    data = response.json()
    if not isinstance(data, dict):
        return []

    direct_products = _normalize_products(
        data.get("entitled_products")
        or data.get("entitledProducts")
        or data.get("products")
    )
    if direct_products:
        return direct_products

    clause = (
        data.get("product_clause")
        or data.get("productClause")
        or data.get("sql_clause")
        or data.get("sqlClause")
        or data.get("clause")
        or data.get("where_clause")
        or data.get("whereClause")
    )
    if isinstance(clause, str):
        return _extract_products_from_clause(clause)

    clauses = data.get("sql_clauses") or data.get("sqlClauses") or data.get("clauses")
    if isinstance(clauses, list):
        for item in clauses:
            if isinstance(item, str):
                products = _extract_products_from_clause(item)
            elif isinstance(item, dict):
                candidate_clause = (
                    item.get("sql_clause")
                    or item.get("sqlClause")
                    or item.get("clause")
                    or item.get("where_clause")
                    or item.get("whereClause")
                )
                products = _extract_products_from_clause(
                    candidate_clause if isinstance(candidate_clause, str) else ""
                )
            else:
                products = []

            if products:
                return products

    return []


def perform_initial_entitlement_check(
    soeid: Optional[str],
    conversation_id: Optional[str] = None,
    entitlement_enabled: bool = True,
) -> Dict[str, Any]:
    """Validate ECM/DCM product entitlements before any downstream actions."""
    del conversation_id

    logger.info("ECM/DCM entitlement gate invoked")

    if not entitlement_enabled:
        logger.info("ECM_DCM_ENTITLEMENT_FEATURE_FLAG disabled - skipping gate")
        default_products = list(_ALLOWED_PRODUCTS)
        return {
            "ok": True,
            "entitled_products": default_products,
            "product_clause": build_product_in_clause(default_products),
            "entitlement_check_skipped": True,
        }

    if not soeid:
        return {
            "ok": False,
            "reason": "missing_soeid",
            "user_message": (
                "I'm unable to verify your ECM/DCM access entitlements because no "
                "user identifier was provided. Please re-authenticate and try again."
            ),
        }

    cached = _cache_get(soeid)
    if cached:
        product_clause = build_product_in_clause(cached)
        logger.info(
            "ECM/DCM entitlement cache hit for soeid=%s: effective_clause=%s",
            soeid, product_clause,
        )
        return {
            "ok": True,
            "entitled_products": cached,
            "product_clause": product_clause,
            "entitlement_source": "cache",
        }

    try:
        entitled_products = get_entitled_products(soeid)
    except ValueError as exc:
        # Configuration error (missing ECM_DCM_PRODUCT_ENTITLEMENT_URL /
        # ECM_DCM_ENTITLEMENT_POLICY_ID). This is a misconfiguration, NOT a
        # transient outage: retrying will not fix it and we must NOT serve a
        # stale-cache fallback (which could grant an out-of-date scope).
        logger.error(
            "ECM/DCM entitlement misconfigured for soeid=%s: %s",
            soeid, exc, exc_info=True,
        )
        return {
            "ok": False,
            "reason": "entitlement_misconfigured",
            "retryable": False,
            "user_message": (
                "I'm unable to verify your ECM/DCM access entitlements because "
                "the entitlement service is not configured correctly. Please "
                "contact support."
            ),
        }
    except RuntimeError as exc:
        logger.error(
            "Entitlement API failed for soeid=%s: %s", soeid, exc, exc_info=True,
        )
        # Transient failure: fall back to last known-good scope so a single
        # API blip does not flip an active session into "permission denied".
        stale = _cache_get_stale(soeid)
        if stale:
            product_clause = build_product_in_clause(stale)
            logger.warning(
                "Using cached ECM/DCM entitlement scope for soeid=%s after API "
                "failure. effective_clause=%s",
                soeid, product_clause,
            )
            return {
                "ok": True,
                "entitled_products": stale,
                "product_clause": product_clause,
                "entitlement_source": "cache_fallback",
            }
        return {
            "ok": False,
            "reason": "entitlement_unavailable",
            "retryable": True,
            "user_message": (
                "I'm unable to verify your ECM/DCM access entitlements right now "
                "due to a system issue. Please try again in a few minutes, or "
                "contact support if the issue persists."
            ),
        }

    # Single source of truth: derive the clause from the same filtered list
    # that we cache and return, so the cached scope and product_clause can
    # never diverge.
    matched = [p for p in entitled_products if p in set(_ALLOWED_PRODUCTS)]
    product_clause = build_product_in_clause(matched)

    if not product_clause:
        logger.info(
            "Access denied for soeid=%s - user has no ECM or DCM entitlements "
            "(raw entitled list: %s).",
            soeid, entitled_products,
        )
        return {
            "ok": False,
            "reason": "no_ecm_dcm_entitlement",
            "retryable": False,
            "user_message": (
                "You don't have entitlements to access ECM or DCM data. "
                "Please contact your administrator or the entitlements team "
                "to request access to Equity Capital Markets (ECM) and/or "
                "Debt Capital Markets (DCM) data."
            ),
        }

    _cache_put(soeid, matched)
    logger.info(
        "ECM/DCM entitlement resolved for soeid=%s: effective_clause=%s",
        soeid, product_clause,
    )
    return {
        "ok": True,
        "entitled_products": matched,
        "product_clause": product_clause,
        "entitlement_source": "api",
    }
