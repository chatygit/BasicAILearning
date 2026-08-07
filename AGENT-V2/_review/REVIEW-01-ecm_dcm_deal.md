# Review 01 — `ecm_dcm_deal.yaml` (deal object)

Reviewed from screenshots, 2026-08-07. Physical source
`dataglobe_oraas.dgstream.vw_deal_summary`, `grain: [product, deal_id]`.

## Verdict

Structurally right. The grain is declared, the object refuses tranche/order
attributes and says where to go instead, and the pre-computed roll-ups
(`tranche_count`, `order_count`, `investor_count`, `currencies`) are exactly what
keeps deal questions single-object. Four correctness defects below, then structural
gaps, then questions I can't answer from the file.

---

## A. Correctness — fix before anything else

### A1. `largest_deal_size` / `smallest_deal_size` are missing `requires_filters: [product]`

`total_deal_size` and `average_deal_size` both carry it; MAX and MIN do not. Without a
product filter, `MAX(deal_size)` compares **ECM share counts against DCM notional
money** and returns whichever number is numerically bigger — always DCM. "What's the
biggest deal?" silently answers "the biggest DCM deal", presented as a cross-product
fact.

Add `requires_filters: [product]` to both. Any metric over `deal_size` needs it; the
rule is *every metric that touches a per-product-unit column*.

### A2. `how_to_use` contradicts `usage_notes` on the trailing-window bound

- `how_to_use`: *"Add an upper bound **at today** for trailing windows"*
- `usage_notes`: *"BOTH bounds (gte start AND **lt tomorrow-midnight**)"*

`usage_notes` is right. An upper bound at today-midnight **drops everything priced
today** — that was a production bug we fixed in the opposite direction, and one
sentence still encodes it. Make `how_to_use` say `lt tomorrow-midnight` verbatim.

### A3. No shorthand→value mapping for `use_of_proceeds` (and friends)

`case_insensitive: true` and a `like` operator are present, which is necessary but not
sufficient. Users type shorthand; the stored values are awkward:

| User says | Stored value |
|---|---|
| m&a, merger, takeover, buyout, acquisition | **`M & A`** (spaces around the ampersand) *and* `Acquisitions` / `Future Acquisitions` |
| refi, refinancing, debt repayment, pay down debt | `Refinance` **and** `Debt Repayment` (both exist) |
| capex | `Capital Expenses` |
| buyback | `Share Repurchase` |
| GCP | `General Corporate Purposes` |

A naive `use_of_proceeds like '%M&A%'` matches **nothing** — the stored value has
spaces. Encode the map wherever the framework allows (allowed values, a synonyms
block, or `usage_notes` if there is nowhere better), and note that `N/A` and
`No Proceeds to Issuer` mean *purpose not stated* and should be excluded from purpose
breakdowns with a note.

Same treatment needed for `sector`: it is a closed list where
`Information Technology` ≠ `Technology` and **`Oil & Gas` ≠ `Energy`** — an energy
question that misses `Oil & Gas` is a wrong answer, not a near miss.

### A4. Ordering has no deterministic tiebreaker

The examples use `order: [{field: total_deal_size, direction: desc}]` with nothing
after it. In production two investors tied on an equal value **swapped places between
two turns of the same session**, which made a follow-up look like a different answer.

Either the builder appends a unique tiebreaker automatically (preferred — say so in
the file), or every example must show one: `order: [{field: total_deal_size, direction:
desc}, {field: deal_id, direction: asc}]`.

---

## B. Structural — encode as data, not prose

The lesson from six weeks of the previous design: **every rule that stayed prose was
eventually paraphrased away; every rule that became structure stopped recurring.**

### B1. Per-product applicability is prose

`equity_type`, `offering_type`, `execution_status`, `deal_region` are all marked
`"ECM."` at the start of their description. That is a convention the model may or may
not honour. If the framework supports something like `applies_to_product: [ECM]`, use
it and have the planner reject the impossible combination up front — a DCM query
filtering `equity_type` currently returns an empty result that reads as "no such
deals".

If the framework does not support it, say so in the open-questions list; it is worth a
small planner change.

### B2. Units are prose

`deal_size` says "ECM shares / DCM money" in its description. The formatter needs this
**machine-readable** to label a column header "Deal Size (shares)" vs "Deal Size (USD)"
— and the header is where the unit belongs (per-cell tags were rejected by QA).

Suggest per-field unit metadata, e.g. `unit: {ECM: shares, DCM: money}`. Related: on
ECM the security-count word depends on the deal class — **"bonds" for convertible-class
deals**, "shares" otherwise — which is derivable from `equity_type` on this object.

### B3. `deal_status` vs `execution_status` needs an explicit tie-break

Both exist with overlapping values. The rule we settled on: **any generic
status/live/priced/closed question → `deal_status`; use `execution_status` only when
the user literally says "execution status".** Without that, the model picks either.

Also worth stating on `deal_status`: values are mixed-case *with case duplicates*
('Open' and 'OPEN' both occur) — `case_insensitive: true` handles it, but the note
explains *why* it is not optional.

### B4. `row_count` duplicates `deal_count` on this object

At deal grain `COUNT(deal_id)` equals `COUNT(DISTINCT deal_id)`. Harmless, but the
model may reach for `row_count` when it means deals. One line in the description —
*"equals deal_count on this object; exists for paging"* — removes the ambiguity.

---

## C. Questions I can't answer from this file

1. **Where does "Citi solo deals" route?** `deal_sharing_type` is absent from this
   object's dimensions and filters. If it lives on the tranche object, `how_to_use`
   should say so — solo/B&D asks sound deal-shaped to a user. And check whether the
   new view fixed the ECM semantics (SOLO meant "Citi-led", 25.1% mislabelled).
2. **Is `requires_filters` enforced or advisory?** If the planner only warns, A1 does
   not actually protect anything.
3. **Where do `suggestable` values come from** — a live `DISTINCT` against the view, or
   a static list? Only `product` declares `values:`. If suggestions are live, that is
   better than any list I could give you; if static, the taxonomy vocabularies need a
   home.
4. **Does `list_count` know the delimiter?** `currency_count: MAX(currencies)` with
   `list_count: true` presumably counts separators. Confirm it uses the same delimiter
   the view emits, and that a single-currency deal returns 1, not 0.
5. **Entitlement interaction.** The header says entitlement injects a product filter
   *and* `how_to_use` says always set one. If a user entitled to ECM only sends
   `product = DCM`, does the server override, reject, or AND them into nothing? A
   rejection with a clear message is the safe behaviour.
6. **`is_null` / `is_not_null`** exist only on `settlement_currency`. Unpriced deals
   ("deals not yet priced") need `is_null` on `first_priced`. Intentional?
7. **`max_limit: 5000`** vs a ~20-row display cap — which layer truncates, and does the
   answer get told the true total so it can say "showing 20 of N"?

---

## D. What is right and should be preserved verbatim

- `grain: [product, deal_id]` declared on the object — this is the whole migration in
  one line.
- `how_to_use` naming the *other* objects for tranche and order attributes. Cross-object
  routing belongs in the catalog, not the skill.
- `average_investor_count` carrying **"Do NOT sum it across deals — investors overlap
  between deals"**. That is precisely the kind of trap that used to cost a wrong answer,
  and it is now attached to the metric itself.
- `total_order_count` allowed to SUM while `average_investor_count` is not — the
  distinction (orders don't overlap, investors do) is correct and non-obvious.
- `issuer_name` filter: **"No id lookup needed."** That single sentence is the
  fewest-hops doctrine; it removes an entire round-trip from most questions.
- `entity_name: true` + `case_insensitive: true` on the name filters.
- The DCM money caveat (deal size is not currency-scoped here; use the tranche object
  grouped by currency) — subtle, correct, and exactly the sort of thing that gets
  answered wrongly otherwise.
