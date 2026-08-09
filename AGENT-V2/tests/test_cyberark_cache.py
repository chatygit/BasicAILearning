"""CyberArk secret cache — the JVM must boot once per FID per TTL, not per query.

Resolving a CyberArk FID spawns a bash script that boots a ~2 GB JVM SecretAgent.
Measured on two consecutive ECM/DCM queries: 5.5s and 7.7s, paid inside the
executor's `execute=` phase, on every single query.

These cases pin the contract that makes caching safe to keep:
  - repeated calls for one FID spawn the script ONCE
  - distinct FIDs are cached independently
  - the entry expires after CYBERARK_CACHE_TTL_SECONDS
  - a FAILED lookup is never cached (a transient failure must not pin for the
    whole TTL)
  - invalidate_secret_cache() forces a re-fetch — this is what makes a rotated
    credential recoverable before the TTL runs out
  - TTL 0 disables caching entirely
  - concurrent cold callers boot ONE JVM between them, not one each

Runs under pytest, or standalone (`python3 tests/test_cyberark_cache.py`).
No third-party packages, and the real subprocess is never invoked.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

APP = Path(__file__).parent.parent / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from utils.cyberark_integration import secrets as sec  # noqa: E402

SPAWNS: list[str] = []
SPAWN_DELAY = 0.0
SPAWN_RESULT: str | None = "s3cr3t-value"


def _fake_retrieve(fid: str, timeout_seconds: int = 30):
    """Stand-in for the bash/JVM spawn — records every real fetch."""
    SPAWNS.append(fid)
    if SPAWN_DELAY:
        time.sleep(SPAWN_DELAY)
    return SPAWN_RESULT


# Originals, captured before anything is patched. NOTHING is patched at import
# time: this module shares a process with the rest of the suite, and a global
# monkeypatch here leaks into every later test (it once made test_secrets.py
# fail with "'s3cr3t-value' != 'supersecret'"). Patch in setup, restore in
# teardown, always.
_ORIG_RUN_RETRIEVE = sec._run_retrieve_script
_ORIG_IS_LINUX = sec._is_linux


def setup_function(func=None) -> None:
    """pytest calls this per test; standalone mode calls it explicitly."""
    sec._run_retrieve_script = _fake_retrieve
    sec._is_linux = lambda: True      # the cache path is Linux-gated upstream
    reset()


def teardown_function(func=None) -> None:
    """Leave the module, the cache and the environment exactly as found."""
    sec._run_retrieve_script = _ORIG_RUN_RETRIEVE
    sec._is_linux = _ORIG_IS_LINUX
    sec.invalidate_secret_cache()
    os.environ.pop("CYBERARK_CACHE_TTL_SECONDS", None)


def reset(ttl: str = "900") -> None:
    global SPAWN_RESULT, SPAWN_DELAY
    SPAWN_RESULT, SPAWN_DELAY = "s3cr3t-value", 0.0
    SPAWNS.clear()
    sec.invalidate_secret_cache()
    os.environ["CYBERARK_CACHE_TTL_SECONDS"] = ttl


def test_repeated_calls_spawn_once():
    reset()
    got = [sec.fetch_key_with_fid("fid-a") for _ in range(3)]
    assert len(SPAWNS) == 1, f"expected 1 spawn, got {len(SPAWNS)}"
    assert got == ["s3cr3t-value"] * 3


def test_distinct_fids_cached_separately():
    reset()
    sec.fetch_key_with_fid("fid-a")
    sec.fetch_key_with_fid("fid-b")
    sec.fetch_key_with_fid("fid-a")
    assert len(SPAWNS) == 2, f"expected 2 spawns, got {len(SPAWNS)}"


def test_ttl_expiry_refetches():
    reset(ttl="1")
    sec.fetch_key_with_fid("fid-a")
    time.sleep(1.1)
    sec.fetch_key_with_fid("fid-a")
    assert len(SPAWNS) == 2, "an expired entry must be re-fetched"


def test_failure_is_never_cached():
    global SPAWN_RESULT
    reset()
    SPAWN_RESULT = None
    assert sec.fetch_key_with_fid("fid-a") is None
    assert sec.fetch_key_with_fid("fid-a") is None
    assert len(SPAWNS) == 2, "a failed lookup must retry, not be pinned for the TTL"


def test_invalidate_forces_refetch():
    reset()
    sec.fetch_key_with_fid("fid-a")
    sec.invalidate_secret_cache("fid-a")
    sec.fetch_key_with_fid("fid-a")
    assert len(SPAWNS) == 2, "invalidate_secret_cache must drop the entry"


def test_ttl_zero_disables_cache():
    reset(ttl="0")
    sec.fetch_key_with_fid("fid-a")
    sec.fetch_key_with_fid("fid-a")
    assert len(SPAWNS) == 2, "CYBERARK_CACHE_TTL_SECONDS=0 must disable caching"


def test_bad_ttl_falls_back_to_default():
    reset(ttl="not-a-number")
    assert sec._cache_ttl_seconds() == sec._DEFAULT_CACHE_TTL_SECONDS


def test_concurrent_cold_callers_spawn_once():
    global SPAWN_DELAY
    reset()
    SPAWN_DELAY = 0.25
    threads = [threading.Thread(target=sec.fetch_key_with_fid, args=("fid-a",))
               for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert len(SPAWNS) == 1, (
        f"8 concurrent cold callers booted {len(SPAWNS)} JVMs — the per-FID lock "
        f"is not collapsing the stampede"
    )


def test_empty_fid_short_circuits():
    reset()
    assert sec.fetch_key_with_fid("") is None
    assert sec.fetch_key_with_fid(None) is None
    assert not SPAWNS


CASES = [
    ("repeated calls spawn once", test_repeated_calls_spawn_once),
    ("distinct FIDs cached separately", test_distinct_fids_cached_separately),
    ("TTL expiry re-fetches", test_ttl_expiry_refetches),
    ("a FAILED lookup is never cached", test_failure_is_never_cached),
    ("invalidate forces re-fetch", test_invalidate_forces_refetch),
    ("TTL 0 disables the cache", test_ttl_zero_disables_cache),
    ("bad TTL falls back to default", test_bad_ttl_falls_back_to_default),
    ("8 concurrent cold callers -> 1 spawn", test_concurrent_cold_callers_spawn_once),
    ("empty FID short-circuits", test_empty_fid_short_circuits),
]


if __name__ == "__main__":
    print()
    failures = 0
    for label, fn in CASES:
        setup_function()
        try:
            fn()
            print(f"  ok   {label}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL {label}\n         {exc}")
        finally:
            teardown_function()
    # The suite shares a process — prove we handed the module back intact.
    if sec._run_retrieve_script is not _ORIG_RUN_RETRIEVE or sec._is_linux is not _ORIG_IS_LINUX:
        failures += 1
        print("  FAIL module left monkeypatched — later tests would see the fake")
    else:
        print("  ok   module restored (no leak into the rest of the suite)")
    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        sys.exit(1)
    print("The SecretAgent JVM boots once per FID per TTL, not once per query.")
    sys.exit(0)
