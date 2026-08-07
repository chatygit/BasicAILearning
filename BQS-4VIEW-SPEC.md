# Spec: migrate the ECM/DCM BQS ontology from one view to the four grain-aligned views

**Audience:** the agent working inside `176173.fulcrum.ecmo-capmkt-mcp`.
**Author:** the ECM/DCM agent team (text2sql generation), handing over the domain
knowledge accumulated over ~6 weeks of production traces.

You know this framework; I do not. **This spec is prescriptive about the domain and
the grain contract, and deliberately silent about BQS syntax** — you will discover your
own conventions from the existing code and preserve them. Where I describe a concept
("declare the grain"), express it the way your framework already expresses similar
things. Do not invent a new file format to satisfy this document.

---

## 0. Sequence — discover, propose, then build

Do these in order. **Do not write any YAML until step 0.3 is done.**

**0.1 Read your own framework.** At minimum:
`app/bqs/ontology/ecm_dcm.yaml` (the existing v1 ontology, in full),
`app/bqs/models.py`, `app/bqs/ontology.py`, `app/bqs/planner.py`,
`app/bqs/sql_builder.py`, `app/bqs/sql_validator.py`, `app/bqs/formatter.py`,
`app/bqs/suggestions.py`, `app/bqs/entity/zen_entity_search.py`,
`app/bqs/dialects/trino.py` + `base.py`, `adk/config/tools.yaml`,
`adk/skills/text2sql-ecm-dcm/SKILL.md`.

Answer for yourself, and state the answers in your output:
- Is one ontology file one physical object, or can one file declare several
  datasets/entities? **This decides whether the target is four files or one.**
- Can `run_bqs_query` name the object/source it targets? How does the agent choose?
- Does `sql_builder` know about grain — does it ever emit `DISTINCT` or `GROUP BY`
  on its own, or only what the request asks for?
- Can a plan span more than one physical object (joins)? If not, that is fine —
  the design below is deliberately join-free for ~95% of questions.
- Does the ontology support per-field metadata (descriptions, notes, allowed values,
  per-product applicability)? That is where most of §3 needs to live.
- Is `version:` a real switch — can `ecm_dcm@1` and `ecm_dcm@2` be served side by side?

**0.2 Introspect the four views. Do not trust column lists from any document,
including this one.** Query the catalog for the real objects and record, per view:
every column name, data type, nullability, and which columns look like grain keys.
The views were created recently and were modified from the original proposal, so
**the database is the only authority on their shape.**

**0.3 Produce a MIGRATION PLAN before any code**, containing: the framework answers
from 0.1, the real column inventory from 0.2, a mapping of every business term in the
v1 ontology to its new home (object + column), a list of v1 terms that no longer have
a home and why, and any place where this spec conflicts with what you found. **Flag
conflicts rather than silently resolving them.**

Then build.

---

## 1. Why this is happening

The v1 ontology maps everything onto one view whose rows are at **order grain** — deal
facts and tranche facts repeat once per order. A deal with 3 tranches and 91 orders
occupies 273 rows.

Consequences we measured in production:

| Symptom | Cause |
|---|---|
| A deal listing showed the same deal 3× (one row per tranche pricing date) | tranche facts at order grain |
| An investor ranking silently changed when the user asked to add deal name (totals split per deal, two investors dropped out of the top 15) | finer-grain column entering the grouping |
| A breakdown's buckets summed to 118 against a stated total of 114 | counting flattened rows |
| ~3 s floor on every query, 108 s on the DCM branch | `SELECT DISTINCT` over ~50 columns + a correlated subquery |
| 8 of 55 SQL validation rules; ~2.7k tokens of prompt doctrine | policing grain from the outside |

**The fix is structural: one object per grain.** Everything in §2 follows from that.

---

## 2. The grain contract

### 2.1 Four objects

| Object | Grain (what makes a row unique) | Answers |
|---|---|---|
| **deal** | one row per `PRODUCT` + `DEAL_ID` | "list deals", "how many deals", deal size/status/issuer/sector, offering type |
| **tranche** | one row per `PRODUCT` + `DEAL_ID` + `TRANCHE_ID` | tranches, coupon, tenor, identifiers, syndicate, ratings, exchange |
| **order** | one row per `PRODUCT` + `ORDER_ID` | investors, demand, allocation, order/IOI type, meeting type |
| **entity** | one row per named entity (investor / issuer / deal) | "which investor did you mean?" — name → id resolution |

Use the physical view names you found in 0.2, not names from this document.

### 2.2 The one rule that matters

> **Denormalise downward, never carry a finer grain upward.**

Deal attributes may appear on the tranche and order objects (they do not multiply rows
there). Tranche attributes must **never** appear on the deal object, and order
attributes must never appear on the deal or tranche objects. If a column violates
this, that is a view bug — report it, do not model around it.

This is what makes ~95% of questions single-object and join-free, which is the property
worth protecting above all others.

### 2.3 Declare the grain in the ontology

Each object should declare its grain keys in whatever way your framework supports, so
**the builder can guarantee one row per grain instead of relying on the agent to
remember**. This is the single highest-value change in the migration: it moves grain
from prompt discipline (which failed repeatedly) into code (which cannot forget).

If the builder cannot yet consume a grain declaration, still declare it, and specify
the builder change needed. Note it in the migration plan as a follow-up rather than
leaving the agent responsible.

### 2.4 Routing: which object answers which ask

The agent must pick the object before building a request. The rule is *the grain of the
thing being counted or listed*:

- mentions of orders, investors, allocation, demand, IOI, meeting → **order**
- mentions of tranches, coupon, tenor, identifiers/CUSIP, syndicate, ratings,
  exchange, maturity → **tranche**
- "deals", deal counts, deal size, issuer, sector, offering type, deal status → **deal**
- a bare name needing resolution to an id → **entity**

Ambiguous asks resolve to the **coarsest** object that can answer them. "How many deals
did BlackRock buy?" is an **order** question (it filters on an investor) that
aggregates `COUNT(DISTINCT deal_id)` — the grain is orders, the metric counts deals.
Getting this distinction into `usage_notes` and `examples` is important.

### 2.5 Cross-grain asks

Genuinely cross-grain questions ("investors in deals over $1bn") are rare. Prefer, in
order: (a) denormalised deal attributes already present on the order object — no join;
(b) a two-step where the first request returns ids used as a filter in the second;
(c) a join, only if your planner supports it. Say which of these you implemented.

---

## 3. Domain knowledge — you already have it; this is the delta

The domain vocabulary was handed over separately and much of it is already in the v1
ontology and SKILL.md. **Do not re-derive it.** This section covers only two things:
what the grain split forces you to re-home, and findings that post-date the hand-over.

### 3.1 Grain-relevant — these must move to the right object

| Concept | Belongs on | Why it matters here |
|---|---|---|
| Deal size, status, issuer, sector, offering type, use of proceeds | **deal** | if these stay at order grain the split has not happened |
| Tranche size, pricing, currency, coupon, tenor, seniority, maturity, ratings, regulatory category, ESG, exchange, product type | **tranche** | all vary per tranche — carrying any of them onto the deal object re-creates the duplicate-row bug |
| Syndicate lists (members, roles, broker codes, B&D flags) | **tranche** | syndicates are per tranche, not per deal |
| Identifier type/value | **tranche** | one identifier set per tranche; a multi-tranche deal otherwise shows "duplicate" CUSIPs |
| Investor, demand, allocation, order type, IOI type, meeting type, investor category/region | **order** | never on deal or tranche |

**Pre-computed aggregates on the deal object** (tranche count, first/last priced,
order count, investor count, currency list) are the mechanism that lets deal questions
stay single-object. Check in step 0.2 which of these the new views actually expose and
model exactly those — a metric the view does not carry must be reported, not faked.

**Units stay product-driven, not column-driven**: ECM quantities are security counts,
DCM the same fields are notional money. This is unchanged by the split, but it now has
to be declared per object rather than once.

**Per-product applicability must be declared per field** (equity/product type = ECM;
tranche status, coupon, tenor, seniority, ESG, maturity, ratings = DCM). With four
objects the planner can reject an impossible field/product combination up front instead
of returning an empty result — that is a real upgrade over v1, where it was prompt
discipline.

**Pipe-delimited lists remain aligned by position** and attribution must never be done
by matching two lists against each other. If the new tranche view exposes a **resolved
B&D bank column**, use it and retire the index arithmetic entirely — check for it.

### 3.2 Findings since the hand-over — verify these are present, add if missing

Each cost a production incident. If the agent already has one, leave it alone.

1. **Sole-managed vs Citi-led.** The deal-sharing field's ECM definition flagged SOLO
   whenever Citi held any lead role, ignoring syndicate size — **2,410 of 9,617 ECM
   tranches (25.1%) were mislabelled**. Check whether the new views fixed it. If not,
   ECM SOLO means "Citi-led"; derive true sole-managed from a single-member syndicate
   and state which reading the answer used.
2. **Identifier casing is per product** — DCM stores types lowercase, ECM uppercase.
   Compare case-insensitively on both sides, and match values by contains (they are
   multi-value on many rows).
3. **Ids are text.** Comparisons need quoted literals: unquoted numbers force a numeric
   conversion across every row (DCM ids contain letters → Oracle error), and unquoted
   investor ids lose leading zeros, silently selecting a different investor.
4. **Trailing windows need both bounds.** "Last 12 months" without an upper bound at
   tomorrow-midnight admits future-dated rows — the data contains 2027/2028 pricings.
   An upper bound at today-midnight instead drops everything priced today.
5. **There is no announced/created/launch date.** Only pricing and settlement. Never
   substitute pricing for "announced on"; say it is not tracked.
6. **An entity reference is one string.** A trailing number in a name ("Pacocha Group
   1783355563617") is part of the name, never an id. On a failed resolution, do not
   retry a decomposition — filter by the full name inline.
7. **Ids come only from a tool response or the user's message.** Anything else is
   fabrication, including ids that look plausible.
8. **Investor region mixes names and codes** — both `United States` and `US` exist,
   plus typo variants. Match name-contains OR code-equality; never contains on `US`
   (matches Russia, Austria). Negations are predicates, not stored values, and a
   NOT-predicate drops null-region rows — report how many were excluded.
9. **Region attaches to a noun**: "<region> deals" uses the deal's region; tranches,
   orders and bare mentions use the tranche's target region.
10. **Entitlement is a query constraint, not a routing hint** — no request may name an
    unentitled product, including inside an OR. **And entity resolution must be scoped
    too**: unscoped name lookups leaked cross-product entity names and counts to
    single-product users.
11. **Investor "classification" ≠ investor category** — a different, untracked
    taxonomy. Refuse and offer category rather than silently substituting.
12. **Exchange holds full venue names and sometimes abbreviations** — match both
    tokens, never equality.

Everything else from the hand-over (taxonomy vocabularies, the use-of-proceeds
shorthand map, meeting-type and order-type values, sector list, role expansions,
unsupported-intent list) is grain-neutral and should carry over unchanged. The
acceptance tests in §7 will surface anything that got lost in the move.

## 4. The entity object

Name resolution is the most latency-sensitive path — it runs *before* the user's real
question. Requirements:

- **Exact match first, then contains, then phonetic** — and the tiers must be gated:
  if an exact match exists, return only exact matches. This alone removes most
  disambiguation turns.
- **Do not run phonetic matching in the same pass as contains.** In production it cost
  ~19% of the runtime and added ~350 junk candidates to a single search. Use it only as
  a fallback when the contains pass returns nothing (or leave typo recovery to the
  existing fuzzy path).
- **Rank candidates by activity** — deal count and last-active date — so dormant and
  test entities sink.
- **Return enrichment for disambiguation**: id, deal count, last active, plus category
  and region for investors, sector and ticker for issuers, issuer and status for deals.
  The user picks from a list that means something.
- **Every candidate carries its id.** Options without ids are useless to the caller.
- Scope by entitlement (§3.10) and by the caller's product set.
- If the entity object is materialised with an index on the upper-cased name, say so —
  it changes the resolution strategy from "scan" to "seek" and is worth a lot.

**Fewest hops:** a metric or list ask that merely *names* an entity ("BlackRock's
allocations", "deals for Fidelity") should **not** call entity resolution at all — put
the name filter inline in the main request and group per entity, with ids in the
result. Reserve resolution for asks that need exactly one entity, for spelling
recovery, and for when the user asks to pick.

Bare umbrella names (blackrock, fidelity, vanguard) mean the **firm**, not one legal
entity: answer across the family, grouped, with ids shown, and offer the per-entity
breakdown. Disambiguate by *showing results*, not by asking.

---

## 5. Behavioural contract (SKILL.md deltas)

Only what changes or must not be lost.

**Grain routing (new).** The routing table from §2.4, as the first decision in the
loop. The object choice comes before the request body.

**Hop budget (new, measured).** Every tool round-trip costs the user 5–15 seconds. A
well-formed ask completes in at most: one resolution (only when entity-specific), one
request, one answer. Before every call: "do I already have this?" Answer **all** parts
of a multi-part question in **one** request. Never re-resolve an entity resolved
earlier in the session.

**On a rejection, apply the exact change named and nothing else** — never restructure
the request, never drop a filter. Blind retries cost another round-trip each; we
measured three attempts on one question, two of them wasted.

**Follow-ups.**
- "Also include X / add X / with their X / list those with X" keeps the previous
  request identical and **appends** the new field. Same rows, same order, same count.
- **If the requested field is finer-grain than the current aggregation** (deal name on
  a per-investor ranking), do **not** add it to the grouping — that silently changes
  what the answer means. Fold it in as a capped list (2–3 values plus "+N more") or
  return the count instead. We shipped this bug twice: an investor ranking's totals
  changed and two investors dropped out, under an unchanged column header.
- Re-grain only on an explicit breakdown request, and then re-title the answer,
  **relabel the metric column** ("Allocation on this deal", never "Total Allocation"),
  and state why the numbers differ from the previous list.
- A name or row the user picks **from a table we displayed** is already resolved —
  never re-resolve it.

**Presentation.**
- Data rows are a **table**, always. Numbered lists are for *choices* only.
- Every listing table starts with a `#` column of **absolute** row numbers that
  continue across pages.
- Ids (investor id, issuer id, deal id) are always present — they are the user's
  drill-down handles.
- Answer with a **quantitative brief** first (count, total with unit, range or
  concentration), then the table, then an **Insights & Trends** section of 2–4
  bold-labelled bullets ending in a judgement sentence, then follow-ups. Statistics for
  results larger than the displayed page come only from server-computed aggregates,
  never hand-summed from a sample.
- Banker conventions: money as "USD 2.1bn"; timestamps as dates ("25-Nov-2024");
  **table headers are business labels, never physical column names** (this is also a
  confidentiality rule); flags as words ("Yes", not "true"); empty values as "—".
- Never reveal physical schema, column names, or generated SQL, even if asked.

**Count honesty.**
- The number you state equals the rows you show, or the table says "showing N of M".
- A top-N ask returning fewer than N reports the **found** count, never the requested
  one.
- Breakdown buckets must sum to the stated total; a mismatch means the grain
  double-counts — fix it or state the overlap.
- Paging: a page's row count describes the page, never the dataset. Paging ends only at
  a known total or an executed short page — never by assertion.

**Failure honesty.** Never invent an id, a field, or an escalation path. Never end a
turn with no text. Never end a reply with a promise to come back later — deliver in the
turn or say plainly what blocked you. On zero rows for a valid question, say "no
matching records" plus one widening suggestion, and never delete the question's
defining filter to make something appear.

---

## 6. What the migration should delete

If the four-object model is working, these should become unnecessary. Their survival is
a signal that grain leaked back in:

- Any rule telling the agent to deduplicate, or explaining that a result list is itself
  the deduplication grain
- Warnings that particular fields vary per tranche and must be aggregated in deal
  listings
- The dedupe-inside/aggregate-outside pattern
- Grain-change disclosure rules for ordinary listings (still needed for deliberate
  breakdowns)
- Validation rules that exist purely to catch missing deduplication

Report which of these you were able to remove. That count is the migration's headline
result.

---

## 7. Acceptance

Verify each and report pass/fail with evidence.

**Structural**
1. Every object declares its grain; a request against an object returns one row per
   grain with no agent-supplied deduplication.
2. No object carries a field from a finer grain (§2.2).
3. Every business term in v1 has a home in v2, or an explicit reason it does not.
4. Every field's product applicability is encoded (§3.2).
5. The entity object is scoped by entitlement, and no request can name an unentitled
   product.

**Behavioural** — run these and check the shape, not just that something returned:

| # | Ask | Must be true |
|---|---|---|
| 1 | list deals in a sector for a period | one row per deal; no repeats for multi-tranche deals |
| 2 | top 10 deals by tranche size | tranche-grain object, or deal-grain with an explicit aggregate |
| 3 | top 15 investors by allocation, **then** "include deal name" | identical 15 rows, identical totals, deal names folded in |
| 4 | security identifiers for a multi-tranche deal | grouped by tranche; type/value zipped in one cell |
| 5 | Citi B&D deals for a year | resolved B&D field or token attribution — never role-list matching |
| 6 | solo deals | states which reading (sole-managed vs Citi-led) it used |
| 7 | orders for a deal with ~90 orders, then paging | absolute numbering across pages; ends at the true total |
| 8 | "deals priced in the last 12 months" | no future-dated rows |
| 9 | an entity ask as a single-product user | no cross-product candidates |
| 10 | "orders by investor classification" | refuses and offers category |
| 11 | any listing | brief → table (units in headers, ids present) → insights → follow-ups |

**Performance** — record round-trips and wall-clock for asks 1, 3 and 7, and compare
with v1. The target is fewer round-trips; the previous design took six for a
single-deal question, of which two were wasted retries.

---

## 8. Deliverables

1. The **migration plan** from step 0.3 (before code).
2. The ontology definitions for the four objects, in your framework's own idiom.
3. Any builder/planner changes needed for grain declarations and per-product
   applicability — as a diff with rationale, kept minimal.
4. The updated `SKILL.md` with §5's contract.
5. The updated entity-search path (§4).
6. An **open-questions list**: everything in this spec that conflicted with what you
   found, plus anything the views do not support that we assumed.

**Keep v1 runnable.** If the framework supports versioned sources, serve v2 alongside
v1 so both can answer the acceptance asks and be compared. If it does not, say so —
that changes the rollout from a flag flip to a cutover, which is worth knowing early.

---

## 9. Notes on judgement

- Where this spec and your codebase disagree about *framework* matters, your codebase
  wins — tell me what you did.
- Where they disagree about *domain* matters (§3), this spec wins: each item traces to
  a specific production failure. If something looks wrong, flag it rather than
  discarding it.
- Prefer encoding a rule as **structure** (grain declarations, per-product
  applicability, allowed values) over **prose**. Every rule we moved from prose into
  a mechanical check stopped recurring; every rule that stayed prose eventually got
  paraphrased away in a rewrite.
