# Review 02 — `capital_markets_entity.yaml` (entity resolution object)

Source `dataglobe_oraas.dgstream.vw_entity_search`, `grain: [entity_type, product,
entity_id]`, `max_limit: 50`.

## Verdict

The best-designed of the two so far *as a contract* — the fewest-hops rule is stated
first, entitlement scoping is explicit, and every candidate carries an id. But the
**matching strategy is a regression against v1**, and one advertised capability is not
actually supported by the filters.

---

## B1. Exact-first is now TWO round-trips — this is the big one

`how_to_use` says: *"Try an exact-name match first (op 'eq'); only fall back to
contains if it returns nothing."*

The v1 design did exact → contains → phonetic tiering **inside one query**, using
`is_exact` / `is_sub` flags with `MAX(...) OVER ()` window gates so a single execution
returned exact matches when any existed and contains-matches otherwise. Here it is a
prompt instruction to run one query, inspect it, and run another.

**Why this matters more than it looks:** the exact tier misses in the *common* case.
A user typing "blackrock" will not `eq` "BLACKROCK FINANCIAL MGMT (NY)". So the
two-hop path becomes the default, not the exception — and we measured tool round-trips
at **5–15 seconds each**, on a path that runs *before* the user's real question.

Three ways out, best first:

1. **Push the tiering into the view.** If `VW_ENTITY_SEARCH` exposed a `match_rank`
   the caller could not compute — or the ontology supported a `smart_name` /
   `name_match` operator that compiles to the gated tiering — resolution is one query
   again. This is the v1 behaviour, restored, with the logic where it belongs.
2. **A computed filter** that expresses "exact if any exact exists, else contains",
   if the framework's `computed_filters` can carry a window predicate.
3. **Accept two hops but invert the default**: lead with contains (which almost always
   returns something), and only use `eq` when the user supplied what looks like a full
   legal name. Cheapest to implement, and strictly better than the current wording
   because it makes the *common* case one hop.

Whichever is chosen, the file should say it in one line rather than leaving the agent
to sequence two calls.

## B2. "Recover a misspelling" is advertised but not supported

`how_to_use` lists misspelling recovery as a reason to use this object. The available
operators are `like`, `eq`, `in`. A genuine typo — "blackrok" — does not match
`%BLACKROK%` against "BLACKROCK", so this path returns nothing.

Either wire a phonetic/fuzzy operator (or a fallback to the existing fuzzy resolver)
**or delete the claim**. An advertised capability that silently fails is worse than an
absent one, because the agent will route to it and then report "no such investor".

Note for whoever implements it: v1 removed phonetic matching from the main pass
deliberately — it cost ~19% of runtime and added ~350 junk candidates on a single
search. It belongs as a **fallback after a zero-result contains pass**, never in the
same query.

## B3. `context_value_1/2` are opaque to the formatter

Their meaning is type-dependent (investor: category/region; issuer: sector/ticker;
deal: status/issuer). The description records that, but a formatter rendering a
disambiguation list has no way to label them — it will emit "Context Value 1".

The target output is:

> `1) BLACKROCK INC [GPNUM: 00919] — Asset Manager · United States · 34 deals, last 2026-05`

so the labels must vary by `entity_type`. Either the view carries label columns
alongside the values, or the ontology declares a per-type label map, or the formatter
special-cases this object. Flag which one you chose.

## B4. No filter on `last_active` or `entity_activity_count`

Ranking sinks dormant entities but cannot exclude them. "Investors active in the last
two years" is a reasonable narrowing, and on a name that matches 40 candidates it is
the difference between a usable list and a wall. Both are dimensions already; adding
them as filters costs nothing.

## B5. The ranking contract is stated three times and differs each time

- Header: `entity_activity_count desc, then last_active desc`
- `how_to_use`: "…desc (add `last_active` desc)"
- Examples: `order: [{field: entity_activity_count, direction: desc}]` only

And none of them ends in a unique tiebreaker, so ties reorder between runs — the same
defect flagged as A4 on the deal object. Make the examples show the full contract:
`entity_activity_count desc, last_active desc, entity_id asc`.

## B6. The two examples disagree on scoping

The blackrock example sets `product`; the apple example does not. Examples are the
strongest teaching signal in the file, so an inconsistency here will be reproduced.
Either both set it, or the file states that entitlement makes it optional.

## B7. Minor

- **`metric: max_activity` as the idiom in both examples.** At this grain, grouping by
  `entity_name, entity_id` and taking `MAX(entity_activity_count)` returns the row's
  own value — it works, but reads oddly. Is a metric mandatory in a request? If not,
  a dimensions-only projection is simpler and less likely to be copied wrongly.
- **`row_count` duplicates `entity_count`** at this grain (same note as the deal object).
- **DEAL activity = tranche count.** For disambiguating deals, recency is a better
  signal than tranche count — two deals with the same name are distinguished by *when*,
  not by *how many tranches*. Consider ordering DEAL candidates by `last_active` first.
- **`max_limit: 50`** is right for the query, but the agent should return ~12 and
  display ~10 with "and N more". Confirm where that cap lives.

---

## What is right and should be preserved

- **"A metric/list ask that merely NAMES an entity does NOT come here — filter the name
  inline on the deal/tranche/order object instead (fewest hops)."** This is the single
  most valuable sentence in either file. It removes a round-trip from the majority of
  questions and it is stated *first*, where the agent will read it.
- Entitlement scoping called out in the header **and** repeated in `usage_notes` — the
  entity path is exactly where the previous design leaked cross-product names.
- "Every candidate carries `entity_id` — a candidate without an id is useless."
- The umbrella-family rule (blackrock/fidelity → return the family grouped, do not force
  a single pick).
- Replacing the zen-API path with a SQL-backed object — one less external dependency on
  the latency-critical path.
