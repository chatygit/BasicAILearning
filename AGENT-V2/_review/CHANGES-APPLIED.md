# AGENT-V2 — changes applied 2026-08-07

The six review documents (REVIEW-01…06) found 25 defects. This pass **applied**
them to the files rather than describing them, and added a regression check so
they cannot silently come back.

Run before handing anything back to the POC repo:

```
python3 AGENT-V2/ontology_check.py     # 659 checks, exit 0 = safe
```

Mutation-tested: 54 deliberate reintroductions of old bugs, 54 caught.

The Python server files live under `AGENT-V2/app/`, mirroring the repo layout,
so they can be edited here and copied back **as-is** — they carry no
transcription banners or review-artifact labels, only ordinary engineering
comments. `entitlement_scope_test.py` is standalone evidence for the gate fix
and runs with no dependencies.

**They came from screenshots — `diff` each against the real file before copying
back.** That warning lives here, deliberately, and not inside the files.

---

## 1. Units guard — the "1,000.0bn shares" class

`requires_filters: [product]` now on **every** aggregate over a column whose unit
depends on product.

| File | Metrics newly guarded |
|---|---|
| deal | `largest_deal_size`, `smallest_deal_size` |
| order | `total_allocation`, `max_allocation`, `average_allocation`, `total_demand`, `max_demand`, `total_order_amount`, `max_order_amount` — **the object had none** |
| tranche | all five size metrics + `syndicate_member_count` |

ECM is share counts, DCM is notional money; an unguarded `MAX` compares
40,000,000 shares against USD 40,000,000 and picks a winner. The order object is
where this actually reached a user.

> **Answered by `planner.py` (§17): it IS enforced** — `_check_required_filters`
> raises `missing_required_filter`. The guard is real. One caveat: it checks the
> field is PRESENT, not that it scopes to a single value, so
> `product in [ECM, DCM]` satisfies it. That is precisely what the old
> entitlement gate injected, which is why the gate fix (open item 1) is the
> load-bearing half.

## 2. Unique tiebreakers — rankings and paging

Every example `order:` now ends on a key unique **at its result grain**
(`deal_id`, `tranche_id`, `order_id`, `investor_id`, `entity_id`), and the rule
is stated in each object's `usage_notes` and in SKILL §6.

The "paged listing" example on the order object was rewritten: it sorted on
non-unique `investor_name` (unstable pages — rows repeat or vanish) **and**
aggregated instead of listing. It now projects `order_id`, `order_allocation`
and `order_demand_qty` and sorts `investor_name, order_id`.

## 3. Entity resolution — two hops down to one

The exact-then-fallback contract was replaced with **one contains request,
ranked, limit 10**. Users type partial names, so the exact tier missed by
construction and the "fallback" was the common path — on the hop that runs
*before* the real question, against a 5–15 s round-trip budget.

Also: the misspelling claim was honest-ified (contains matching cannot recover a
true typo — retry once, then ask), `context_value_1/2` now carry a
label-by-entity-type rule, and the issuer example gained the `product` filter the
investor example already had.

> **Ask the view owner for `MATCH_RANK`** on `VW_ENTITY_SEARCH` (0 = exact,
> 1 = prefix, 2 = contains). That restores v1's single-query tiering as a plain
> `order` field. Noted in the file.

## 4. Stored-value traps — given a home

The ontologies declared `values:` for only `product` and `entity_type`, so every
taxonomy trap was homeless. Each now lives in the relevant filter's
`description` (which ships with the catalog) **and** in a new **SKILL §7b**
table:

`1x1` · `M & A` (spaces) · `Refinance` + `Debt Repayment` · `Oil & Gas` ≠
`Energy` · `Open`/`OPEN` · lowercase DCM identifier types · `10-YEAR` ·
`Fixed to FRN` · `SEC Registered(Public)` · full exchange venue names ·
`Common Shares`/`Common Stock` · `United States`/`US` and the `%US%` trap.

Descriptions were used rather than `values:` lists. **The stated reason was
wrong and the conclusion still holds — for a better reason.** I assumed
`values:` might be *validated*, so an incomplete list would reject legitimate
queries. `ontology.py` shows it is not validated at all: it is a **curated list
that suggestions are ranked against *instead of* a live `DISTINCT` probe**. So
an incomplete list doesn't reject anything — it silently makes `did_you_mean`
worse, by replacing real values with our partial guess. Same verdict: only add
`values:` for an enum we know is complete (`product`, `entity_type`,
`deal_sharing_type` — all already declared). **When we do learn a complete enum,
adding it is a pure win: zero live queries.**

> **`suggestable: true` DOES fetch live `DISTINCT` values — but only on a 0-row
> result.** So it is a *recovery* mechanism, not a *prevention* one, and it
> splits the trap table in two:
> - **Zero-row traps rescue themselves** (`One-to-One`, `%M&A%`, `10Y`, `NYSE`,
>   `Fixed-to-FRN`) — the server returns the real value and the agent retries.
> - **Wrong-population traps have no safety net** (`Energy` missing
>   `Oil & Gas`, `Refinance` missing `Debt Repayment`, `%US%` matching Russia,
>   `Open`/`OPEN` splitting buckets) — rows come back, nothing fires, the answer
>   looks right.
>
> That distinction is now in SKILL §7b. It is the more useful framing: it tells
> the agent which mistakes it can recover from and which it cannot.

## 5. B&D and syndicate attribution

- **"Non-B&D" is now two predicates, not a negated participation.** Final form,
  matching the server's own docstring verbatim: `"non-B&D"` =
  `bill_and_deliver` with `negate` (**token-less**); `"Citi non-B&D"` =
  `syndicate_member` token `citi` **plus** `bill_and_deliver` with `negate`.
  Negating *participation* excludes nearly every tranche on a Citi book — a
  production zero-result. Worked example on the tranche object, stated in
  SKILL §7 and in the agent instruction.
  *(This took two corrections: first written with `bnd_bank not_like`, which
  `models.py` showed does not exist (§13); then with a token passed to
  `bill_and_deliver`, which `mcpserver.py` showed is token-less (§15). `negate`
  is also the better tool than `ne` because it handles NULLs correctly — §14.)*
- **New `role_attribution` unsupported intent**: `syndicate_role` is
  position-aligned with the member list, so the compiler cannot say *which* bank
  held a role. Matching the two lists independently produces confident false
  attributions. The refusal comes with a plan B (members and roles side by side).
- `syndicate_member_count` marked **ECM-only** — DCM exposes just the B&D bank,
  so the count is always 1 there.
- `deal_sharing_type = 'SOLO'` now asserted as true sole-managed (fixed
  upstream), with `syndicate_member_count = 1` kept as the independent
  cross-check.

## 6. Null disclosure — made executable

`investor_region`, `deal_region` and `tranche_region` gained
`is_null`/`is_not_null`. The ontology instructed the agent to "say how many
null-region rows were excluded" while giving it no way to count them — a rule the
config asks for but does not enable is worse than no rule.

Row-level threshold filters were also added on `order_allocation`,
`order_demand_qty`, `order_amount` and `tranche_size` — "orders larger than 1m
shares" is a row predicate and had no filter (only a HAVING on the total).

## 7. Taxonomy contradiction resolved

The order object described `investor_category` as "Investor **classification**"
while its own `unsupported_intents` said classification is a different untracked
taxonomy. The dimension now says **category** only; the word "classification"
appears solely in the refusal, which now also carries *why* (its values —
Strategic, Family Office, Retail, SWF, DSP, Index, Quant — do not appear in
category at all, so substituting returns a wrong population, not an approximate
one).

## 8. Time windows

`how_to_use` on the deal object said "add an upper bound at **today**" while
`usage_notes` said "lt **tomorrow-midnight**". The first drops everything priced
today. All four files and SKILL §9 now say tomorrow-midnight, and the check fails
if "upper bound at today" reappears.

## 9. SKILL.md

- §2 object-choice rule restated mechanically: *the object must be fine enough to
  carry every field the ask FILTERS or PROJECTS; among those, pick the coarsest* —
  the old headline ("coarsest object wins") contradicted its own BlackRock
  example.
- §7b trap table (new, see 4).
- §11: **pipe-list cells are ATOMIC** — never split across columns; zip aligned
  type/value lists into one cell. This is the bug that made DEAL_ID display an
  ISIN.
- §11: **"Incomplete Data:"** added to the sanctioned Insights labels, giving
  every disclosure duty in the skill one consistent place to land.
- §6: unique-tiebreaker rule; listing-vs-aggregate rule.
- §10: drill-down reuses the id from the previous response — never re-search.
- §4: one-request resolution.
- Never-do list gained: never rank/page without a tiebreaker, never split a pipe
  list across columns.

## 10. tools.yaml — the real survival kit

Tool definitions ship with **every** request regardless of which skills loaded,
how long the conversation ran, or whether the model re-read the catalog. In this
architecture that makes the tool description the most reliable rule surface, so
it now carries the four rules whose absence yields a *wrong* answer rather than a
failed one: pick by grain · always scope product · never total shares and money ·
ids are text.

`mcp_tool_names` pinned to `[discover_business_terms, run_bqs_query]` instead of
`[]` — a governed read-only surface should not silently grow when a tool is added
to the server.

## 11. skills.yaml

`skills.yaml` said "load it alongside `ontology-text-to-sql`"; `SKILL.md` front
matter said self-contained. Self-contained is right and is now asserted in both
(v1 proved skill loading is discretionary — a prose-only dependency between two
skills doubles the failure surface). The generic skill now points ECM/DCM asks at
the specific one. Added `metadata.ontology_version: "2"` for trace attribution.

## 12. agents.yaml (review 07)

The survival kit **already existed** and is the best structural decision in v2 —
a nine-point CORE CONTRACT in `static_instruction` that restates grain routing,
product scoping, units, metric routing, B&D and date windows without the skill.
Changes:

- **Removed the instruction to leak the ontology.** It said *"State which object
  (source), metric, dimensions, and filters you used"* — directly against the
  skill's confidentiality rule, and it loads on every turn while the skill may
  not. Replaced with a deferral to the skill's house style, a minimal fallback,
  and a CONFIDENTIAL clause that now covers internal *field* names too.
- **Added the rules that produce *wrong* answers** rather than failed requests:
  ids are text, no fabricated ids, unique tiebreakers, tomorrow-midnight, the
  two-predicate non-B&D, roles are not attributable, the worst value traps,
  pipe cells stay atomic, count honesty, never end a turn with no text.
- Object-choice rule restated mechanically, matching SKILL §2.
- Added *"discovery is per-SESSION knowledge"* — free win if it currently fires
  per turn.

Confirmed from this file, not inferred: `skills:` attaches **only**
`text2sql-capital-markets`, so the old *"load it alongside `ontology-text-to-sql`"*
instruction was unsatisfiable. The self-contained fix was correct.
`ontology-text-to-sql` now has no consumer — attach or drop it.

Not changed, deliberately: `execution_mode` is unset and documented as
*"one LLM call"*. A normal turn here is three or more. See REVIEW-07 G6.

## 13. The BQS contract — `models.py` corrected two of my own edits

Reading `app/bqs/models.py` invalidated part of the pass above. Both are fixed,
and both are now checked:

- **There is no `not_like` operator.** `FilterOperator` is exactly
  `eq ne gt gte lt lte in not_in between like is_null is_not_null`. My non-B&D
  recipe used `bnd_bank not_like '%CITIGROUP%'` in four places — it would have
  been rejected at runtime. The governed negation is a **`computed_filter` with
  `negate: true`**, which `BQSComputedFilter` documents with this exact example.
  Rewritten as `broker_participation('citi')` + `bill_and_deliver('citi',
  negate)`. *(New `[VERIFY]`: does `bill_and_deliver` accept a token? If it is
  token-less, negating it means "no B&D at all" — a different population.)*
- **`operators:` lists are now whitelisted against the enum**, so no file can
  declare an operator the compiler doesn't implement.

Confirmed correct: `order` takes multiple keys (every tiebreaker is valid),
`having` exists with comparison operators, filters are a flat ANDed list with no
OR (the exchange and investor-region rewrites were right for the right reason).

Newly documented in SKILL §0b and the agent instruction:

- **`source` is `Optional` and defaults to "the single configured source."** In
  a four-object world an omitted `source` silently answers from the wrong
  object. Always set it.
- **Exactly ONE `metric` per request.** A second figure is a second request —
  which is *why* coverage costs two. Values to display rather than aggregate go
  in `dimensions`.
- **`time_grain`** (`day`/`week`/`month`/`quarter`/`year`) buckets time
  server-side. Any "by month"/"trend" ask should use it instead of pulling raw
  dates and grouping by hand — one request, correct buckets.
- **`derived_filters`** exist: token-less governed predicate names from
  discovery (e.g. `settlement_currency_mismatch`). Read what discovery offers
  before hand-building an equivalent.

## 15. `mcpserver.py` — a correction, a token win, and a server bug

Full analysis in `REVIEW-08-mcpserver.md`.

**I was wrong that discovery cannot be scoped.** The signature is
`discover_business_terms(source: str | None = None)`. I inferred "no arguments"
from the agent instruction and the tool description — both describe the *call
site*, not the *tool*. Corrected in REVIEW-07 and here.

**The fix is config-only and now applied.** The agent already carries the
four-object routing table in its own instruction and in SKILL §2, so it can pick
the object with **no tool call at all**, then fetch exactly one catalog:
`discover_business_terms(source="capital_markets_order")`. That is the two-stage design,
using the routing table we already ship as the thin index. A wrong pick costs one
extra scoped call — still far cheaper than four catalogs on every turn.

**`bill_and_deliver` is token-less**, and the `run_bqs_query` docstring documents
the composite recipe in the same words we independently arrived at. Our version
passed it a token; corrected everywhere.

**`mcp_tool_names` pinning is now justified by evidence** rather than principle —
the server also registers `tool_echo_user_context`, a diagnostic that returns the
caller's resolved SOEID. Auto-discovery would have offered it to the agent.

**And the server bug (item 1 below):** the entitlement gate drops the agent's
`product` filter and replaces it with the caller's full entitlement. For a
dual-entitled user, "ECM deals in 2025" silently becomes ECM **and** DCM — which
means `total_deal_size` sums share counts with notional money. Every units guard
we added is satisfied (a product filter *is* present) and none of them help. This
is the one finding no config change can address.

## 16. We now own the server code — `AGENT-V2/app/`

Transcribed from screenshots into the repo's own layout so they can be edited
and copied back:

| File | Status |
|---|---|
| `app/bqs/models.py` | faithful transcription, no functional change |
| `app/bqs/sql_builder.py` | faithful transcription, no functional change |
| `app/bqs/planner.py` | faithful transcription + two inline `REVIEW P1/P2` notes on `_check_required_filters` |
| `app/bqs/ontology.py` | faithful transcription, no functional change |
| `app/services/domain_query_service.py` | faithful transcription + inline notes |
| `app/bqs/suggestions.py` | faithful transcription + two perf notes |
| `app/mcpserver.py` | **one behavioural change**, marked `# <<< FIX 1 >>>` — the entitlement intersect. Three fail-open paths marked `# <<< OPEN 1/2/3 >>>` and deliberately left alone |

**Diff each against the real file before copying back** — these came from
screenshots, so whitespace and anything off-screen may differ. All four parse
cleanly (`ast.parse`).

`entitlement_scope_test.py` proves FIX 1 across eight cases with no
dependencies; three of the eight were silently widened by the old code, and all
three are the ordinary dual-entitled shape. `ontology_check.py` now runs it and
also fails if the fix, the enforcement, or the `OPEN` markers disappear.

## 17. `ontology.py` — the last unknown, and one correction

Full detail in `SERVER-CONTRACT.md` §13.

**Correction: `values:` is not validated.** I said we avoided `values:` lists
because an incomplete list might *reject* legitimate queries. Wrong — it is a
curated list that suggestions are ranked against *instead of* a live `DISTINCT`
probe. A partial list doesn't reject anything; it silently degrades
`did_you_mean` by replacing real values with our guess. Same conclusion, better
reason — and when we do learn a complete enum, declaring it is a pure win (zero
live queries). Now enforced: only `product`, `entity_type` and
`deal_sharing_type` may declare `values:`.

**Correction: an omitted `source` fails cleanly.** I said it would "silently
answer from the wrong object". `resolve()` only defaults when exactly ONE source
is registered; with four it raises `Missing 'source'. Available sources: [...]`.
Still always set it — but the cost is a wasted round-trip, not a wrong number.
(Also useful: `deal`, `tranche`, `order`, `entity` each resolve uniquely via
sub-scope matching, while `ecm` is ambiguous across all four.)

**`grain` exists to retire `dedup_key`** — *"For a grain-aligned view (one
physical row per grain) value metrics need no dedup_key."* Our four objects
declaring `grain` and no `dedup_key` is the intended design, confirmed at source.

**HOT RELOAD changes how we ship.** `get()` calls `reload()` on every request and
re-reads any YAML whose mtime changed. **Ontology changes go live without a
server redeploy** — a real break from v1, where a promote meant an app restart.
It also means a bad YAML is live just as fast, so running `ontology_check.py`
before every copy is not optional. Now checked as behaviour, not as a comment.

**`BQS_ENABLED_SOURCES`** is an allow-list; a source not listed is loaded and
then ignored. **All four object names must be in it.** Promote-checklist item.

**Quantified cost of unscoped discovery:** `_generic_how_to_use()` — ~10 lines of
source-agnostic instructions — is prepended to *every* source's `how_to_use`. A
no-argument `discover_business_terms()` returns that block **four times**, on top
of four full catalogs.

**Unused feature worth asking about: `as_of_date`.** A source can declare a
governed availability query; the server then returns `as_of_date` on every
response so the agent renders *"Data as of: &lt;Month YYYY&gt;"* instead of
guessing. None of our four declare it, and "how current is this?" is a question
bankers actually ask.

## 18. `domain_query_service.py` — one landmine, three confirmations

**DEPLOYMENT LANDMINE — `BQS_ENABLED_SOURCES` (open item 0 below).** The
allow-list is an **exact match** on each ontology's `source`. The four-view
migration renamed the single `capital_markets` source into **four**. If that env var (or
`settings.bqs_enabled_sources`) still says `capital_markets`, all four objects are loaded
and then **silently ignored** — discovery returns nothing and every query fails
to resolve a source. Nothing in the config can detect it; the fix is one
environment value, and it belongs on the promote checklist before anything else.

**Confirmed: the zen-API path is not ours.** `ENTITY_SOURCE =
"revenue_returns_entities"` — only a source with that exact name is served from
zen. `capital_markets_entity` goes down the normal SQL path against `VW_ENTITY_SEARCH`,
which is the design intent.

**Confirmed: the suggestion contract, authoritatively.** `_enrich_result` calls
`build_suggestions` **only** when `row_count == 0`, and `build_disambiguation`
**only** when it is non-zero. Enrichment failures are swallowed. This is the code
that makes SKILL §7b's split correct — a filter returning the *wrong* rows gets
no help at all.

**Confirmed: `sql_audit` carries the generated SQL into the agent-visible
response.** The confidentiality rule is load-bearing, not theoretical — the SQL
is in the payload. SKILL §8 now names the field.

Two smaller notes left inline: the `invalid_request` message repeats the
misleading *"'source' is optional (defaults to the single configured source)"*
(`REVIEW S4` — wrong in a four-source deployment), and the no-argument discovery
path re-scans the ontology directory once **per source** because `registry.get()`
reloads each time (`REVIEW S3`).

## 19. `suggestions.py` — two rules that are pure upside

**A 0-row answer costs MORE than a good one.** `_build_distinct_probe` runs
`SELECT DISTINCT <col> … WHERE UPPER(col) LIKE :stem` against the **whole base
view** — it carries neither the request's `product` filter nor its date range,
and the `UPPER()` defeats any plain index. That runs **once per suggestable
filter** in the failed request, on top of the original query. Getting the value
right first time is now a *performance* rule in SKILL §7b, not only an accuracy
one.

**Projecting the name field you filter on makes disambiguation free.**
`build_disambiguation` has two paths: if the entity-name field is already in
`dimensions`, it counts distinct names **from the rows it already returned** —
no query. If not, it runs a bounded `DISTINCT` probe. Same block either way; one
costs a round-trip and the other costs nothing. Now stated in SKILL §5, and it
also happens to be what lets the answer *show* the user which entities got
blended.

Other mechanics worth knowing: `_stem()` keeps the longest alphanumeric token
minus two characters (so `BLACKROCKK` still retrieves `BLACKROCK…`); ranking is
rapidfuzz `WRatio` with a **score floor of 60** and **top 5** returned; probes
are capped at **200** distinct values and disambiguation lists at **25**;
curated `values:` skip the probe entirely — which is the second reason a
complete enum is worth declaring.

## 20. POST-DEPLOY: two bugs the deployed config still had

Both found after the copy-over, both now fixed in this tree.

**(a) `usage_notes` item parsed as a MAPPING, killing the entity source.**
`- ONE request: contains-match…` is *valid YAML* that loads as a `Hash`, so
`usage_notes: list[str]` failed pydantic validation, `_refresh_file` logged and
skipped, and **`capital_markets_entity` was never registered**. One missing pair of
quotes removed a whole object. The gate missed it because it only checked that
the YAML *parsed* — it did. Now checked structurally: any unquoted prose-list
item containing `": "` fails. Swept all four; that was the only instance.

**(b) The four objects declare NO `computed_filters`, but the config told the
agent to use four of them.** `broker_participation` / `syndicate_member` /
`bill_and_deliver` / `syndicate_role_lead` were referenced in SKILL §7, agent
rule 7, the tranche `how_to_use` and a *worked example* — and
`planner._resolve_computed_filter` raises `unknown_computed_filter` for every
one. The four-view split dropped v1's `computed_filters` block; I then rewrote
the non-B&D recipe *onto* those filters after `mcpserver.py` documented them as
the governed path, which made the breakage worse.

Rewritten to what actually runs today: filter participation with
`syndicate_member_name like '%CITIGROUP%'`, **project `bnd_bank`**, split
billed/not-billed in the answer. Both wrong turns are now explicitly prohibited
in all three places — never negate participation (structural zero on a Citi
book), never use `bnd_bank ne`/`not_in` (silently drops the *no B&D recorded*
rows that a non-B&D answer is partly about).

New referential-integrity check: no example may name an undeclared computed
filter, and neither the skill nor the agent instruction may recommend one
without stating it is unavailable.

> **Port the `computed_filters` block from the v1 `capital_markets.yaml` into
> `capital_markets_tranche.yaml`.** It is worth real effort: a computed filter is the
> ONLY place this system can express an **OR** (an alias's codes are OR-joined
> into one regex) and the only **NULL-safe negation**. That single block would
> fix non-B&D properly *and* give us the clean form of the exchange, refi and
> USA value traps. Port it rather than re-deriving — a wrong regex fails
> silently by matching the wrong rows.

---

## Still open — not config fixes

| # | Item | Who |
|---|---|---|
| 0 | **`BQS_ENABLED_SOURCES` must list the four new source names** (or `*`). It is an exact-match allow-list and the migration renamed `capital_markets` into four. If stale, all four objects load and are silently ignored — discovery returns nothing. Check this FIRST | deploy |
| 1 | **THE ENTITLEMENT GATE DISCARDS THE USER'S PRODUCT FILTER.** A dual-entitled user who asks for ECM gets ECM+DCM, and size/allocation metrics then sum shares with money. One-line fix: intersect `requested` with `entitled` instead of replacing. **No config change can work around this.** REVIEW-08 H2 | POC team — urgent |
| 2 | Three entitlement fail-open paths: import failure skips the gate, gate-ok-with-no-products runs unscoped, and `RUN_MODE` defaults to `"local"` which disables it. Decide which should fail closed; put `RUN_MODE` on the promote checklist. REVIEW-08 H3 | POC team |
| 3 | ~~Does discovery return all four catalogs?~~ **Resolved, and better than expected: `discover_business_terms(source=...)` is scopeable.** The `(no arguments)` call was a config choice. Two-stage discovery is now applied — the agent picks the object from its own routing table, then fetches ONE catalog. Still worth **measuring `promptTokenCount`** before and after to size the win | us — applied |
| 4 | ~~Is `requires_filters` enforced?~~ **Resolved: YES, it raises `missing_required_filter`.** The units guard is real. Caveat: it checks the field is PRESENT, not that it scopes to ONE value — which is exactly why item 1 is load-bearing | resolved |
| 5 | ~~Does `suggestable: true` fetch live DISTINCTs?~~ **Resolved: YES — but only on a 0-row result.** Recovery, not prevention. It rescues typo/casing traps; it cannot rescue a filter that returns the WRONG rows. SKILL §7b now splits the trap table on exactly that line | resolved |
| 6 | ~~Does `bill_and_deliver` accept a token?~~ **Resolved: token-less.** The `run_bqs_query` docstring documents the composite verbatim — `"Citi non-B&D" = syndicate_member "citi" plus bill_and_deliver with negate`. Our files now match it exactly | resolved |
| 7 | Which `derived_filters` exist? They may already cover recipes we wrote by hand | POC team |
| 8 | `execution_mode` semantics — does the default support a multi-tool turn? | POC team |
| 9 | `MATCH_RANK` column on `VW_ENTITY_SEARCH` → one-hop exact-first resolution | view owner |
| 10 | `TRANCHE_SIZE` denormalised down onto `VW_ORDER_DETAIL` → coverage becomes single-object. Legal at that grain (coarser), like `tranche_name`/`currency` already are | view owner |
| 11 | **Function-based indexes on `UPPER(col)`** — every case-insensitive filter compiles to `UPPER(col) op UPPER(?)`, so plain b-trees are unusable on ~25 filtered columns across the four views. Or normalise the values (`Open`/`OPEN`) so case-insensitivity isn't needed. Added as an addendum to `QA-FINDINGS-FOR-DATA-TEAM.md` | data team |
| 12 | Every `[VERIFY]` marker in `capital_markets_tranche.yaml` — the file is a draft written to the other three objects' conventions, not introspected from the physical view | user |

## 14. `sql_builder.py` — what it confirmed, and one trap it revealed

Recorded in `SERVER-CONTRACT.md` with the verbatim extracts. Summary:

**Confirmed real and correctly declared** — `case_insensitive` (wraps both sides
in `UPPER`), `numeric: true` (emits the cast that VARCHAR-backed measures need —
the v1 `TRANCHE_SIZE` type mismatch), `list_count: true` (counts the pipe list,
deliberately uncast), `time_grain` (`date_trunc` into SELECT and GROUP BY),
`computed_filters` (regex over one governed column, pattern bound as a
parameter), `derived_filters` (server-authored column-vs-column predicates).

**Negation is well-defined, including NULLs.** The regexp helper COALESCEs NULL
to a non-matching sentinel, so `NOT(...)` correctly returns rows with no B&D
flag as "non-B&D". That is why `negate` is the right tool and `ne` is not — `ne`
would silently drop exactly those rows.

**ORDER BY sorts on output aliases**, so a sort field must be the metric or a
projected dimension. The tiebreaker rule is a hard compiler constraint, not a
style preference.

**The trap: there is a `dedup_key` mechanism, and `HAVING` is rejected on any
metric that uses it** (*"plain path only; the planner rejects HAVING combined
with a deduplicated metric"*). No metric in the four ontologies declares
`dedup_key` — correct, because grain-aligned views are the whole premise. But
our `currency_count` and `syndicate_member_count` examples both rely on
`HAVING`, so **adding a `dedup_key` to either would silently break them**. Now
checked. And if a metric ever genuinely needs `dedup_key`, that is evidence the
view is not at its claimed grain — fix the view, not the ontology.

New checks added for all of this: value aggregations must declare `numeric:
true`, and no `dedup_key` metric may appear in a `having:`.
