# Capital Markets Agent — Latency Plan

**Date:** 2026-08-11 · **Baseline:** QA trace "Top 10 issuers by total deal size in DCM in 2024", **77.38s**, new views deployed.

Every number below is one of: **[M]** measured (trace, MCP log, or code I ran), **[E]** estimate with arithmetic shown, **[G]** guess. Claims cite `file:line`.

---

## 0. Provenance corrections that change the plan

Three inherited claims are wrong, and correcting them moves the ranking. I verified each myself.

**C-1. `tiktoken` IS installed** — at `/Users/babachaitanyakothapalli/AgenticApps/venv/bin/python` (v0.12.0), just not in the scratchpad venv or any system `python3`. The synthesis review's "F1 FATAL — none of the token numbers were measured" is itself incorrect. I re-ran the real `OntologySpec.discovery()` through cl100k_base and reproduce the corrected figures exactly:

| source | FULL tokens [M] | prose share [M] |
|---|---:|---:|
| `capital_markets_deal` | 10,277 | 42% |
| `capital_markets_tranche` | 14,100 | 40% |
| `capital_markets_order` | 7,968 | 53% |
| `capital_markets_entity` | 4,914 | 71% |
| **all four** | **37,259** | 46% |

MAP 1's 34,400 was ~8% low. `SKILL.md` = **12,136 tok / 44,579 chars** [M], exact. `static_instruction` (`agents.yaml:41-226`) = **3,068 tok** [M].

**C-2. The synthesis turn is NOT thinking-bound — and the repo already measured it.** `_review/ontology_check.py:769-772`:

> `# Event 10 of the 2026-08-09 trace: candidatesTokenCount 9,299 / thoughtsTokenCount 266, i.e. 67s of a 153s answer was the model typing 189 table rows`

**266 thinking tokens on a synthesis turn — 2.8% of that turn's output.** MAP 4's "thinking is 65–90s across four turns" and Lever D's "~5,800 hidden tokens per synthesis" are both refuted for synthesis.

**But the opposite is true for the decision turns.** `memory/ecm-dcm-v2-latency.md` records `thoughtsTokenCount` **2,269–3,135** attached to *"the 83s pre-MCP bucket (root turn 14s + load_skill 6s)"*. So:

> **Decision turns are ~98% hidden reasoning. Synthesis turns are ~3%.** Both camps were right about a different turn. This is what makes turn removal the top lever and thinking-budget tuning a low one.

**C-3. CyberArk is already fixed — do not re-bank it.** `memory/ecm-dcm-v2-latency.md` priced it at **13.2s** (10%) of the 136s trace, then: *"Old next-win, NOW DONE… Confirmed live: `CyberArk cache HIT for FID 'ecm_starburst_dev' (ttl=900s)`."* It is absent from the 77.38s trace. Any plan re-claiming it is double-counting a banked win.

---

## 1. LATENCY BUDGET — where the 77.38s goes

### 1a. The trace does not close, and that is the first finding

The five listed agent `call_llm` spans sum to **26+9+9+29+22 = 95s** against a `capital_markets_agent_v2` span of **74.67s** — **127% of its own parent.** The spans overlap, are rounded, or one is a duplicate. One decomposition closes to within 0.04s:

```
  2.65  askbanking_root_agent          (call_llm 2.56 + transfer_to_agent 750µs)
 26.0   call_llm  -> load_skill                          [643 MICROseconds of work]
  9.0   call_llm  -> discover_business_terms
  1.71  discover_business_terms tool                     (cold; 0.0038s warm)
  9.0   call_llm  -> run_bqs_query
 29.0   span = run_bqs_query execute 21.67 + synthesis ~7.3
------
 77.36  vs measured 77.38                                 ✓
```
The "~22s" fifth entry is a nested or duplicated child under the 29s span. **Confirm before publishing any number** (§6, T0).

### 1b. The budget, both readings

| Bucket | Literal (this trace) | Share | Central (see 1c) |
|---|---:|---:|---:|
| Root routing LLM | 2.65s | 3.4% | 2.65s |
| **3 × LLM turn that emits one function call and nothing else** | **44.0s** | **56.9%** | **21.6s** |
| Database (`execute` 21.67 + discovery cold-load 1.71) | 23.4s | 30.2% | 23.4s |
| Actual synthesis (writing the answer) | ~7.3s | 9.4% | ~7.3s |

**Under either reading, the largest single bucket is LLM time spent deciding which tool to call — not the database, not the answer.** That survives constraint 3 intact: it is entirely above the database.

### 1c. The 26s is an outlier — nine samples of the same work

The 26s figure drives every inflated estimate in the input maps. It is a 3–5× outlier against every other measurement of a tool-decision turn:

| sample | source |
|---:|---|
| 4.78s | MAP 3 debug-3/8 inter-tool gap |
| 5.40s | MAP 3 debug-11 |
| 6.0s | `memory/…v2-latency.md` — `load_skill` turn, 50s Blackrock trace |
| 7.09s | earlier 4-call trace |
| 7.42s | MAP 3 debug-5 |
| 8.78s | earlier 4-call trace |
| 9.0s, 9.0s | this trace |
| **26.0s** | **this trace — the outlier** |

Mean excluding the outlier: **57.47 / 8 = 7.18s** [M inputs]. The memory carries a standing instruction on exactly this: *"4× variance on identical work → get 2–3 more samples before touching thinking budgets."*

**I use 7.2s as the central cost of one tool-decision turn**, and quote 4.8–26s as the range.

### 1d. The realistic PROD floor, before any change

Only `execute` is volume-dependent. QA `vw_order_detail` = **5,874,386 orders** (`_diagnostics-results.md:769`); PROD is much smaller. The four non-outlier executes measured 2.21 / 3.01 / 3.90 / 4.48s → median **~3.5s**.

```
PROD today, central   = 2.65 root + 3 × 7.2 decision + 3.5 DB + 7.3 synthesis
                      = 35.1s          [E]
PROD today, literal   = 77.38 − (21.67 − 3.5) = 59.2s   [E]
```

> **The database contributes ~3.5s of a ~35s PROD ask — 10%. Everything else is model time. Do not spend effort below the database.**

---

## 2. RANKED PLAN — seconds saved ÷ implementation risk

Ranked on **PROD-relevant** seconds (volume-dependent savings discounted), divided by risk. `∅` = no view change, no DB change.

| # | Change | PROD seconds [E] | Risk | Class | Where |
|---|---|---:|---|---|---|
| **1** | Fold skill + names-catalog into `static_instruction`; delete the two mandates | **14.4** | med-high | NEEDS-CONFIRMATION | config |
| **2** | Tiebreaker rule + planner order-key synthesis | **6.2** | very low | DECIDED | prompt + `planner.py` |
| **3** | `BQS_MAX_RESPONSE_ROWS=50` | **0 normal / 17.7 worst** | very low | NEEDS-A-DECISION | env |
| **4** | P1 `currencies like '% | %'` pushdown idiom | **6.2 + DB** | very low | DECIDED | ontology YAML |
| **5** | Disambiguation: carry ids on free path + drop `eq` | **1.5–3.9** | low | DECIDED | `suggestions.py` |
| **6** | `d.alias` → `d.business_name` (paging crash) | 6.2 per occurrence | none | DECIDED | `planner.py:462` |
| **7** | Guard HAVING-without-GROUP-BY | 0 (correctness) | none | DECIDED | `planner.py` |
| **8** | Delete dead `computed_filters`/`derived_filters` docs from tool docstring | 0 (~400 tok) | none | DECIDED | `mcpserver.py` |
| **9** | Curated `values:` on closed code-lists only | 0 (removes probes) | low | DECIDED | ontology YAML |
| **10** | Model split → Flash on the build turn | 2.9–4.3 | med | NEEDS-CONFIRMATION | config |
| — | Micro-optimising the Python | **0.00007** | — | **DO NOT** | — |

---

### #1 — Kill two of the three tool-decision turns  · 14.4s [E] · med-high risk · ∅

**The mechanism.** Three turns produce zero reasoning. Each emits one function call whose arguments are already determined:

- `load_skill` takes a **literal constant**. Forced by `agents.yaml:48-55` (*"STEP 0 … MANDATORY … NEVER answer an ECM/DCM data question without loading this skill first"*). The tool executes in **643 microseconds** [M] behind a multi-second turn.
- `discover_business_terms(source=…)`'s argument comes from a routing table **already in the system prompt** — and `agents.yaml:63-65` admits it: *"Pick the object from the routing list in rule 2 (**it is right here; you do not need a tool call to choose**)."*

Both payloads are provably static. `domain_query_service.py:68-79` → `discovery()` (`ontology.py:294-378`) reads only YAML-loaded fields: no DB call, no user, no date, no entitlement filtering. Byte-identical for every user, every session, every turn.

**Arithmetic:**
```
2 turns × 7.18s (mean of 8 non-outlier samples)   = 14.36s
+ discover tool, warm                             =  0.45s
                                                  ─────────
central                                             14.8s   [E]
low anchor  (memory, Blackrock trace, direct)        9.0s
high anchor (this trace, de-nested ×74.67/95)       29.0s
```
**Report 14s central, 9–29s range.** Not the 35–37s the input maps headline — that figure is built on the single 26s outlier in a trace that overshoots its own parent by 27%.

**What to inline.** Not all 37,259 tokens of discovery. The complete name catalog for all four objects — every metric, dimension, filter with legal operators and curated values — is **~2,100 tokens** [M]. Everything else is prose that `SKILL.md` already duplicates (§7 duplication map: the stored-value vocabulary ships **3×**, the BQS request anatomy **4×**).

**Two rules that MUST survive the fold** or the saving reverses:
1. The ordering rule from `ontology.py:282-284` — *"'field' is the metric or a selected dimension"* — which is exactly what `planner.py:331-336` enforces. Drop it and you manufacture a `bad_order_field` rejection on every ranking ask. (This is #2; do #2 **first** so #1 cannot regress it.)
2. `SKILL.md:255-259` — COUNT metrics are unit-free, one request grouped by `product`.

**Cost the input maps understated.** This breaks **23 promote-gate sites** [M], not ~10: `has(SKILL,…)` ×15, `has(AGENTS,…)` ×5, `has(SKILLS,…)` ×2, `has(TOOLS,…)` ×1 in `_review/ontology_check.py` (181 checks total). Two fail by construction — `:552` (`"does NOT end your turn"`) and `:553` (`"discover_business_terms"`) — because they guard the exact prose this change deletes. **The gate encodes intent; when intent changes the gate changes with it, deliberately and in the same commit.** This is a config edit *plus* a reviewed gate amendment.

**Keep `discover_business_terms` as a tool.** Remove the *mandate*, not the tool. It stays as an escape hatch, and `mcpserver.py:467` uses it to warm the entitlement cache — dropping it moves one ECMO round-trip onto the first `run_bqs_query` (net-neutral, both serial; re-measure).

**Blocked on:** Q1 (Static Instruction field length cap) and Q2 (do the built-in `load_skill`/`list_skills` declarations persist after detaching `skills:`? — `tools.yaml:26-27` records a runtime error listing them as available in a run with an empty MCP toolset, so **expect them to persist** and write the negative instruction).

---

### #2 — The tiebreaker rule · 6.2s [E] · very low risk · ∅ · **DO THIS FIRST**

`planner._resolve_orders` (`planner.py:326-337`) allows only `{metric} ∪ projected dimensions`. But `agents.yaml:139-151` mandates *"END EVERY ranking or paged `order` WITH A UNIQUE KEY (deal_id / tranche_id / order_id / investor_id)"* — **with no instruction to also project it.** On any grouping that does not project that id, the mandated request is invalid by construction:

```
BQS rejected: Order field 'deal_id' must be the metric or a selected dimension.
Allowed: ['issuer_id', 'issuer_name', 'total_deal_size']
```

`SKILL.md:64` has the correct form (*"or a **projected** dimension"*); `agents.yaml` rule 8 does not. **Every top-N ask currently rides on the skill being loaded and obeyed** — which #1 removes. `_review/ontology_check.py:47-52` already encodes the right rule (`is_unique_at_grain`: must be in dims). The gate is right; the prose the model reads is not.

```
rejected hop = 0.27s transport + 5.9s LLM turn = 6.2s   [E, both M inputs]
worst observed repair turn (debug-6)          = 24.06s  [M]
```

**Two parts, ship (a) today:** (a) add *"…and put that key in `dimensions` too"* to `agents.yaml:139-151` — one clause, no dependency; (b) `planner.py` appends projected dims as trailing ASC keys instead of rejecting — the code already exists at `:461-463`.

---

### #3 — `BQS_MAX_RESPONSE_ROWS=50` · 0s normal / 17.7s worst · NEEDS-A-DECISION · ∅

This is **server enforcement of the one thing the repo has actually measured**, not a token trim. `_review/ontology_check.py:769` calls the row cap *"the largest single latency item measured."*

```
9,299 output tokens / 189 rows = 49.2 tok/row      [M]
9,299 output tokens / 67s      = 138.8 tok/s       [M]
                    →            0.354 s/printed row

server hands over today (formatter.py:20)  100 rows → 35.4s worst case
prompt cap (agents.yaml:169-171)            50 rows → 17.7s
                                                     ───────
                          bound on the failure mode   17.7s   [E]
```

**The asymmetry is the bug.** The server hands the model 100 rows; the prompt tells it to print 50. Every rule at that layer is *prompt-only* — `memory/…v2-latency.md`: *"everything hardened in the config layer is prompt-only; the server enforces only names/grain/entitlement/read-only."* Today nothing stops a 100-row table. Also removes ~6,200 input tokens per listing.

**Why NEEDS-A-DECISION, not DECIDED.** `_enrich_result` passes the **capped** records to disambiguation (`domain_query_service.py:189` → `formatter.py:36-37`). Halving the cap halves the sample `suggestions.py:362` counts distinct names from, so `len(names) <= 1 → continue` fires more often and the "you blended two BlackRocks" warning is silently suppressed more often. **Latency vs disambiguation coverage — your call.** Mitigation: ship with #5, which makes the free path carry ids and reduces reliance on the sample.

---

### #4 — The multi-currency pushdown idiom · 6.2s + DB · very low risk · **ontology YAML only**

**No input map ranked this, and it is the actual explanation for observation (d).** `views/_docs/_IMPROVEMENTS.md:138-147`:

> *"**`SPLIT` and `CARDINALITY` cannot push down to Oracle through the federation link, so the whole matched set crosses the wire before the threshold is applied** (TRACE — this is the shape of the 136s 'List all the multi-currency deals in the year 2024' run)."*

The fix is fully specified at `_IMPROVEMENTS.md:152-172`: replace `having: [{metric: currency_count, op: gt, value: 1}]` with a filter `{field: currencies, op: like, value: "% | %"}`. A pushable `WHERE` instead of a non-pushable `HAVING`.

It fixes **three things at once**: (i) the federation-pushdown blowup; (ii) the second hop, because the `HAVING`-shaped request is what triggers the rejection/retry; (iii) the silently-wrong-total defect — `metric=deal_count` + `having` + no dimensions compiles to `COUNT(DISTINCT …) … HAVING MAX(…) > 1` **with no GROUP BY**, returning *every* in-scope deal if any one is multi-currency (reproduced by two independent reviewers).

**Correctness precondition, already verified:** `_IMPROVEMENTS.md:176-180` — Q21 measured **6,940 DCM deals rendering `USD | USD | USD`** before the view rewrite; a pipe meant nothing. The new views confirm zero such deals, so a pipe genuinely means two distinct currencies. *This idiom is only correct because the views already shipped.*

---

### #5 — Disambiguation: stop paying for the second scan · 1.5–3.9s [E] · low risk · ∅

Measured: order/BlackRock `execute=3.01s` **`ENRICH=3.88s`** total 6.89s — the probe is **56% of the call** [M]. It issues `SELECT DISTINCT investor_name, investor_gp_id FROM vw_order_detail WHERE <same WHERE> … LIMIT 26`.

Two one-line gates delete the round trip rather than overlapping it:

**(a) The free path throws the ids away.** `suggestions.py:336-348` collects names only; `ids` (`:337`) is never populated on that branch, so `matched = [{"name": n, "id": ids.get(n)}]` (`:370`) yields `id: None` for every row — and the code falls to the probe. `_EntityFilter.id_column` holds the physical `investor_gp_id`; the projected business dimension `investor_id` maps to the *same* column (`capital_markets_order.yaml:287`). A reverse map `{d.column: business_name}` makes the id free. I verified all 7 `entity_name → entity_id_column` mappings: **every id column is also a dimension column**, so the map works. And `agents.yaml` already *mandates* the shape the fix needs (*"when you filter on a name also PROJECT its id in `dimensions`"*), gated at `ontology_check.py:760-764`. **The server pays a probe on exactly the shape the prompt requires.**

**(b) `_DISAMBIG_OPS` includes `"eq"`** (`suggestions.py:44` — `{"like", "eq", "in"}` [M]). So the probe fires on the *exact-name follow-up the system's own hint asks for* (`:387`, "re-run filtered to that single exact name"). Restricting to `{"like","in"}` removes it from every such hop, for one word.

**Do not count (a) and (b) separately — they are two fixes for the same hop.** Then re-measure `enrich=`; adopt concurrency **only if still >1s**, and only after someone confirms `execute_starburst_query` is thread-safe (`utils/starburst.py` is not in this tree — see §5).

---

### #6–#9 — free, ship with the next deploy

**#6 Paging crash.** `planner.py:462` builds `ResolvedOrder(column_alias=d.alias, …)` but `ResolvedDimension` (`planner.py:41-44`) has only `business_name`/`column` — **no `alias`** [M, verified]. Any `offset` with no `order` raises `AttributeError`, swallowed by `domain_query_service.py:275-284` into `internal_error` + *"do not retry"*. That is the exact flow `formatter.py:62-70` steers the agent into. One word: `d.business_name`. **Note:** the untracked `tests/test_response_paging.py` has 13 cases and **never calls `plan_query` with `offset`** — the feature ships with a test file that gives false confidence on the line that crashes. Add the case with the fix.

**#7 HAVING guard.** Reject `having` when `group_cols` is empty, in `planner._resolve_having` (`planner.py:345-387`). The rejection message is already written for you at `capital_markets_deal.yaml:124-126`.

**#8 Delete dead capability docs.** `mcpserver.py:526-535` spends ~180 tokens documenting `computed_filters` and `derived_filters` **with a worked recipe** — and I verified by grep that **neither is declared in any of the four ontologies** [M]. It is a live hallucination vector shipped on every request, and `agents.yaml:121-138` (rule 7, ~310 tok) exists largely to tell the model not to use what this docstring advertises. Delete both paragraphs, shrink rule 7: **~400 prefix tokens and one class of `unknown_computed_filter` rejection, gone.**

**#9 Curated `values:` — closed code-lists ONLY.** Today **6 `values:` declarations against 42 `suggestable: true` filters** [M, grep]. `values:` short-circuits the DB probe entirely (`suggestions.py:163-165`) and is advisory, not enforced — `planner._validate_filter` never checks it, so an unlisted legitimate value cannot be rejected.
**Enumerate:** `esg_bond`, `coupon_type`, `coupon_freq`, `delivery_type`, `seniority`, `reg_category`, `order_type`, `ioi_type`, `meeting_type`, `investor_region`, `deal_region`, `tranche_region`, `offering_type`, `deal_status`, `tranche_status` (~15).
**Do NOT enumerate:** `sector`, `use_of_proceeds`, `currency`, `exchange`, `product_type`, `product_class`, `equity_type`, `investor_category` — the ontology itself flags these as trap-laden (`capital_markets_deal.yaml:128-133`: `'Oil & Gas'` is separate from `'Energy'`; `'M & A'` has spaces) and `_diagnostics-results.md:519-546` shows `STATUS` holds 16 values *including case-variant duplicates* (`announced`/`Announced`). An incomplete enum on those makes real data unreachable.
**Cost to price:** `ontology.py:350` emits `values` into discovery → **+500–900 tokens** [E] on the catalog. This pulls against #1. Resolve the direction before both bank a saving.

---

### #10 — Model split · 2.9–4.3s [E] · NEEDS-CONFIRMATION

`gemini-2.5-flash` is a proven value on this platform (`V1/agent/entity-search-agent-v2.yml:9`). Scope is the **build turn only** — synthesis needs judgement.

```
one build turn on Pro (central)         7.2s
Flash 40% faster [G]                  → 4.3s, saves 2.9s
Flash 60% faster [G]                  → 2.9s, saves 4.3s
```

**Use `agent_type: SEQUENTIAL` (`agents.yaml:7`), never `transfer_to_agent`** — every transfer is an LLM routing decision measured at **2.56s** [M] in this very trace. A `transfer_to_agent`-based split makes the plan slower.

**Hard prerequisite — `requires_filters` is bypassed today.** `_entitlement_gate` mutates the request in place and appends a product filter at `mcpserver.py:406-416` *before* `plan_query` → `_check_required_filters` (`planner.py:433`), which tests **presence only**. **16 of the 20 `requires_filters` declarations are `[product]` — all 16 are unreachable.** Units currently rest on the model volunteering a product filter, i.e. on prompt compliance. Fix that before downgrading the model, or you lose the guard and the enforcement together. **Test protocol (from the memory, use verbatim):** run the UAT set on pro and flash and **DIFF THE GENERATED SQL** — every request logs `BQS(trino) executing: …` (`executor.py:246`). Objective, no human grading.

**Gate blind spot:** `has(AGENTS, phrase)` checks test the *whole file*, not a specific agent. Add a `capital_markets_agent_fast` sibling with a stripped instruction and **all 16 rule checks still pass** while the Flash agent carries none of them. Add a per-agent check first.

---

## 3. ABOVE-THE-DATABASE vs VIEW CHANGES

### Everything in §2 is above the database. **No view change is proposed.**

| Layer | Items |
|---|---|
| ADK config (`agents.yaml`, `tools.yaml`, `skills.yaml`) | #1, #2a, #10 |
| Skill file | #1 |
| Ontology YAML | #4, #9 |
| MCP server Python | #2b, #5, #6, #7, #8 |
| Environment variable | #3 |
| **Trino views** | **none** |

### The one view change that was tempting is already rejected — by the repo, on the right grounds

`_IMPROVEMENTS.md:793-799`, **R6 — a precomputed `CURRENCY_COUNT` column: ❌ REJECT**:

> *"Tempting: it turns `having currency_count gt 1` (non-pushable `CARDINALITY(SPLIT(...))`) into a pushable `WHERE`. But **P1** gets the same predicate pushdown with `currencies like '% | %'`, needs no column, no cycle and no exception. Prefer the lookup over the computation, and prefer the free one over the costed one."*

That is exactly the constraint-1 test, already applied and already passed. #4 is the above-the-database version of the same fix, at zero deploy cost against 2–4 days.

**The one ask where a view change stays competitive** is coverage/oversubscription (demand ÷ tranche size), because `TRANCHE_SIZE` is not at order grain (`capital_markets_order.yaml:133-138`). Adding it to `vw_order_detail` would fix it. **It still loses**, on three counts: it costs a 2–4 day deploy cycle; it fixes exactly one ask shape; and a server-side scope prefilter plus multi-metric support fixes four ask shapes for pure server-side work. **Do not schedule it. Revisit only if the scope prefilter is rejected.**

---

## 4. WHAT I AM DELIBERATELY NOT PROPOSING

1. **No materialized views, no indexes on views.** Explicitly out of scope per your constraint. Not proposed, not implied.
2. **No view-body change** (see §3).
3. **Nothing whose value exists only at QA volumes.** Specifically de-ranked:
   - The **"0-row probes cost up to ~100s"** headline. The 34.89s anchor is an unscoped `DISTINCT` scan over a view holding **5,874,386 QA orders** (`_diagnostics-results.md:769`) — the single most volume-dependent number in the system. It also uses k=3 when the author's own worked example has k=2 (`product` short-circuits at `suggestions.py:164`). **#9 drives k toward 1 by construction; that is the fix, not thread pools.**
   - The **"paging is 50× quadratic / 3.2MB"** claim. Real, but the waste is rows that will not exist in PROD.
   - **`C1b` speculative concurrency.** `saving = min(t_exec, t_probe)`; both terms shrink with volume, and the surviving portion depends entirely on a fixed per-query connect floor in `utils/starburst.py` — **which is not in this tree** (§5).
4. **No micro-optimisation of the request path.** I re-ran the shipping code: `model_validate` 3.0µs, `registry.get()` incl. `reload()` 41.7µs, `plan_query` 6.1µs, `build_sql` 7.6µs, `assert_read_only` 12.9µs — **~71µs total**, and `discovery()` rebuild 0.006–0.039ms. Memoising discovery saves **~0.3ms**. The memory already recorded this from the other side: *"`build`/`format`/`enrich` ≈ 0.00s — our Python is free."* **Do not spend a day here.**
5. **No thinking-budget change yet.** The one synthesis measurement says **266** thinking tokens (C-2), and the memory carries an explicit hold: *"4× variance on identical work → get 2–3 more samples before touching thinking budgets."* Ask the question (Q3); do not act on it.
6. **No `COUNT(*) OVER ()` / `total_rows`.** `grep -c OVER app/bqs/sql_builder.py` = **0** [M] — there is no window-function path. This is a new SQL-generation capability that must also be grain-correct under `MetricSpec.dedup_key` and `having`. Get it wrong and you ship a **server-blessed wrong total**, which is precisely what `formatter.py:84-89` and the count-honesty contract exist to prevent — now un-second-guessable by the model. Two maps also double-count its ~9.7s. **Defer.**
7. **No entitlement TTL increase / stale-while-revalidate.** Both widen the window in which a *revoked* ECM/DCM entitlement is still honoured. That is a security-posture change needing a named owner, not an env tweak, for ~1.4s once per 300s session.

---

## 5. METHOD LIMITS — state these when the plan is presented

- **`app/bqs/dialects/factory.py` and `app/utils/starburst.py` are not in this repo.** They exist in the deployed image. Consequence: `domain_query_service.py` and `executor.py` **cannot be imported in this tree** (`ModuleNotFoundError`). Any proposal touching them is a static design against an unrunnable file. Connection setup, pooling, TLS handshake and per-query auth cost all live there and I make **no claim** about them.
- **The 77.38s trace does not reconcile** (§1a). Every second in §2 that derives from it is provisional until T0.
- **`google-adk` and `fastmcp` are not installed here.** Built-in tool declaration sizes, the `(merged)` parallel-call semantics, and whether per-tool descriptions reach higher environments are all unverified.
- **The one measurement everything leans on** (`ontology_check.py:770`) is a **QA-scale event**: 189 rows. In PROD the same ask may return 20. #3's worst-case saving shrinks with it.

---

## 6. SEQUENCED ROLLOUT

Each step is chosen so the next is informed by data.

### Step 0 — measure, before publishing any number (½ day, zero code)
- **T0. Reconcile the trace.** Get non-overlapping span accounting for one ask. The 26s span is the single largest input to every estimate and it belongs to a trace that overshoots its parent by 27%. Get 2–3 more traces whose spans actually sum.
- **T1** (`_LATENCY-TESTS.md:12-24`) — *"How many DCM deals priced in 2024?"*, a one-row answer. If synthesis stays 25–45s it is output/thinking-bound; if it drops to 5–10s it is input-bound. **This decides whether #3 is worth anything.**
- **T2** — same question twice in one session. If turn 2's first `call_llm` drops, a prefix cache already exists and #1's caching benefit is partly spent. If not, nothing is being reused.
- **T5** — per-call `promptTokenCount` / `thoughtsTokenCount` / `cachedContentTokenCount`. **Partly answered already** at `ontology_check.py:770`; get one more synthesis turn and one decision turn to confirm the 266-vs-2,700 split (C-2). *If these are not exposed anywhere, that is itself a finding: nobody can attribute model cost today.*

### Step 1 — the free correctness fixes (1 day, ship together)
#2a (one clause in `agents.yaml`), #6 (`d.business_name` + the missing test), #7 (HAVING guard), #8 (delete dead capability docs), #4 (the `'% | %'` idiom).
**Measure after:** re-run the multi-currency ask and the top-10-issuers ask. Expect the `bad_order_field` rejection hop and the federation blowup to disappear. Re-run `_review/ontology_check.py` (181 checks) and `V1/regression_check.py`.

### Step 2 — the server fixes (2–3 days)
#5 (free-path ids + `_DISAMBIG_OPS`), #2b (planner order-key synthesis), #9 (closed-list `values:` only).
**Measure after:** the `enrich=` phase timer in the `BQS timing` log line. If `enrich` is now ~0, the concurrency work is unnecessary — **do not build the thread pool.** Also re-measure the discovery payload; #9 inflates it by 500–900 tok and that pulls against Step 4.

### Step 3 — ask the platform team (parallel, blocks Step 4)
All of §7 in one email. **Q1 and Q2 block #1; Q5 blocks #10.**

### Step 4 — the big one (1 week, gated on Step 3)
#1, with the gate amended in the same commit. **Do #2 first** so the fold cannot regress the ordering rule.
**Measure after:** turn count per ask (should be 2, not 4), and `promptTokenCount` / `cachedContentTokenCount` on turn 1. If `cachedContentTokenCount` is non-zero, a byte-identical prefix generator becomes worth building; if it is zero, **do not build it** — it is machinery serving an unproven benefit.

### Step 5 — #3 and #10, both decisions, both informed by Step 0
#3 needs your call on the disambiguation trade. #10 needs the `requires_filters` bypass fixed first, and T1's answer to know whether the build turn is worth splitting.

---

## 7. OPEN QUESTIONS

### NEEDS-CONFIRMATION — stack capabilities nobody has verified

| # | Question | Blocks | Why it matters |
|---|---|---|---|
| **Q1** | **What is the maximum length of the Static Instruction field** in the Ask Banking onboarding UI? | **#1** | The fold is ~15–33k tokens pasted by hand. `README.md`: higher environments do not read `adk/config/*` — promotion is a manual paste. If the cap is small, fold only §0/§0b/§2/§6/§7b/§11. |
| **Q2** | Does the platform support **session-start auto-load of an attached skill**? And do the built-in `load_skill`/`list_skills` declarations persist after dropping `skills:`? | **#1** | If auto-load exists, #1 costs a config flag and no paste at all — the cheapest possible version, and nobody has asked. If the built-ins persist, a model that calls `list_skills` out of habit burns the turn we just removed; write the negative instruction. |
| **Q3** | Is **context caching** enabled on our `gemini-2.5-pro` deployment (`agents.yaml:38`)? Does the gateway pass `cached_content`? Is `cachedContentTokenCount` ever non-zero? | sizing #1 | Decides whether a 33k prefix is cheap or expensive. **Book zero seconds against caching** — it is an enabler for #1's turn removal, not a saving. |
| **Q4** | Is **`thinking_budget`** or any thinking-level control exposable per agent? Is `max_output_tokens`? | — | No `generate_content_config`, `thinking_budget`, `max_output_tokens`, `temperature` or `top_p` exists in any config file [M, grep]. Given C-2 the payoff is on decision turns; if #1 lands, most of it is already gone. |
| **Q5** | Can an **`agent_type: SEQUENTIAL`** entry carry a **different `model:` per child**, with MCP tool results flowing between steps? | **#10** | The only shape where a model split costs zero extra routing turns. Live precedent: `opportunity_insight` in `V1/reference/agents-tools-skills.txt`. |
| **Q6** | What does **`execution_mode`** take, and what does the default do with a multi-tool turn? | **#1** | `agents.yaml:12` documents `single_turn # handles the request in one LLM call (default)` — contradicted by a trace with 4–5 `call_llm`. Open since `REVIEW-07 G6`. #1's design is "two turns"; resolve first. |
| **Q7** | Is **streaming** enabled end-to-end (runner → chat surface)? | — | ~27–30s of **perceived** improvement, **0s actual** [E]. Take it if it is a flag; never count it as a saving. **Do not stream thoughts** — confidentiality (`SKILL.md:616-620`). |
| **Q8** | Is `execute_starburst_query` **thread-safe / re-entrant**? Does `starburst.py` open a connection per query? | any concurrency | Not answerable in this tree (§5). A fixed per-call connection floor would show as a floor near the 276ms minimum execute. |

### NEEDS-A-DECISION — tradeoffs only you can make

| # | Decision |
|---|---|
| **D-A** | **#3 row cap: 50 or 100?** Bounds the worst case at 17.7s instead of 35.4s, at the cost of a smaller disambiguation sample (`suggestions.py:362` fires `continue` more often, suppressing the "two BlackRocks" warning more often). |
| **D-B** | **Has the ontology + SKILL promote (`_DEPLOY-ORDER.md` step 3) actually happened?** The brief says new views are deployed. If the ontology is still the old one, the trace is measuring a mismatched pair and #4 is already partly live. |
| **D-C** | **Is a 4-turn agent that never mis-routes worth 14s more than a 2-turn agent that occasionally does?** #1 trades the model's ability to re-read authoritative field names at runtime for a static prefix. `SKILL.md:25-29` currently makes discovery authoritative over the skill's own lists. |
| **D-D** | **Who owns the entitlement TTL decision?** Not proposed (§4.7), but it will be raised again as a ~1.4s win. It is a security posture change. |

---

## 8. THE HONEST FLOOR

**After everything in §2, on `gemini-2.5-pro`:**

```
root routing LLM (transfer_to_agent)              2.65s   [M] — platform, not ours
one build turn (emit run_bqs_query)               7.2s    [E] — irreducible on Pro
database (PROD, median non-outlier execute)       3.5s    [E]
synthesis (writing the answer)                    7.3s    [E]
                                                 ───────
                                                 20.7s
```

**With #10 (Flash on the build turn):** 7.2 → ~4.3s → **~17.8s**.

This matches the memory's independent conclusion from the other direction: *"Two turns are irreducible (emit query, render answer) and cost ~10s on `gemini-2.5-pro` before the DB. **15s requires a faster model.**"*

### What it would take to go below ~18s

Everything left is a platform change, not a repo change:

1. **Delete the root routing turn (2.65s, 13% of the floor).** Requires the Ask Banking orchestrator to route deterministically — by pattern, entitlement, or a sticky session — rather than by an LLM call over agent descriptions. Not ours to change, and worth asking for: it is a pure LLM call with one obvious answer.
2. **Collapse build + synthesis into one turn.** Only possible if the model can emit the query and the prose in one pass, which means predicting the answer shape before seeing the rows. Not realistic for tabular answers.
3. **A materially faster model for the build turn** — Flash gets part way; anything below ~3s per turn needs a small model, and small models are exactly what the `requires_filters` bypass makes unsafe today.
4. **Streaming**, which does not lower the floor but moves the first visible token to ~10s and changes what "slow" feels like.

> **Bottom line: 77s → ~35s in PROD with no changes at all (the DB shrinks), → ~21s with this plan, → ~18s with a model split. The last 18s is three LLM turns and one query, and only the platform team can remove any of them.**
