"""Request corpus: every doctrine recipe and every catalog example must PLAN and
COMPILE through the real planner, and the SQL must not drift unnoticed.

Why this exists (RT-2, analysis 2026-09-17): none of the recent failure classes
had a pre-deploy catch. Doctrine named fields that do not exist (investor_gp_id,
pricing_ts), a SKILL row prescribed a request shape the catalog contradicted,
and no planner-backed proof of any recipe or yaml example existed. This file:

  Part A — plans + compiles every `examples[].request` body in every catalog.
  Part B — plans + compiles the canonical request bodies behind the QA prompts
           that failed on UAT, and snapshots their SQL in tests/golden_sql/.
           A golden mismatch is a FINDING (an ontology or planner change
           altered the SQL an existing flow produces); regenerate deliberately
           with BQS_UPDATE_GOLDEN=1 after reading the diff.

Runs under pytest, or standalone (`python3 tests/test_request_corpus.py`).
Without pydantic/yaml the cases SKIP LOUDLY — and the gate now treats a SKIP as
a failure, so run it with the interpreter that passes pytest.
"""

from __future__ import annotations

import difflib
import os
import sys
from pathlib import Path

APP = Path(__file__).parent.parent / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

ONT = APP / "bqs" / "ontology"
GOLDEN = Path(__file__).parent / "golden_sql"

SKIPPED: list[str] = []


def _deps() -> bool:
    try:
        import pydantic  # noqa: F401
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True


def _registry():
    from bqs.ontology import OntologyRegistry

    return OntologyRegistry(str(ONT))


def _compile(reg, body: dict) -> str:
    """Validate → plan → build SQL → read-only check. Returns the SQL text."""
    from bqs.dialects.trino import TrinoDialect
    from bqs.models import BQSRequest
    from bqs.planner import plan_query
    from bqs.sql_builder import build_sql
    from bqs.sql_validator import assert_read_only

    req = BQSRequest.model_validate(body)
    plan = plan_query(req, reg.get(body["source"]))
    sql = build_sql(plan, TrinoDialect()).sql
    assert_read_only(sql)
    return sql


# --------------------------------------------------------------------------
# Part A — every catalog example plans and compiles
# --------------------------------------------------------------------------

def _yaml_examples():
    import yaml

    out = []
    for path in sorted(ONT.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        for i, ex in enumerate(doc.get("examples") or []):
            body = ex.get("request")
            if body:
                out.append((path.name, i, ex.get("question", ""), body))
    return out


def test_every_catalog_example_plans_and_compiles():
    if not _deps():
        SKIPPED.append("catalog examples (pydantic/yaml not installed)")
        return
    reg = _registry()
    examples = _yaml_examples()
    assert examples, "no examples found under app/bqs/ontology — the catalogs lost their examples"
    failures = []
    for fname, i, question, body in examples:
        try:
            _compile(reg, body)
        except Exception as e:  # noqa: BLE001 — every failure is reported
            failures.append(f"{fname} example #{i} ({question[:60]!r}): {type(e).__name__}: {str(e)[:160]}")
    assert not failures, "catalog examples that no longer plan/compile:\n  " + "\n  ".join(failures)


# --------------------------------------------------------------------------
# Part B — canonical recipe bodies behind the QA prompts, with golden SQL
# --------------------------------------------------------------------------

CORPUS: dict[str, dict] = {
    # QA 22 — one order-object query with product_class, no deal sample.
    "ig_2024_top5_allocation": {
        "source": "capital_markets_order",
        "metric": "total_allocation",
        "dimensions": ["investor_name", "investor_id", "currency"],
        "filters": [
            {"field": "product", "op": "eq", "value": "DCM"},
            {"field": "product_class", "op": "like", "value": "%Investment Grade%"},
            {"field": "pricing_date", "op": "gte", "value": "2024-01-01"},
            {"field": "pricing_date", "op": "lt", "value": "2025-01-01"},
        ],
        "order": [{"field": "total_allocation", "direction": "desc"},
                  {"field": "investor_name", "direction": "asc"}],
        "limit": 5,
    },
    # QA 16 / TC1 — the ORDERBOOK MATRIX: top 5 per tranche AND per deal on one
    # transaction (a transaction can map to several deals), both figures.
    "txn_top5_per_tranche_matrix": {
        "source": "capital_markets_order",
        "metric": "row_count",
        "dimensions": ["investor_name", "investor_id", "transaction_id", "deal_id",
                       "deal_name", "pricing_date", "tranche_name", "order_demand_qty",
                       "order_allocation", "currency"],
        "filters": [
            {"field": "product", "op": "eq", "value": "DCM"},
            {"field": "transaction_id", "op": "eq", "value": "75043505"},
        ],
        "partition_by": ["deal_id", "tranche_name"],
        "per_partition_limit": 5,
        "order": [{"field": "order_demand_qty", "direction": "desc"},
                  {"field": "investor_name", "direction": "asc"}],
    },
    # QA 18 — a deal-name ask with no product word: both products in, product
    # projected, ONE query (never guess ECM first).
    "deal_name_ask_product_unknown": {
        "source": "capital_markets_order",
        "metric": "total_demand",
        "dimensions": ["investor_name", "investor_id", "product"],
        "filters": [
            {"field": "product", "op": "in", "value": ["ECM", "DCM"]},
            {"field": "deal_name", "op": "like", "value": "%TRAVELERS%"},
        ],
        "order": [{"field": "total_demand", "direction": "desc"}],
        "limit": 5,
    },
    # QA 2 step 1 — a ranking that feeds an orderbook drill-down: named, booked.
    "largest_ipos_named_booked": {
        "source": "capital_markets_deal",
        "metric": "row_count",
        "dimensions": ["deal_name", "deal_id", "deal_size", "investor_count"],
        "filters": [
            {"field": "product", "op": "eq", "value": "ECM"},
            {"field": "offering_type", "op": "like", "value": "%IPO%"},
            {"field": "investor_count", "op": "gte", "value": 1},
            {"field": "deal_name", "op": "is_not_null"},
            {"field": "last_priced", "op": "gte", "value": "2026-01-01"},
        ],
        "order": [{"field": "deal_size", "direction": "desc"}],
        "limit": 5,
    },
    # QA 2 step 2 — N deals × top investors = ONE partitioned request.
    "ipo_drilldown_top5_per_deal": {
        "source": "capital_markets_order",
        "metric": "row_count",
        "dimensions": ["deal_name", "deal_id", "investor_name", "investor_id",
                       "order_demand_qty", "order_allocation"],
        "filters": [
            {"field": "product", "op": "eq", "value": "ECM"},
            {"field": "deal_id", "op": "in", "value": ["75063863", "75067049"]},
        ],
        "partition_by": ["deal_id"],
        "per_partition_limit": 5,
        "order": [{"field": "order_allocation", "direction": "desc"}],
    },
    # QA 17 — "did <investor> indicate in txn X": order object, txn id, name stem.
    "indicated_in_txn_named_investor": {
        "source": "capital_markets_order",
        "metric": "row_count",
        "dimensions": ["investor_name", "investor_id", "tranche_name", "order_demand_qty",
                       "demand_as_submitted", "demand_unit", "order_allocation"],
        "filters": [
            {"field": "product", "op": "eq", "value": "DCM"},
            {"field": "transaction_id", "op": "eq", "value": "75043505"},
            {"field": "investor_name", "op": "like", "value": "%AMUNDI%"},
        ],
    },
    # QA 15 — the investor-given matrix over six months.
    "investor_matrix_6m": {
        "source": "capital_markets_order",
        "metric": "row_count",
        "dimensions": ["investor_name", "issuer_name", "pricing_date", "deal_name", "tenors",
                       "tranche_name", "order_demand_qty", "order_allocation", "currency"],
        "filters": [
            {"field": "product", "op": "eq", "value": "DCM"},
            {"field": "investor_name", "op": "like", "value": "%FIDELITY%"},
            {"field": "pricing_date", "op": "gte", "value": "2026-03-17"},
            {"field": "pricing_date", "op": "lt", "value": "2026-09-18"},
        ],
        "order": [{"field": "issuer_name", "direction": "asc"},
                  {"field": "pricing_date", "direction": "desc"}],
        "limit": 200,
    },
    # QA 25 — allowed order types per tranche of a transaction.
    "allowed_order_types_per_tranche": {
        "source": "capital_markets_tranche",
        "metric": "row_count",
        "dimensions": ["tranche_name", "tenors", "allowed_order_spread",
                       "allowed_order_yield", "allowed_order_max_price"],
        "filters": [
            {"field": "product", "op": "eq", "value": "DCM"},
            {"field": "transaction_id", "op": "eq", "value": "75043505"},
        ],
    },
    # SKILL §6 — investors never allocated despite placing orders: having eq 0.
    "never_allocated_having": {
        "source": "capital_markets_order",
        "metric": "total_allocation",
        "dimensions": ["investor_name", "investor_id"],
        "filters": [
            {"field": "product", "op": "eq", "value": "DCM"},
            {"field": "pricing_date", "op": "gte", "value": "2025-01-01"},
            {"field": "pricing_date", "op": "lt", "value": "2026-01-01"},
        ],
        "having": [{"metric": "total_allocation", "op": "eq", "value": 0}],
        "limit": 50,
    },
}


def _golden_check(name: str, sql: str) -> str | None:
    """Return a failure message, or None. Writes the golden when absent or when
    BQS_UPDATE_GOLDEN=1 (deliberate regeneration after reading the diff)."""
    GOLDEN.mkdir(exist_ok=True)
    path = GOLDEN / f"{name}.sql"
    if not path.exists() or os.environ.get("BQS_UPDATE_GOLDEN") == "1":
        path.write_text(sql + "\n")
        return None
    expected = path.read_text().rstrip("\n")
    if expected == sql:
        return None
    diff = "\n".join(difflib.unified_diff(expected.splitlines(), sql.splitlines(),
                                          fromfile=f"golden/{name}.sql", tofile="now", lineterm=""))
    return f"{name}: generated SQL changed — a doctrine/ontology/planner change altered an existing flow. " \
           f"Read the diff, then BQS_UPDATE_GOLDEN=1 if intended.\n{diff}"


def test_recipe_corpus_plans_compiles_and_matches_golden():
    if not _deps():
        SKIPPED.append("recipe corpus (pydantic/yaml not installed)")
        return
    reg = _registry()
    failures = []
    for name, body in CORPUS.items():
        try:
            sql = _compile(reg, body)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{name}: does not plan/compile — {type(e).__name__}: {str(e)[:200]}")
            continue
        msg = _golden_check(name, sql)
        if msg:
            failures.append(msg)
    assert not failures, "\n\n".join(failures)


def test_corpus_bodies_only_name_catalog_keys():
    """Cheap, dependency-free: every field named in the corpus is a key of its
    object's catalog (the failure class that produced investor_gp_id/pricing_ts)."""
    import re

    for name, body in CORPUS.items():
        src = (ONT / f"{body['source']}.yaml").read_text()
        keys = set(re.findall(r"^  ([a-z_0-9]+):", src, re.M))
        named = set(body.get("dimensions", [])) | {f["field"] for f in body.get("filters", [])} \
            | set(body.get("partition_by", [])) | {o["field"] for o in body.get("order", [])} \
            | {body["metric"]} | {h["metric"] for h in body.get("having", [])}
        missing = sorted(named - keys)
        assert not missing, f"{name}: names not in {body['source']}.yaml: {missing}"


if __name__ == "__main__":
    ok = True
    for fn in (test_every_catalog_example_plans_and_compiles,
               test_recipe_corpus_plans_compiles_and_matches_golden,
               test_corpus_bodies_only_name_catalog_keys):
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as e:
            ok = False
            print(f"  FAIL {fn.__name__}\n{e}")
    for note in SKIPPED:
        print(f"  SKIP {note}")
    if SKIPPED and os.environ.get("BQS_REQUIRE_PLANNER") == "1":
        ok = False
    print("\nEvery recipe and example plans, compiles, and produces the SQL it did yesterday."
          if ok else "\nCorpus FAILED.")
    sys.exit(0 if ok else 1)
