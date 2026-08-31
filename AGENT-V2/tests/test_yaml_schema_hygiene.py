"""Every ontology YAML entry carries only KNOWN schema keys.

Observed 2026-08-31: two flow-style filter entries used UNQUOTED
descriptions containing commas — YAML silently splits at the comma and the
remainder becomes a garbage mapping key ('max 40 per in-list.': None). A
strict loader (extra='forbid') rejects the file at registry load, and every
downstream test (planner contract included) fails with it — while a lenient
environment shows nothing. This test IS the strict loader.

Runs under pytest, or standalone. Requires PyYAML only.
"""

from __future__ import annotations

import glob
import os
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

HERE = os.path.dirname(os.path.abspath(__file__))
ONTOLOGY_DIR = os.path.join(HERE, "..", "app", "bqs", "ontology")

KNOWN_KEYS = {
    "column", "operators", "description", "products", "suggestable",
    "case_insensitive", "values", "aggregation", "numeric",
    "requires_filters", "entity_id_column", "entity_name",
    "pattern_template", "fixed_codes", "list_count",
}
SECTIONS = ("filters", "dimensions", "metrics", "computed_filters")


def test_no_garbage_keys_in_any_ontology_yaml():
    if yaml is None:
        print("SKIP: PyYAML not installed")
        return
    offenders = []
    for f in sorted(glob.glob(os.path.join(ONTOLOGY_DIR, "capital_markets_*.yaml"))):
        doc = yaml.safe_load(open(f))
        for section in SECTIONS:
            for name, spec in (doc.get(section) or {}).items():
                if isinstance(spec, dict):
                    extras = set(spec) - KNOWN_KEYS
                    if extras:
                        offenders.append(
                            f"{os.path.basename(f)} {section}.{name}: {sorted(extras)}"
                        )
    assert not offenders, (
        "Unknown schema keys — usually an UNQUOTED flow-style description "
        "split at a comma (quote it): " + "; ".join(offenders)
    )


CASES = [
    ("no garbage keys in ontology yamls", test_no_garbage_keys_in_any_ontology_yaml),
]

if __name__ == "__main__":
    failed = 0
    for label, case in CASES:
        try:
            case()
            print(f"PASS {label}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {label}: {e}")
    sys.exit(1 if failed else 0)
