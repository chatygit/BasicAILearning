# Release-2 config flips — STAGED, apply ONLY after the release-2 views deploy

Configs naming missing columns kill every query (round-2 lesson). The
views in this batch: away orders + ORDER_OWNERSHIP + EQUITY_TYPE on the
order view; currency global fallback on tranche/order; CURRENCIES in
pricing order on the deal view. When the view team confirms deploy (run
_deploy-check.sql — rows 1i PASS, 1j shows an away count), apply ALL of
the following, run the three gates, delete this file.

## capital_markets_order.yaml
1. NEW dimension + filter `order_ownership` (column order_ownership,
   products ["ECM"], ops eq/ne/in/not_in/is_null/is_not_null,
   case-insensitive, suggestable). Description: "HOME = our (owned) book;
   AWAY = orders seen away. INCLUDED IN ALL TOTALS since release 2 —
   before it, every figure was HOME-only. 'our orders'/'Citi's book' =
   eq HOME; NULL = flag not stored on that row. DCM: NULL (no flag)."
2. NEW dimension + filter `equity_type` (products ["ECM"], mirror the
   tranche object's entry verbatim incl. the known value list, like-only
   class matching, NEVER-OR-with-product_type rule).
3. `currency` description: remove the grain-asymmetry caveat (healed);
   note the global-name fallback now applies at all grains.
4. Doc notes: (a) totals/counts now include AWAY orders — for
   before/after comparisons or "our book" asks, filter order_ownership;
   (b) the BlackRock-class recipe is ONE request now: investor +
   equity_type both live here — the SMALLER-side two-step remains only
   for deal_status / deal_size / use_of_proceeds.
5. Applicability lists: ECM-only set gains order_ownership + equity_type.

## capital_markets_tranche.yaml + capital_markets_deal.yaml
6. `currency` (tranche): drop the "effectively NULL when demand-currency
   row missing" hedge — global fallback live.
7. `currencies` (deal, both yamls' cross-refs): "ordered by FIRST PRICING
   (lead currency first), no longer alphabetical."

## SKILL.md
8. §5 currency bullet: REMOVE the "KNOWN GRAIN ASYMMETRY (PROD issue #2)"
   block; REMOVE "ALPHABETICAL, not chronological" and replace with:
   list reads in pricing order, lead first — position IS meaningful now;
   the one-query chronology recovery recipe retires.
9. §3 two-step block: equity_type leaves the two-step list ("investor in
   convertibles" = ONE order-object request); keep SMALLER side + HARD
   BUDGET for the remaining cross-object asks.
10. §6b/§7: new bullet — ALL ECM order figures include away orders since
    release 2; "our/Citi's orders" = order_ownership HOME; disclose the
    home/away split when a total mixes them and the user asked about
    "our" book.
11. Routing row: "away orders / home orders / our book" → order ·
    order_ownership.

## Gate (ontology_check.py)
12. Retire: [present] "ALPHABETICAL, not" pin and the "KNOWN GRAIN" pin
    (their doctrine is deleted by #8) — replace with pins on the new
    wording ("pricing order, lead first"; "include away orders").
13. Add _PRODUCT_PINS: (order, order_ownership, ECM), (order,
    equity_type, ECM).
14. Update the [routing] two-step pin if its pinned strings change.

## capital_markets_tranche.yaml (added 2026-08-21)
15. NEW dimension + filter `settlement_ts` (column settlement_ts,
    products ["DCM"], range ops like the deal object's entry, mirroring
    its description — tranche grain = the tranche's OWN settlement, not
    the deal MAX; ECM is NULL at this grain, route ECM settlement asks to
    the deal object). Add _PRODUCT_PINS entry (tranche, settlement_ts,
    DCM). SKILL routing row: "tranches settling in <period>" → tranche ·
    settlement_ts (DCM); ECM settlement stays a deal-object ask.
