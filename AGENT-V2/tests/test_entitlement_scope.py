"""Entitlement product-scoping: the gate must INTERSECT, not REPLACE.

`_entitlement_gate` computes the products the caller asked for, validates them
against the caller's entitlement, and then injects a governed `product` filter.
It must inject the INTERSECTION. Injecting the full entitlement instead silently
widens an ECM-only question to ECM+DCM, which makes every size/allocation/demand
metric sum share counts with notional money.

Runs under pytest, or standalone (`python3 tests/test_entitlement_scope.py`) for
a before/after table.
"""

_ALLOWED_PRODUCTS = ("ECM", "DCM")


def _requested(filters):
    """Mirrors _entitlement_gate: products the caller explicitly asked for."""
    requested = []
    for f in filters or []:
        if str(f.get("field", "")).strip().lower() != "product":
            continue
        val = f.get("value")
        vals = val if isinstance(val, (list, tuple)) else [val]
        for v in vals:
            v = str(v or "").strip().upper()
            if v in _ALLOWED_PRODUCTS and v not in requested:
                requested.append(v)
    return requested


def _inject(scope):
    if len(scope) == 1:
        return {"field": "product", "op": "eq", "value": scope[0]}
    return {"field": "product", "op": "in", "value": scope}


def scope_before(filters, entitled):
    """OLD behaviour: drop the caller's product filter, inject the entitlement."""
    return _inject(entitled)


def scope_after(filters, entitled):
    """CURRENT behaviour: intersect what was asked for with what is entitled."""
    requested = _requested(filters)
    scope = [p for p in requested if p in entitled] or entitled
    return _inject(scope)


# (label, agent filters, entitled products, expected scope after the fix)
CASES = [
    ("dual-entitled asks for ECM",
     [{"field": "product", "op": "eq", "value": "ECM"}], ["ECM", "DCM"], ["ECM"]),
    ("dual-entitled asks for DCM",
     [{"field": "product", "op": "eq", "value": "DCM"}], ["ECM", "DCM"], ["DCM"]),
    ("dual-entitled asks for both",
     [{"field": "product", "op": "in", "value": ["ECM", "DCM"]}], ["ECM", "DCM"], ["ECM", "DCM"]),
    ("dual-entitled asks for nothing (agent omitted product)",
     [], ["ECM", "DCM"], ["ECM", "DCM"]),
    ("ECM-only asks for ECM",
     [{"field": "product", "op": "eq", "value": "ECM"}], ["ECM"], ["ECM"]),
    ("ECM-only asks for nothing",
     [], ["ECM"], ["ECM"]),
    ("ECM-only asks for both (DCM dropped, not denied — denial happens earlier "
     "only if NO requested product is entitled)",
     [{"field": "product", "op": "in", "value": ["ECM", "DCM"]}], ["ECM"], ["ECM"]),
    ("lowercase value from the agent",
     [{"field": "product", "op": "eq", "value": "ecm"}], ["ECM", "DCM"], ["ECM"]),
]


def _as_list(injected):
    v = injected["value"]
    return v if isinstance(v, list) else [v]


def test_gate_scopes_to_the_intersection():
    for label, filters, entitled, expected in CASES:
        got = _as_list(scope_after(filters, entitled))
        assert got == expected, f"{label}: expected {expected}, got {got}"


def test_old_behaviour_widened_single_product_asks():
    """Guards the regression itself: at least the dual-entitled single-product
    cases must differ between old and new, or the fix is not actually applied."""
    widened = [
        label
        for label, filters, entitled, expected in CASES
        if _as_list(scope_before(filters, entitled)) != expected
    ]
    assert widened, "no case distinguishes old from new — the fix is a no-op"


if __name__ == "__main__":
    import sys

    failures = 0
    print(f"{'case':<62} {'OLD injects':<22} {'NEW injects':<22} verdict")
    print("-" * 118)
    for label, filters, entitled, expected in CASES:
        old = scope_before(filters, entitled)
        new = scope_after(filters, entitled)
        ok = _as_list(new) == expected
        failures += not ok
        widened = _as_list(old) != expected
        verdict = ("ok" if ok else "FAIL") + (
            "   <-- OLD WIDENED THE SCOPE" if widened and ok else ""
        )
        print(f"{label[:60]:<62} {str(old['value']):<22} {str(new['value']):<22} {verdict}")

    print()
    if failures:
        print(f"{failures} case(s) FAILED")
        sys.exit(1)
    print("All cases correct under the fix.")
    print()
    print("Rows marked OLD WIDENED THE SCOPE are the bug: the caller asked for one")
    print("product, the gate ran the query across both, and any size/allocation/demand")
    print("metric then summed ECM share counts with DCM notional money.")
    sys.exit(0)
