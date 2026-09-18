"""Catalog ↔ view contract: what a catalog says a column is must match what the
view actually projects, per product branch.

Why this exists (RT-3 / XL-4, analysis 2026-09-17): a yaml `column:` that the
view does not project fails at query time with a Trino "cannot be resolved";
a field declared for both products but CAST(NULL) on one branch returns a
silent zero for that product; a field declared for one product while the view
fills it on both is a false rejection (product_not_applicable). Nothing checked
this before — the gate only pinned remembered names.

Pure text: no pydantic needed (PyYAML only, and the file falls back to a regex
key scan without it). The view parser mirrors the gate's [views] alias walker.

KNOWN_DRIFTS lists the mismatches that are live today and ride the release
train. The set is STRICT: a drift that disappears must be removed from the set
(the test fails until you do), and a new drift fails immediately.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
ONT = ROOT / "app" / "bqs" / "ontology"
VIEWS = ROOT / "views"

# (yaml file, field kind, field name, kind of drift) — see test output for the
# exact wording; keep this set in sync with BACKLOG §2 "products: matches the DDL".
KNOWN_DRIFTS: set[tuple[str, str, str, str]] = set()

# Two-branch views: branch 0 = ECM, branch 1 = DCM (the UNION ALL order).
TWO_BRANCH_PRODUCTS = ("ECM", "DCM")


def _view_branches(path: Path) -> list[list[tuple[str, str]]]:
    """Per top-level SELECT branch: [(ALIAS, expression_text), ...] in order."""
    src = path.read_text()
    m = re.search(r"CREATE OR REPLACE VIEW[^;]*?AS\s*SELECT", src)
    assert m, f"{path.name}: no CREATE OR REPLACE VIEW ... AS SELECT"
    body = src[m.end():]
    # Walk the projection at paren depth 0 up to the top-level FROM; split
    # on depth-0 commas; the alias is the last `AS NAME` of each item.
    branches, items, depth, cur, infrom = [], [], 0, [], False
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                break
        if depth == 0:
            # A keyword only counts when it is a whole word: the character
            # before must not be part of an identifier, and the slice must
            # extend past the keyword so the trailing boundary is real
            # (`FROM_TS`, `SELECTED` must NOT match — PR bot, 2026-09-18).
            word_start = i == 0 or not (body[i - 1].isalnum() or body[i - 1] == "_")
            if word_start and re.match(r"UNION\s+ALL(?![A-Za-z0-9_])", body[i:i + 12]):
                branches.append(items); items, cur, infrom = [], [], False
                i += len(re.match(r"UNION\s+ALL", body[i:i + 12]).group(0)); continue
            if not infrom and word_start and re.match(r"FROM(?![A-Za-z0-9_])", body[i:i + 5]):
                if cur:
                    items.append("".join(cur)); cur = []
                infrom = True
            if not infrom and word_start and re.match(r"SELECT(?![A-Za-z0-9_])", body[i:i + 7]):
                i += 6; continue
            if not infrom and ch == ",":
                items.append("".join(cur)); cur = []; i += 1; continue
        if not infrom:
            cur.append(ch)
        i += 1
    if cur and not infrom:
        items.append("".join(cur))
    branches.append(items)
    out = []
    for br in branches:
        cols = []
        for item in br:
            am = re.search(r"\bAS\s+\"?([A-Z_][A-Z0-9_]*)\"?\s*$", item.strip(), re.S)
            if am:
                cols.append((am.group(1), item.strip()))
        out.append(cols)
    return [b for b in out if b]


def _catalog_fields(path: Path) -> tuple[str, dict[str, dict]]:
    """Return (view name, {field: {'kind', 'column', 'products'}}) from a yaml."""
    src = path.read_text()
    try:
        import yaml

        doc = yaml.safe_load(src)
        view = doc["base_view"].split(".")[-1].upper()
        fields = {}
        for kind in ("metrics", "dimensions", "filters"):
            for name, spec in (doc.get(kind) or {}).items():
                if isinstance(spec, dict) and spec.get("column"):
                    fields[f"{kind}:{name}"] = {"kind": kind, "column": str(spec["column"]).upper(),
                                                "products": tuple(spec.get("products") or ())}
        return view, fields
    except ImportError:
        view = re.search(r"^base_view:\s*\S+\.(\w+)", src, re.M).group(1).upper()
        fields = {}
        for kind in ("metrics", "dimensions", "filters"):
            sec = re.search(rf"^{kind}:\s*$(.*?)(?=^\S)", src, re.M | re.S)
            if not sec:
                continue
            for bm in re.finditer(r"^  ([a-z_0-9]+):(.*?)(?=^  [a-z_0-9]+:|\Z)", sec.group(1), re.M | re.S):
                cm = re.search(r"column:\s*([a-z_0-9]+)", bm.group(2))
                pm = re.search(r"products:\s*\[([^\]]*)\]", bm.group(2))
                if cm:
                    prods = tuple(p.strip(" \"'") for p in pm.group(1).split(",")) if pm else ()
                    fields[f"{kind}:{bm.group(1)}"] = {"kind": kind, "column": cm.group(1).upper(), "products": prods}
        return view, fields


def _drifts() -> set[tuple[str, str, str, str]]:
    found = set()
    for ypath in sorted(ONT.glob("*.yaml")):
        view, fields = _catalog_fields(ypath)
        vpath = VIEWS / f"{view.lower()}.sql"
        if not vpath.exists():
            found.add((ypath.name, "base_view", view, f"no views/{view.lower()}.sql — every field is unverifiable"))
            continue
        branches = _view_branches(vpath)
        aliases = {a for br in branches for a, _ in br}
        # Each branch names its own product in the PRODUCT literal — never
        # assume the UNION order (vw_trade_detail puts DCM first).
        branch_products = []
        for br in branches:
            pm = re.search(r"'(ECM|DCM)'", dict(br).get("PRODUCT", ""))
            branch_products.append(pm.group(1) if pm else None)
        two = len(branches) == 2 and all(branch_products)
        for key, spec in fields.items():
            kind, name = key.split(":", 1)
            col = spec["column"]
            if col not in aliases:
                found.add((ypath.name, kind, name, f"column {col} is not projected by {vpath.name}"))
                continue
            if not two:
                continue
            stubbed = []
            for prod, br in zip(branch_products, branches):
                expr = dict(br).get(col, "")
                if re.match(r"CAST\s*\(\s*NULL\s+AS", expr, re.I):
                    stubbed.append(prod)
            declared = spec["products"]
            live = tuple(p for p in TWO_BRANCH_PRODUCTS if p in branch_products and p not in stubbed)
            if stubbed and not declared:
                found.add((ypath.name, kind, name, f"NULL on {'/'.join(stubbed)} but declared for both products"))
            elif declared and tuple(sorted(declared)) != tuple(sorted(live)):
                found.add((ypath.name, kind, name,
                           f"declared products {list(declared)} but the view fills it on {list(live)}"))
    return found


def test_view_parser_finds_every_branch_and_alias():
    for v in ("vw_deal_summary", "vw_tranche_summary", "vw_order_detail", "vw_trade_detail"):
        br = _view_branches(VIEWS / f"{v}.sql")
        assert len(br) == 2, f"{v}: expected 2 UNION branches, parsed {len(br)}"
        assert [a for a, _ in br[0]] == [a for a, _ in br[1]], f"{v}: branch alias lists differ"
        assert len(br[0]) >= 20, f"{v}: parsed only {len(br[0])} projected columns"


def test_catalog_columns_match_the_views():
    found = _drifts()
    new = found - KNOWN_DRIFTS
    gone = KNOWN_DRIFTS - found
    msg = []
    if new:
        msg.append("NEW catalog↔view drifts (fix the yaml products:/column:, or add to KNOWN_DRIFTS with a ticket):\n  "
                   + "\n  ".join(" | ".join(d) for d in sorted(new)))
    if gone:
        msg.append("drifts in KNOWN_DRIFTS that no longer exist — remove them:\n  "
                   + "\n  ".join(" | ".join(d) for d in sorted(gone)))
    assert not msg, "\n".join(msg)


if __name__ == "__main__":
    ok = True
    for fn in (test_view_parser_finds_every_branch_and_alias, test_catalog_columns_match_the_views):
        try:
            fn()
            print(f"  ok   {fn.__name__}")
        except AssertionError as e:
            ok = False
            print(f"  FAIL {fn.__name__}\n{e}")
    print("\nThe catalogs describe the views the agent actually queries." if ok else "\nContract FAILED.")
    sys.exit(0 if ok else 1)
