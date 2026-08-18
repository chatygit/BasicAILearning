# ROUND-2 STAGED CONFIG — apply ONLY after the view batch deploys

**DO NOT push these ontology/skill changes before the views.** They reference
columns (`BILLED_BY`, `OFFERING_TYPE` on the order view; `EQUITY_TYPE` on the
tranche view) that do not exist until the batch deploys — pushed early, every
query naming them dies with a Trino column-not-found. Sequence: (1) deploy
views, (2) run `_deploy-check.sql` → all PASS/INFO, (3) apply this file,
(4) push MCP + configs, (5) delete this file.

Measured basis (2026-08-18): ECM BILLED_BY 90.2% populated (86,611/96,006,
full bank names despite the source column being named BILLEDBY_BROKER_CODE);
DCM BILLED_BY 74% (OB_ORDER.BND), varying within 53% of tranches.

## 1. capital_markets_order.yaml

**dimensions** — add:
```yaml
  billed_by: {column: billed_by, description: "The bank that billed/settled THIS order (B&D), on BOTH products — full bank names on both (the ECM source column is misleadingly named BILLEDBY_BROKER_CODE but holds names). Order-level truth: it VARIES within a tranche (measured on half of DCM tranches), so it can legitimately disagree with the tranche object's BND_BANK designation list — for 'billed by' asks, THIS column wins. NULL = no billing bank recorded (~10% ECM, ~26% DCM)."}
  offering_type: {column: offering_type, products: ["ECM"], description: "ECM. Deal-level offering type denormalized to order grain — only 'IPO' and 'FO' stored. Makes 'investors in IPOs' ONE request on this object (no deal-id ferry). NULL on DCM."}
```

**filters** — add:
```yaml
  billed_by:
    column: billed_by
    operators: [like, in, not_in, is_null, is_not_null]
    suggestable: true
    case_insensitive: true
    description: >-
      The bank that billed THIS order, both products, full names. Match with
      like on a stem, NEVER eq — variants are real ('Citigroup Global Markets
      Inc.' and ', Inc.' both occur; a truncated 'J.P. Morgan P' exists on
      DCM). Citi = '%CITIGROUP GLOBAL MARKETS%' ONLY (the 'Citi (Test
      Syndicate CMG)'/CITIBANK entities are NOT Citi). is_null = no billing
      bank recorded — a real bucket, report it as that. For 'Citi non-B&D
      orders' use the bill_and_deliver computed filter with negate (NULL-safe);
      a bare not_in/ne here silently drops the unrecorded orders.
  offering_type:
    column: offering_type
    products: ["ECM"]
    operators: [eq, ne, in, is_null, is_not_null]
    suggestable: true
    case_insensitive: true
    description: >-
      ECM. 'IPO' and 'FO' only (same vocabulary as the deal object).
      "Investors in IPOs" is now ONE request HERE — filter offering_type eq
      'IPO' with the investor filters; the deal-id two-step is dead.
```

**computed_filters** — add (token-less, mirrors the tranche one; a single
stem works for BOTH products because both hold names):
```yaml
computed_filters:
  bill_and_deliver:
    column: billed_by
    pattern_template: "{value}"
    fixed_codes: ["CITIGROUP GLOBAL MARKETS"]
    description: >-
      Citi billed this ORDER (token-less; Citi is implied). negate true =
      'Citi non-B&D orders', NULL-safe so unrecorded-billing orders stay in.
      Order-level twin of the tranche object's filter — this one is
      per-order truth, that one is the tranche designation.
```

**how_to_use** — update the applicability list: the ECM-only closed list
gains `offering_type` (now eight fields); add one line: "billed_by is on BOTH
products (order-level billing truth; the tranche's BND_BANK is only the
designation)."

## 2. capital_markets_tranche.yaml

**dimensions + filters** — add `equity_type` (mirror the deal object's entry:
products ["ECM"], operators [eq, ne, in, not_in, like], suggestable,
case_insensitive, the known-set description INCLUDING the Exchangable-
misspelling and the never-blend-with-product_type rule).

**Gate note**: add (tranche, equity_type, ECM), (order, offering_type, ECM)
to `_PRODUCT_PINS` in ontology_check.py. billed_by declares NO products (both).

## 3. SKILL.md

- **Class-word map**: the "CLASS ask ranked by a TRANCHE metric" two-step
  bullet COLLAPSES — equity_type is on the tranche object now: one request,
  filter equity_type there directly, project product_type for the sub-type
  breakdown. Delete the 40-id fallback clause for this shape.
- **IPO two-step (§2 block)**: "Investors in IPOs is TWO requests today" →
  ONE request on the order object (offering_type filter). Keep the id-ferry
  doctrine for shapes that still need it (equity-class + investor asks
  remain two-object until equity_type reaches the ORDER view — it has not).
- **§7 B&D**: add — "billed by X" at ORDER grain = order object billed_by
  (like-stem); billed-by league tables = GROUP BY billed_by (both products);
  the tranche BND_BANK is the DESIGNATION and can legitimately disagree.
- **Routing table**: order-object row gains "billed by / billing bank"
  vocabulary; tranche B&D row scopes to designation/syndicate asks.

## 4. agents.yaml

Rule-2 routing list, order line: add "billed by, offering type (IPO/FO)".
