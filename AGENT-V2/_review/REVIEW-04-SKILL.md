# Review 04 — `SKILL.md` (v2, four grain-aligned objects)

## Verdict

This is a better artefact than anything in v1. The hop budget, the grain-safe follow-up
rule, count honesty and the "never do" list are near-verbatim, and §3's routing table
resolves the ask **before** the first tool call — which is where routing decisions
belong. Two answers I'd been waiting for also appear here: the tranche view exposes a
**resolved `bnd_bank`**, and **`deal_sharing_type = 'SOLO'` is now true sole-managed**
(the 25.1% ECM mislabelling was fixed upstream). Good.

Seven findings, one of which is load-bearing for the whole design.

---

## D1. §4 still resolves in two round-trips — and it contradicts §0

§0 states the hop budget: *"every round-trip is 5–15 s… at most one resolution + one
request + one answer."* §4 then says: *"Try exact (`op: eq`) first; only fall back to
`like '%NAME%'` if exact returns nothing."*

For a partial name — which is what users type — the exact tier **misses by
construction**: "blackrock" never equals "BLACKROCK FINANCIAL MGMT (NY)". So the
two-hop path is the *common* case, not the exception, on the one path that runs before
the user's actual question.

v1 did exact → contains tiering **inside one query** using `is_exact`/`is_sub` flags
with `MAX(...) OVER ()` gates. That capability was lost in the migration.

Fix, best first: (a) expose a `match_rank` on `VW_ENTITY_SEARCH`, or a `name_match`
operator that compiles to the gated tiering — one query, v1 behaviour restored;
(b) express it as a `computed_filter`; (c) at minimum invert the default — lead with
contains (which almost always returns something) and use `eq` only when the user
supplied what looks like a full legal name.

## D2. The taxonomy value traps have no home — this depends on one unanswered question

Nowhere in the skill or the three ontologies I've seen are these encoded:

| Trap | Consequence if missed |
|---|---|
| Meeting type literal is **`1x1`**, not "One-to-One" | zero rows on a QA prompt |
| Use of proceeds **`M & A`** has spaces | `like '%M&A%'` matches nothing |
| Refi lives under **both** `Refinance` and `Debt Repayment` | undercount |
| **`Oil & Gas` ≠ `Energy`** in sector | wrong population, looks plausible |
| Deal status has case duplicates (`Open`/`OPEN`) | half the rows silently missing |
| Identifier types are **lowercase on DCM**, uppercase on ECM | DCM identifier asks return nothing |

The skill correctly delegates values to the catalog ("taxonomy words are filter
VALUES"), and the ontologies declare `values:` for **only** `product` and
`entity_type`. So unless `suggestable: true` triggers a live `DISTINCT` lookup, these
traps are homeless in v2 — and each one produced a wrong answer in v1.

**This is the question I most need answered:** does `suggestable` fetch live values? If
yes, D2 is already solved and better than any list I could write. If no, every
`suggestable` filter needs a `values:` list plus a synonym map, and that is a
substantial addition to all four files.

## D3. The "non-B&D" recipe is ambiguous — and it's where we had a production bug

§7 lists `bill_and_deliver` *(no token) — flag-based B&D; kept for parity, negate with
`negate:true` for "non-B&D"*.

What does negating a flag-based filter mean?
- "this tranche has **no** B&D designated at all", or
- "the B&D bank is **not** Citi"?

Those are different populations, and the second is what a banker asking for "Citi
non-B&D deals" wants: **deals Citi participated in but did not bill**. In v1 the model
expressed this as a whole-syndicate negation, which excluded every deal where Citi
appeared *anywhere* — a structural zero on a Citi platform.

Now that `bnd_bank` is resolved, the correct recipe is expressible and unambiguous:

> `broker_participation(citi)` **AND NOT** `bnd_bank like '%Citigroup%'`

State that explicitly in §7 rather than leaving `negate:true` to interpretation, and
say what the flag-negation actually produces so the two aren't confused.

## D4. Coverage needs two requests — the skill's own hop budget forbids that

§6: *"Coverage/oversubscription = demand ÷ size — demand is on the order object, size
on the tranche/deal object; request each and divide in your narrative."*

Honest, but "was the book covered?" is among the most common syndicate questions, and
answering it costs two round-trips (10–30 s) plus arithmetic the model does by hand —
against §0's "one request".

**`tranche_size` can be denormalised down onto the order object** without breaking the
grain contract (it is coarser than order grain, so it cannot multiply rows), exactly as
`tranche_name`, `currency` and `pricing_date` already are. Then coverage is a computed
metric on one object. Worth one column from the view owner.

## D5. The object-choice rule needs a sharper tie-break

§2 says **"Coarsest object that can answer wins"**, then immediately says "How many
deals did BlackRock buy?" is an **order** question — where deal is the coarser object.
The prose resolves it ("it filters an investor"), but the two sentences read as
contradictory and a model under pressure will apply the headline.

Suggested restatement, which is mechanical rather than judgemental:

> **The object must be fine enough to carry every field the ask FILTERS or PROJECTS.
> Among the objects that qualify, pick the coarsest.** The metric may count anything
> coarser than the grain — filtering an investor forces the order object, even though
> the answer counts deals.

## D6. §11 is missing the pipe-list *display* rule

§7 covers pipe lists for *matching* (position-aligned, contains not equality, never
cross-match by index). §11 has no rule for *rendering* them — and the production bug
was a rendering one: the model split `"CUSIP | FIGI | ISIN"` across table columns,
which shifted every subsequent column so `DEAL_ID` displayed "ISIN".

Add to §11: **pipe-list cells are atomic — never split across columns; zip aligned
type/value lists into pairs in one cell ("CUSIP 123456789 · FIGI 12345X"), and label
identifier answers by tranche.**

## D7. The "Incomplete Data" bullet is missing from Insights & Trends

§11 specifies 2–4 bold-labelled bullets ending in a judgement. Worth adding one more
sanctioned label: **"Incomplete Data:"** — what the answer could *not* show (NULL
buckets excluded, a column unpopulated for that product, a comparison that returned
nothing). It is the house form of the disclosure duties scattered elsewhere (null
regions dropped by a NOT-predicate, no-meeting orders excluded from "other than 1x1"),
and it gives them a consistent place to land instead of being improvised.

---

## What is excellent and should not be touched

- **The hop budget with its measured cost** (§0). Telling the model that a round-trip
  costs 5–15 s changes how it plans; an unpriced rule doesn't.
- **§10's finer-grain follow-up rule**, complete with the incident: *"this bug dropped
  two investors from a ranking under an unchanged header — do not repeat it."*
  Citing the failure makes the rule stick in a way an abstract instruction does not.
- **§11 count honesty** — all four members of the family (state = show, top-N reports
  found, buckets sum to total, a page's count describes the page). This was four
  separate fixes in v1; here it is one coherent paragraph.
- **§3's routing table resolving before the first tool call**, including "re-sort /
  re-explain data already in this chat → answer directly, no tool call". That is a free
  round-trip saved on a very common follow-up.
- **"Explicit labeled id → 0 rows means no data for that id, never substitute a
  lookalike."** Exactly the fabrication failure from v1.
- **"Ids are TEXT — always quote them; a trailing number in a name is part of the name,
  never an id."** Both production bugs, one sentence.
- **"Rating-agency names are never entities."** Non-obvious, and it prevents a wasted
  resolution hop.
- **§8's response-shape table**, particularly *"the fix is often 'this field lives on a
  different object, switch source'"* — that is the new failure mode this architecture
  creates, anticipated before it happened.
- **§7's `bnd_bank` preference over flag matching**, and the confirmation that
  `deal_sharing_type = 'SOLO'` now means true sole-managed.
