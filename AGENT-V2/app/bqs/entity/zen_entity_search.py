"""Zen entity search — company/GFCID resolution + revenue-access entitlement.

Ported from the nl2sql-server ``src/app/text2sql/utilities/api_client.py``.
Flow:
    1. zen-client ``/client?searchText=...`` (by gfcid when supplied, else name).
    2. Collect all gfcIds from the response.
    3. zen-coverage data-checker to determine revenue access.
    4. Return the client records whose gfcId has revenue access.

``CLIENT_KEY`` follows the interaction-api CyberArk pattern: the env var holds a
CyberArk nickname, and the real secret is resolved at runtime via
``fetch_key_with_fid``.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from middleware.soeid_middleware import get_soeid
from utils.cyberark_integration.secrets import fetch_key_with_fid

load_dotenv()

logger = logging.getLogger(__name__)

_session: requests.Session | None = None


def _build_session() -> requests.Session:
    session = requests.Session()
    retry_strategy = Retry(total=2, backoff_factor=0.5, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(pool_connections=5, pool_maxsize=10, max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = _build_session()
    return _session


def _resolve_ssl_verify() -> Any:
    """Return the appropriate SSL verification value."""
    ssl_cert = os.getenv("SSL_CERT_FILE")
    if ssl_cert:
        return ssl_cert
    if os.getenv("DISABLE_SSL_VERIFY", "").lower() == "true":
        return False
    return True

# SECURITY: _resolve_ssl_verify() is DEAD CODE — nothing calls it. Both zen
# calls below hardcode `verify=False`, so TLS certificates are never validated
# on requests that carry the caller's SOEID and the x-IBM-client-Secret. The
# helper already computes the right value (SSL_CERT_FILE > DISABLE_SSL_VERIFY >
# True); the fix is to pass `verify=_resolve_ssl_verify()` at both call sites.


def _build_zen_headers(soeid: str) -> dict[str, str]:
    """Build headers for zen-client / zen-coverage calls.

    ``CLIENT_KEY`` holds a CyberArk nickname; the real secret is resolved at
    runtime. Falls back to the raw env value when CyberArk is unavailable
    (e.g. local dev, where ``fetch_key_with_fid`` returns None).
    """
    client_id = os.environ.get("CLIENT_ID", "")
    client_key_nickname = os.environ.get("CLIENT_SECRET", "")
    client_secret = fetch_key_with_fid(client_key_nickname) or client_key_nickname
    return {
        "Content-Type": "application/json",
        "SOEID": soeid,
        "x-IBM-client-Id": client_id,
        "x-IBM-client-Secret": client_secret,
    }


def _call_zen_client_search(
    zen_client_url: str, search_text: str, headers: dict[str, str]
) -> list:
    params = {
        "searchText": search_text,
        "limit": "1000000",
        "pagesize": "1000000",
    }
    logger.info("Calling zen-client API with searchText='%s'", search_text)
    start = time.time()
    resp = _get_session().get(
        zen_client_url, params=params, headers=headers, verify=False, timeout=60
    )
    logger.info(
        "[perf] zen-client API call in %.2fs (status=%d)",
        time.time() - start,
        resp.status_code,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"zen-client API call failed (HTTP {resp.status_code}): {resp.text[:200]}"
        )
    return resp.json().get("clients", [])


def _call_zen_coverage_data_checker(
    zen_coverage_url: str, soeid: str, gfcid_list: list, headers: dict[str, str]
) -> list:
    payload = {"soeId": soeid, "gfcIds": gfcid_list}
    logger.info("Calling zen-coverage data-checker with %d gfcIds", len(gfcid_list))
    start = time.time()
    resp = _get_session().post(
        zen_coverage_url, json=payload, headers=headers, verify=False, timeout=60
    )
    logger.info(
        "[perf] zen-coverage data-checker call in %.2fs (status=%d)",
        time.time() - start,
        resp.status_code,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"zen-coverage API call failed (HTTP {resp.status_code}): {resp.text[:200]}"
        )
    return [str(g) for g in resp.json().get("revenueAccess", [])]


def zen_entity_search(
    entity_name: str = "",
    gfcid: str = "",
    soeid: str = "",
) -> list:
    """Search clients via zen-client, then filter by revenue access via zen-coverage.

    Returns the raw zen-client records whose gfcId has revenue access. Mapping to
    the BQS row shape is handled by the caller.
    """
    if not soeid:
        soeid = get_soeid()
    if not soeid:
        raise ValueError(
            "SOEID is required for entity search but could not be resolved "
            "from the request context."
        )
    soeid = soeid.upper()

    zen_client_url = os.environ.get("ZEN_CLIENT_SEARCH_URL", "")
    zen_coverage_url = os.environ.get("ZEN_COVERAGE_DATA_CHECKER_URL", "")

    search_text = gfcid.strip() if gfcid and gfcid.strip() else entity_name.strip()
    if not search_text:
        return []

    if not zen_client_url or not zen_coverage_url:
        raise ValueError("Zen client/coverage URL not configured")

    headers = _build_zen_headers(soeid)

    clients = _call_zen_client_search(zen_client_url, search_text, headers)
    if not clients:
        return []

    gfcid_list = [str(c["gfcId"]) for c in clients if c.get("gfcId")]
    if not gfcid_list:
        return []

    revenue_access_gfcids = set(
        _call_zen_coverage_data_checker(zen_coverage_url, soeid, gfcid_list, headers)
    )
    logger.info("Revenue access granted for %d gfcIds", len(revenue_access_gfcids))

    return [c for c in clients if str(c.get("gfcId", "")) in revenue_access_gfcids]

# NOTE: this module serves ONLY the `revenue_returns_entities` source. The four
# ECM/DCM objects never reach it — `capital_markets_entity` resolves through SQL against
# VW_ENTITY_SEARCH. So the latency here (two sequential calls, 60s timeout each)
# is not on the ECM/DCM path, but the TLS issue above is in a server we own.
