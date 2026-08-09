from __future__ import annotations

import hashlib
import logging
import os
import platform
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _normalize_cyberark_stderr(stderr_text: str) -> str:
    """Filter out non-actionable JVM noise and keep meaningful SecretAgent errors."""
    lines = [ln.strip() for ln in (stderr_text or "").splitlines() if ln.strip()]
    if not lines:
        return ""

    noise_prefixes = (
        "Picked up _JAVA_OPTIONS:",
    )
    filtered = [ln for ln in lines if not ln.startswith(noise_prefixes)]
    return " | ".join(filtered or lines)


def _masked_secret_preview(value: str, prefix: int = 2, suffix: int = 2) -> str:
    """Return a non-sensitive preview for troubleshooting logs."""
    if value is None:
        return "<none>"
    if len(value) <= (prefix + suffix):
        return "*" * len(value)
    return f"{value[:prefix]}***{value[-suffix:]}"


def _secret_fingerprint(value: str) -> str:
    """Stable non-reversible digest prefix for correlating secret values across calls."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:12]


def _normalize_secret_agent_max_memory(value: str) -> str:
    """Normalize memory to JVM-friendly unit format (e.g. 512m, 2g)."""
    raw = (value or "").strip()
    if not raw:
        return "2048m"

    if raw[-1:].lower() in {"k", "m", "g"}:
        return raw

    # Bare numeric values can be interpreted as bytes by some JVM setups.
    if raw.isdigit():
        return f"{raw}m"

    # Preserve unknown formats to avoid breaking custom runtime configurations.
    return raw


@dataclass(frozen=True)
class SecretResolution:
    value: Optional[str]
    source: str  # "env_plaintext" | "cyberark_fid" | "none"


def _is_linux() -> bool:
    return platform.system().lower() == "linux"


# ---------------------------------------------------------------------------
# Per-FID secret cache.
#
# Resolving a FID spawns a bash script that boots a ~2 GB JVM SecretAgent.
# Measured on two consecutive ECM/DCM queries: 5.5s and 7.7s, paid inside the
# executor's `execute=` phase, on EVERY query. The credential is identical each
# time, so it is cached per FID for a bounded window.
#
# Deliberate properties:
#   - only SUCCESSES are cached; a failed lookup must retry on the next call,
#     never be pinned for the whole TTL
#   - one lock per FID, so N concurrent cold callers boot ONE JVM, not N
#   - CYBERARK_CACHE_TTL_SECONDS=0 turns the cache off entirely
#
# Trade-off: a rotated credential stays stale for up to the TTL, where an
# uncached lookup would self-heal on the next query. `invalidate_secret_cache()`
# exists for that — call it when a caller sees an authentication failure.
# ---------------------------------------------------------------------------
_DEFAULT_CACHE_TTL_SECONDS = 900

_SECRET_CACHE: dict[str, tuple[float, str]] = {}
_SECRET_CACHE_LOCK = threading.Lock()
_FID_LOCKS: dict[str, threading.Lock] = {}


def _cache_ttl_seconds() -> int:
    try:
        return max(0, int(os.getenv("CYBERARK_CACHE_TTL_SECONDS",
                                    str(_DEFAULT_CACHE_TTL_SECONDS))))
    except ValueError:
        logger.warning(
            "CYBERARK_CACHE_TTL_SECONDS is not an integer; using %ds",
            _DEFAULT_CACHE_TTL_SECONDS,
        )
        return _DEFAULT_CACHE_TTL_SECONDS


def _fid_lock(fid: str) -> threading.Lock:
    with _SECRET_CACHE_LOCK:
        lock = _FID_LOCKS.get(fid)
        if lock is None:
            lock = _FID_LOCKS[fid] = threading.Lock()
        return lock


def _cached_secret(fid: str, ttl: int) -> Optional[str]:
    if not ttl:
        return None
    with _SECRET_CACHE_LOCK:
        hit = _SECRET_CACHE.get(fid)
    if not hit:
        return None
    if (time.monotonic() - hit[0]) >= ttl:
        return None
    return hit[1]


def invalidate_secret_cache(fid: Optional[str] = None) -> None:
    """Drop a cached secret — all of them when ``fid`` is None.

    Call this after an authentication failure so a rotated credential is picked
    up on the next attempt instead of waiting out the TTL.
    """
    with _SECRET_CACHE_LOCK:
        if fid is None:
            _SECRET_CACHE.clear()
            logger.info("CyberArk secret cache cleared (all FIDs)")
        elif _SECRET_CACHE.pop(fid, None) is not None:
            logger.info("CyberArk secret cache invalidated for FID '%s'", fid)


def _retrieve_script_path() -> str:
    # Override-able for container image differences
    override = os.getenv("CYBERARK_RETRIEVE_SCRIPT", "").strip()
    if override:
        return override
    return str(Path(__file__).resolve().parent / "retrieve.sh")


def _run_retrieve_script(fid: str, timeout_seconds: int = 30) -> Optional[str]:
    script_path = _retrieve_script_path()
    if not os.path.exists(script_path):
        logger.error("CyberArk retrieve script not found: %s", script_path)
        return None

    env = os.environ.copy()

    env["CYBERARK_SECRET"] = fid
    normalized_mem = _normalize_secret_agent_max_memory(
        os.getenv("SECRET_AGENT_MAX_MEMORY")
        or os.getenv("CYBERARK_SECRET_AGENT_MAX_MEMORY")
        or "2048m"
    )
    env["SECRET_AGENT_MAX_MEMORY"] = normalized_mem
    env.setdefault("CYBERARK_SECRET_AGENT_MAX_MEMORY", normalized_mem)

    try:
        proc = subprocess.run(
            ["bash", script_path],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.error("CyberArk retrieve timed out for FID '%s'", fid)
        return None
    except OSError as exc:
        logger.error("CyberArk retrieve failed to start for FID '%s': %s", fid, exc)
        return None

    if proc.returncode != 0:
        stderr_msg = _normalize_cyberark_stderr(proc.stderr or "")
        logger.error(
            "CyberArk retrieve failed for FID '%s' (rc=%s): %s",
            fid,
            proc.returncode,
            stderr_msg,
        )
        return None

    # SecretAgent may output informational lines before the secret.
    # Use the final stdout line as the secret while preserving whitespace
    # inside that line.
    stdout = proc.stdout or ""
    if not stdout.strip():
        logger.error("CyberArk returned empty output for FID '%s'", fid)
        return None

    lines = stdout.splitlines()
    if len(lines) > 1:
        logger.warning(
            "CyberArk stdout contained %d lines; using last line as secret payload",
            len(lines),
        )
    secret = lines[-1] if lines else stdout.rstrip("\r\n")

    logger.info("CyberArk lookup succeeded for FID '%s' (len=%d)", fid, len(secret))
    return secret


def fetch_key_with_fid(fid: Optional[str]) -> Optional[str]:
    """Resolve secret from CyberArk FID. Linux-only by design.

    Cached per FID — see the cache block above. Only the JVM spawn is skipped on
    a hit; every caller still gets the same value it would have got.
    """
    logger.info(
        "CyberArk fetch_key_with_fid called (has_fid=%s, linux=%s)",
        bool(fid),
        _is_linux(),
    )
    if not fid:
        logger.warning("CyberArk fetch skipped: empty FID")
        return None
    if not _is_linux():
        logger.warning("CyberArk fetch skipped on non-Linux runtime for FID '%s'", fid)
        return None

    ttl = _cache_ttl_seconds()
    cached = _cached_secret(fid, ttl)
    if cached is not None:
        logger.info("CyberArk cache HIT for FID '%s' (ttl=%ds)", fid, ttl)
        return cached

    # One lock per FID: concurrent cold callers wait for a single JVM boot
    # instead of each spawning their own.
    with _fid_lock(fid):
        cached = _cached_secret(fid, ttl)
        if cached is not None:
            logger.info("CyberArk cache HIT for FID '%s' (after wait)", fid)
            return cached

        logger.info("CyberArk fetch starting for FID '%s'", fid)
        secret = _run_retrieve_script(fid)
        if secret and ttl:
            # Only successes are cached — a failure must retry next call.
            with _SECRET_CACHE_LOCK:
                _SECRET_CACHE[fid] = (time.monotonic(), secret)
        return secret


def resolve_secret(
    *,
    plaintext_env: str,
    fid_env: str,
    required: bool = False,
    allow_plaintext_fid_fallback: bool = False,
) -> SecretResolution:
    """
    Resolution order:
      1) plaintext env
      2) CyberArk lookup using fid_env
      3) optional fid_env-as-secret fallback (for local/dev)
    """
    plain = os.getenv(plaintext_env, "").strip()
    fid = os.getenv(fid_env, "").strip()

    logger.info(
        "Secret resolve request: plaintext_env=%s(has_value=%s) fid_env=%s(has_value=%s) linux=%s required=%s",
        plaintext_env,
        bool(plain),
        fid_env,
        bool(fid),
        _is_linux(),
        required,
    )

    if plain:
        logger.info("Secret resolved from plaintext env: %s", plaintext_env)
        return SecretResolution(value=plain, source="env_plaintext")

    if fid:
        logger.info("Attempting CyberArk lookup using FID from %s", fid_env)
        resolved = fetch_key_with_fid(fid)
        if resolved:
            logger.info("Secret resolved via CyberArk FID from %s", fid_env)
            logger.info(
                "Resolved secret diagnostics: len=%d preview=%s sha256_prefix=%s",
                len(resolved),
                _masked_secret_preview(resolved),
                _secret_fingerprint(resolved),
            )
            return SecretResolution(value=resolved, source="cyberark_fid")
        if allow_plaintext_fid_fallback:
            # Optional compatibility mode where fid_env may directly hold secret.
            logger.warning(
                "CyberArk lookup failed; using plaintext FID fallback from %s",
                fid_env,
            )
            return SecretResolution(value=fid, source="env_plaintext")

    if required:
        logger.error(
            "Secret resolution failed: missing %s and unresolved %s",
            plaintext_env,
            fid_env,
        )
        raise ValueError(
            f"Missing secret: set {plaintext_env} or configure CyberArk via {fid_env}"
        )

    logger.info("Secret resolution returned none for %s/%s", plaintext_env, fid_env)
    return SecretResolution(value=None, source="none")
