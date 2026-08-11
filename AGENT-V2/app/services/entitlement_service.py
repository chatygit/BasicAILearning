"""ECM/DCM product entitlement — resolves which of ECM / DCM a SOEID may see.

`perform_initial_entitlement_check` is the entry point every caller should use:
it owns the cache, the failure taxonomy and the user-facing messages.
`get_entitled_products` is the raw, uncached API fetch underneath it — calling it
directly costs a live HTTP round trip and gives up the stale-scope fallback.

CACHING
    One entry per SOEID, fresh for ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS
    (default 300). Expired entries are KEPT as last-known-good: if the API is
    down, an active session keeps its existing scope instead of being told it has
    no access. That fallback is bounded by
    ECM_DCM_ENTITLEMENT_STALE_MAX_AGE_SECONDS (default 3600) so a revocation
    still takes effect within the hour even through a sustained outage.
    Set the TTL to 0 to disable caching entirely.

FAILURE TAXONOMY — the distinction matters, because the two are not the same
incident and must not produce the same advice:
    ValueError   -> misconfiguration (missing URL / policy id). Not retryable,
                    and NEVER served from stale cache: if the deployment is
                    wrong we must not keep answering from a scope we can no
                    longer verify.
    RuntimeError -> the API was reachable-ish but did not give us an answer
                    (non-200, connection error, timeout, unparseable body).
                    Retryable, and stale-eligible.

`reason` is a STABLE SLUG, never free text. mcpserver's `_entitlement_gate`
copies it straight into the agent-facing error `code`, so putting an exception
string there would ship upstream response bodies to the model and out to the
user. Detail belongs in the log; the slug goes on the wire.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_ALLOWED_PRODUCTS: tuple[str, ...] = ("ECM", "DCM")

_DEFAULT_CACHE_TTL_SECONDS = 300.0
_DEFAULT_STALE_MAX_AGE_SECONDS = 3600.0

# Bounded so a long-lived pod that serves many users cannot grow this without
# limit. Eviction is oldest-first; entitlement is cheap to re-fetch.
_CACHE_MAX_ENTRIES = 2000

# soeid_key -> (fetched_at_monotonic, products)
_CACHE: Dict[str, Tuple[float, List[str]]] = {}
_CACHE_LOCK = threading.Lock()

# One lock per SOEID so N concurrent cold requests for the same user make ONE
# API call between them rather than N. Without it, a burst at session start
# multiplies the slowest dependency in the request path.
_SOEID_LOCKS: Dict[str, threading.Lock] = {}
_SOEID_LOCKS_GUARD = threading.Lock()

# Built once. The previous code constructed a Session per call, which threw away
# the connection pool it had just configured and paid a fresh TCP + TLS
# handshake on every query.
_SESSION: Optional[requests.Session] = None
_SESSION_LOCK = threading.Lock()


def _cache_ttl_seconds() -> float:
    try:
        return float(os.getenv("ECM_DCM_ENTITLEMENT_CACHE_TTL_SECONDS", "300"))
    except ValueError:
        return _DEFAULT_CACHE_TTL_SECONDS


def _stale_max_age_seconds() -> float:
    try:
        return float(os.getenv("ECM_DCM_ENTITLEMENT_STALE_MAX_AGE_SECONDS", "3600"))
    except ValueError:
        return _DEFAULT_STALE_MAX_AGE_SECONDS


def _request_timeout_seconds() -> float:
    try:
        return float(os.getenv("ECM_DCM_ENTITLEMENT_TIMEOUT_SECONDS", "30"))
    except ValueError:
        return 30.0


def _cache_key(soeid: str) -> str:
    """SOEIDs identify a person, not a spelling — fold case so 'BK42867' and
    'bk42867' share one entry. The ORIGINAL string is what goes to the API."""
    return (soeid or "").strip().lower()


def _cache_get_fresh(key: str) -> Optional[List[str]]:
    ttl = _cache_ttl_seconds()
    if ttl <= 0:
        return None
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
    if not entry:
        return None
    fetched_at, products = entry
    if (time.monotonic() - fetched_at) >= ttl:
        return None
    return list(products)


def _cache_get_stale(key: str) -> Optional[Tuple[List[str], float]]:
    """Last known-good scope regardless of TTL, as (products, age_seconds)."""
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
    if not entry:
        return None
    fetched_at, products = entry
    age = time.monotonic() - fetched_at
    if age > _stale_max_age_seconds():
        return None
    return list(products), age


def _cache_put(key: str, products: List[str]) -> None:
    if _cache_ttl_seconds() <= 0:
        return
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), list(products))
        if len(_CACHE) > _CACHE_MAX_ENTRIES:
            oldest = min(_CACHE, key=lambda k: _CACHE[k][0])
            _CACHE.pop(oldest, None)


def clear_entitlement_cache(soeid: Optional[str] = None) -> None:
    """Drop cached scope — for tests, and for ops after an entitlement change
    that must take effect before the TTL runs out."""
    with _CACHE_LOCK:
        if soeid:
            _CACHE.pop(_cache_key(soeid), None)
        else:
            _CACHE.clear()


def _soeid_lock(key: str) -> threading.Lock:
    with _SOEID_LOCKS_GUARD:
        # Locks are tiny but the dict is keyed by an unbounded value, so cap it.
        # Dropping them is safe: the only cost of losing a lock is that a
        # concurrent pair might both fetch once.
        if len(_SOEID_LOCKS) > _CACHE_MAX_ENTRIES * 2:
            _SOEID_LOCKS.clear()
        lock = _SOEID_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SOEID_LOCKS[key] = lock
        return lock


def _build_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(total=2, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(pool_connections=5, pool_maxsize=10, max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        with _SESSION_LOCK:
            if _SESSION is None:
                _SESSION = _build_session()
    return _SESSION


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


def _extract_products_from_clause_list(clauses: Any) -> list[str]:
    """Pull ECM/DCM out of a list of clauses, each a string or an object."""
    if not isinstance(clauses, list):
        return []
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


def _describe_shape(data: Any, depth: int = 0) -> str:
    """Structure of a response WITHOUT its values — safe to log anywhere.

    An empty product list is indistinguishable from a parse miss, and the parser
    below recognises about ten key spellings. When it finds none of them the
    useful question is 'what shape DID the API return', and the keys answer that
    without putting entitlement data in the log.
    """
    if isinstance(data, dict):
        if depth >= 2:
            return "{…}"
        inner = ", ".join(
            f"{k}: {_describe_shape(v, depth + 1)}" for k, v in list(data.items())[:12]
        )
        return "{" + inner + "}"
    if isinstance(data, list):
        if depth >= 2:
            return "[…]"
        head = _describe_shape(data[0], depth + 1) if data else ""
        return f"[{len(data)} x {head}]" if data else "[]"
    return type(data).__name__


def build_product_in_clause(products: list[str]) -> str:
    entitled = [p for p in _ALLOWED_PRODUCTS if p in set(products)]
    if not entitled:
        return ""
    if len(entitled) == 1:
        return f"PRODUCT = '{entitled[0]}'"
    values = ", ".join(f"'{p}'" for p in entitled)
    return f"PRODUCT IN ({values})"


def get_entitled_products(soeid: str) -> list[str]:
    """RAW fetch — no caching. Callers wanting the cache and the stale-scope
    fallback go through perform_initial_entitlement_check.

    Raises:
        ValueError:   the entitlement API is not configured.
        RuntimeError: it is configured but did not return a usable answer.
    """
    url = os.getenv("ECM_DCM_PRODUCT_ENTITLEMENT_URL", "").strip()
    policy_id = os.getenv("ECM_DCM_ENTITLEMENT_POLICY_ID", "").strip()

    if not url or not policy_id:
        raise ValueError(
            "Missing ECM/DCM entitlement API settings. "
            "Ensure ECM_DCM_PRODUCT_ENTITLEMENT_URL and "
            "ECM_DCM_ENTITLEMENT_POLICY_ID are configured."
        )

    payload = {
        "policyId": policy_id,
        "soeid": soeid,
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-citiportal-loginid": soeid,
    }

    logger.info(
        "ECM/DCM entitlement API POST %s (policyId=%s, soeid=%s)", url, policy_id, soeid
    )
    try:
        response = _get_session().post(
            url,
            json=payload,
            headers=headers,
            timeout=_request_timeout_seconds(),
            verify=_resolve_ssl_verify(),
        )
    except requests.RequestException as exc:
        # A connection error or timeout is an OSError, NOT a RuntimeError, so
        # this used to escape the caller's handler entirely and surface as an
        # unhandled tool crash instead of a governed "try again" message.
        raise RuntimeError(f"ECM/DCM entitlement API unreachable: {exc}") from exc

    if response.status_code != 200:
        logger.warning(
            "ECM/DCM entitlement API non-200 (HTTP %s) for soeid=%s",
            response.status_code,
            soeid,
        )
        raise RuntimeError(
            "ECM/DCM entitlement API request failed "
            f"(HTTP {response.status_code}): {response.text[:500]}"
        )

    logger.info("ECM/DCM entitlement API HTTP 200 for soeid=%s", soeid)
    try:
        data = response.json()
    except ValueError as exc:
        # requests' JSONDecodeError subclasses ValueError, which is the
        # misconfiguration signal — so a 200 carrying a proxy's HTML error page
        # used to be reported to the user as "contact support, the service is
        # misconfigured". It is a transient upstream failure; say so.
        raise RuntimeError(
            f"ECM/DCM entitlement API returned an unparseable body: {exc}"
        ) from exc

    products = _parse_entitlement_response(data)
    if not products:
        # An empty list and a parse miss look identical to the caller, and the
        # difference decides whether you call the entitlements team or fix a
        # key name here. Shape only — no values.
        logger.warning(
            "ECM/DCM entitlement API returned NO ECM/DCM products for soeid=%s. "
            "Response shape: %s",
            soeid,
            _describe_shape(data),
        )
        if os.getenv("ECM_DCM_ENTITLEMENT_DEBUG_BODY", "").strip().lower() in {
            "1", "true", "yes",
        }:
            logger.warning(
                "ECM/DCM entitlement raw body (ECM_DCM_ENTITLEMENT_DEBUG_BODY): %s",
                response.text[:2000],
            )
    return products


def _parse_entitlement_response(data: Any) -> list[str]:
    """Map an entitlement API response onto ['ECM'] / ['DCM'] / both.

    Deliberately NARROW. This function decides what a person is allowed to see,
    so every extra branch is another way to read a grant that was never issued —
    `_extract_products_from_clause` regex-matches ECM/DCM anywhere in a string,
    which is safe over a field the API means as a clause and unsafe over
    arbitrary text. Only shapes this API is KNOWN to return are handled.

    Verified against the QAT policy backend 2026-08-09: a SOEID with a grant
    parses here; a SOEID without one returns nothing and is correctly denied.
    Speculative handling for top-level arrays and gateway envelopes was tried
    and removed once the API was observed working — when nothing parses, the
    `Response shape:` warning in the caller says so, and the shape is the thing
    that tells you whether to add a branch or call the entitlements team.
    """
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
    return _extract_products_from_clause_list(clauses)


def _granted(soeid: str, products: List[str], source: str) -> Dict[str, Any]:
    """Build the success payload and log the one line that answers 'what is this
    user entitled to' — grep GRANTED."""
    matched = [p for p in products if p in set(_ALLOWED_PRODUCTS)]
    product_clause = build_product_in_clause(matched)
    logger.info(
        "ECM/DCM entitlement gate GRANTED for soeid=%s: products=%s clause=%s source=%s",
        soeid,
        matched,
        product_clause,
        source,
    )
    return {
        "ok": True,
        "entitled_products": matched,
        "product_clause": product_clause,
        "entitlement_source": source,
    }


def perform_initial_entitlement_check(
    soeid: Optional[str],
    conversation_id: Optional[str] = None,
    entitlement_enabled: bool = True,
) -> Dict[str, Any]:
    """Validate ECM/DCM product entitlements before any downstream actions."""
    del conversation_id

    logger.info(
        "ECM/DCM entitlement gate invoked (enabled=%s, soeid_present=%s)",
        entitlement_enabled,
        bool(soeid),
    )

    if not entitlement_enabled:
        logger.info(
            "ECM_DCM_ENTITLEMENT_FEATURE_FLAG disabled - skipping gate; granting ECM+DCM"
        )
        default_products = list(_ALLOWED_PRODUCTS)
        return {
            "ok": True,
            "entitled_products": default_products,
            "product_clause": build_product_in_clause(default_products),
            "entitlement_check_skipped": True,
        }

    if not soeid:
        logger.warning("ECM/DCM entitlement gate DENIED: reason=missing_soeid")
        return {
            "ok": False,
            "reason": "missing_soeid",
            "retryable": False,
            "user_message": (
                "I'm unable to verify your ECM/DCM access entitlements because no "
                "user identifier was provided. Please re-authenticate and try again."
            ),
        }

    key = _cache_key(soeid)

    cached = _cache_get_fresh(key)
    if cached:
        return _granted(soeid, cached, "cache")

    # Cold. Take the per-SOEID lock so a burst collapses to one API call, then
    # re-check: whoever we queued behind has almost certainly just filled it.
    with _soeid_lock(key):
        cached = _cache_get_fresh(key)
        if cached:
            return _granted(soeid, cached, "cache")

        t0 = time.perf_counter()
        try:
            entitled_products = get_entitled_products(soeid)
        except ValueError as exc:
            # Misconfiguration. Retrying will not fix it, and we must NOT serve a
            # stale scope we can no longer verify.
            logger.error(
                "ECM/DCM entitlement MISCONFIGURED for soeid=%s after %.1fms: %s",
                soeid,
                (time.perf_counter() - t0) * 1000,
                exc,
                exc_info=True,
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
        except Exception as exc:  # noqa: BLE001 - RuntimeError plus anything unforeseen
            # run_bqs_query has no exception handler of its own, so anything that
            # escapes here reaches the agent as a raw tool crash instead of a
            # governed message. Nothing gets out.
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.error(
                "ECM/DCM entitlement API FAILED for soeid=%s after %.1fms: %s",
                soeid,
                elapsed_ms,
                exc,
                exc_info=True,
            )
            stale = _cache_get_stale(key)
            if stale:
                products, age = stale
                logger.warning(
                    "ECM/DCM entitlement using STALE cached scope for soeid=%s "
                    "after API failure (age=%.0fs, products=%s)",
                    soeid,
                    age,
                    products,
                )
                return _granted(soeid, products, "cache_fallback")
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

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "ECM/DCM entitlement API replied in %.1fms for soeid=%s (raw products: %s)",
            elapsed_ms,
            soeid,
            entitled_products,
        )

        matched = [p for p in entitled_products if p in set(_ALLOWED_PRODUCTS)]
        if not matched:
            logger.info(
                "ECM/DCM entitlement gate DENIED for soeid=%s: "
                "reason=no_capital_markets_entitlement (raw entitled list: %s).",
                soeid,
                entitled_products,
            )
            return {
                "ok": False,
                "reason": "no_capital_markets_entitlement",
                "retryable": False,
                "user_message": (
                    "You don't have entitlements to access ECM or DCM data. "
                    "Please contact your administrator or the entitlements team "
                    "to request access to Equity Capital Markets (ECM) and/or "
                    "Debt Capital Markets (DCM) data."
                ),
            }

        # Cache the FILTERED list, so the cached scope and the clause derived
        # from it can never diverge.
        _cache_put(key, matched)
        return _granted(soeid, matched, "api")
