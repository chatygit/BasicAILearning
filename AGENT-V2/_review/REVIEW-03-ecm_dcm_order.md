# Review 03 — `ecm_dcm_order.yaml` (order object)

Source `dataglobe_oraas.dgstream.vw_order_detail`, `grain: [product, order_id]`.

## Verdict

The best of the three. Deal and tranche attributes are denormalised **down** exactly
as the grain contract requires, the routing note about "how many deals did X buy"
survived verbatim, the investor-region trap is spelled out, and `unsupported_intents`
now lives **in the ontology** rather than in a prompt — that last one is a genuine
upgrade over v1.

Two defects are serious, and one is a contradiction inside the file itself.

---

## C1. No metric declares `requires_filters: [product]` — and this is the object where it matters most

The deal object guards `total_deal_size` and `average_deal_size`. Here **nothing is
guarded**: `total_allocation`, `total_demand`, `max_allocation`, `average_allocation`,
`max_demand` all sum or compare a column whose unit is **shares on ECM and money on
DCM**.

This is not theoretical. The production incident was on this exact shape — a "top
investors by allocation" answer that summed across products and rendered
**"1,000.0bn shares"**, a number that cannot exist. `how_to_use` says "State the unit",
but the request that produced it was already wrong before formatting.

Add `requires_filters: [product]` to every metric over `order_allocation`,
`order_demand_qty` and `order_amount`. If the planner treats `requires_filters` as
advisory rather than blocking, that needs to change first — otherwise the guard on the
deal object is decorative too.

## C2. The file contradicts itself on "classification"

- Dimension: `investor_category: "ECM. Investor **classification** (Long Only, Hedge Fund…)"`
- `unsupported_intents.investor_classification`: *"'classification' is a different,
  untracked taxonomy from investor_category"*

Both are in the same file. The dimension description teaches the model that category
*is* classification; the refusal rule then denies it. Whichever the agent reads last
wins, which is not a design.

Fix: the dimension description says **"Investor category"** and nothing else. The word
"classification" should appear in this file **only** inside the unsupported intent.

Worth adding while you are there, since it is the actual reason the distinction exists:
classification's values (Strategic, Family Office, Retail, SWF, DSP, Index, Quant) do
not appear in category at all — that is why substituting one for the other returns a
wrong population rather than an approximate one.

## C3. The "paged listing" example cannot page, and does not list

```yaml
order: [{field: investor_name, direction: asc}]
limit: 50
```

Two problems:

1. **`investor_name` is not unique.** Paging with a non-unique sort key gives unstable
   pages — rows can repeat or vanish between page 1 and page 2. Any request that will
   be paged needs a unique final sort key (`order_id` here). This is the same class as
   the ranking tie that reshuffled between turns in production, but with worse
   consequences, because the user sees it as missing data.
2. **It aggregates rather than lists.** The projection is
   `[investor_name, investor_id, order_type, ioi_type]` with `metric: order_count` —
   that answers "how many orders per investor", not "show me the orders". A genuine
   order listing needs `order_id` and the allocation/demand columns.

Suggested replacement:

```yaml
- question: Orders for a specific deal (paged listing)
  request:
    source: ecm_dcm_order
    metric: order_count
    dimensions: [order_id, investor_name, investor_id, tranche_name,
                 order_type, ioi_type]
    filters:
      - {field: product, op: eq, value: ECM}
      - {field: deal_id, op: eq, value: "REPLACE_WITH_DEAL_ID"}
    order: [{field: investor_name, direction: asc}, {field: order_id, direction: asc}]
    limit: 50
```

And state the general rule somewhere in the file: **every order/limit that may be
paged ends in a unique key.**

## C4. A stated rule that cannot be executed

`how_to_use` says: *"A NOT-region predicate drops null-region rows; say how many were
excluded."*

Correct and important — but `investor_region` offers only `[eq, ne, in, not_in, like]`.
There is **no `is_null`/`is_not_null`**, so the agent has no way to count the excluded
rows and cannot honour the instruction. Add both operators.

The same gap exists anywhere a NOT-predicate is legal. A rule the ontology asks for
but does not enable is worse than no rule: the agent either ignores it or invents a
number.

## C5. Coverage is cross-object — but it does not have to be

`how_to_use` notes *"Coverage = demand ÷ size (size lives on the tranche/deal
object)"*. That is honest, but coverage — "was the book covered?", "3.2× covered" — is
one of the most common syndicate questions, and today it needs two requests plus manual
division.

**`tranche_size` can be denormalised down onto the order object without violating the
grain contract** — it is *coarser* than order grain, so it cannot multiply rows. That
is exactly what the rule permits ("denormalise downward, never carry a finer grain
upward"), and it is already being done for `deal_name`, `tranche_name`, `currency` and
`pricing_date`.

With `tranche_size` present, coverage becomes a computed metric on a single object.
Worth raising with whoever owns the view; the cost is one more column.

## C6. `meeting_type` has no values, and the value is the trap

The stored literal is **`1x1`** — not "One-to-One", which is what a model will guess.
We lost a QA cycle to exactly that. Also relevant: *"other than 1x1"* must exclude both
`1x1` **and** `No Meeting`, and the answer should say the no-meeting orders were
excluded, or the count reads as if everyone met.

If `suggestable: true` pulls live `DISTINCT` values, this is already solved — please
confirm, because the same question decides whether `investor_category`,
`order_type` and `ioi_type` need explicit value lists too.

## C7. Minor

- **No row-level threshold filter on allocation/demand.** `HAVING` on `total_allocation`
  covers "investors whose total exceeds X", but "orders larger than 1m shares" is a
  row-level predicate and has no filter. Confirm whether that is intentional.
- `row_count` duplicates `order_count` at this grain (third occurrence — worth one
  consistent line in all four files).
- `investor_region`, `investor_category`, `meeting_type`, `order_type`, `ioi_type` are
  all prefixed "ECM." in prose — same per-product-applicability point as A/B: it belongs
  in structure if the framework allows it.

---

## What is right and should be preserved

- **The routing note in the header** — *"'how many deals did &lt;investor&gt; buy?' is an
  ORDER question… the grain is orders; the metric counts deals."* This is the single
  hardest routing call in the whole model, and it is stated where the agent will see it
  before anything else.
- **The investor-region rule**, complete with `%US%` matching Russia and Austria, and
  the null-region disclosure requirement. That is a production bug converted into a
  permanent instruction.
- **The metric routing map** (demand → total_demand, allocation → total_allocation,
  DCM amount → total_order_amount). Metric ambiguity caused repeated wrong answers in
  v1; this resolves it at the catalog level.
- **`unsupported_intents` inside the ontology.** In v1 this lived in a separate JSON the
  agent might or might not have loaded. Here it is part of the authoritative catalog,
  with patterns, a reason and a user-facing message — refusals now come with a plan B
  by construction.
- `investor_id`: **"Quote it — leading zeros matter."** Precisely the failure that
  silently selected the wrong investor.
- Umbrella-family handling and "No id lookup needed" on `investor_name` — the
  fewest-hops doctrine, consistently applied across all three objects.
