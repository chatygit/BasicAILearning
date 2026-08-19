# ECM/DCM four-object redesign — final summary

**Date:** 2026-08-10 · **Gates at hand-back:** `_review/ontology_check.py` **934 passed / 0 failed**,
`V1/regression_check.py` **206 passed / 0 failed**.
**Executable check:** all 30 declared ontology examples and all 11 spec §7 acceptance
asks plan through the real `planner.plan_query` and compile through `sql_builder.build_sql`.

Governing principle applied throughout: *the domain knowledge is finite; the lazy
solution wins.* Every rule that could be a list of values is a list of values; every
runtime computation that could be a pre-computed column is one; every instruction that
could be a worked example is one.

---

## 1. What changed, per file

### `views/vw_*.sql` — the physical truth (prior batch)
Four views rewritten and validated. All four now **hold their declared grain**, which
is the change everything else depends on.

| View | Grain | Now holds | Value fixes |
|---|---|---|---|
| `vw_deal_summary` (22 cols) | product + deal_id | ECM 18,399 rows = 18,399 deals (was 22,347) | DCM currency list deduped (6,940 deals showed `USD \| USD \| USD`) |
| `vw_tranche_summary` (39) | product + deal_id + tranche_id | ECM 33,010 = 33,010; DCM 36,370 = 36,370 | `TRANCHE_SIZE` text→NUMBER (E-notation preserved), `SECURITIES_MATURITY` string→DATE, `TENORS` bare hyphen→NULL, `DELIVERY_TYPE` list→scalar, `BND_BANK` now the full co-B&D list, identifier lists zip-aligned |
| `vw_order_detail` (20) | product + order_id | ECM 48,302 = 48,302; DCM 5,826,084 = 5,826,084 (was 11.9m rows for 5.87m orders) | DCM allocation now reads `OB_ORDER.FINAL_ALLOC` — it was reporting **zero** on the busiest tranches |
| `vw_entity_search` (8) | entity_type + product + entity_name + entity_id | grain re-declared to match reality | none — body unchanged this batch |

### `app/bqs/ontology/*.yaml` — four objects
Rewritten against the new views, then adversarially reviewed (33 defects found and
fixed across the four files before this pass). Highlights: the deal roll-ups became
**filterable**, per-product applicability became an enumerated lookup, the B&D index
arithmetic was retired in favour of the resolved `bnd_bank` column, and every value
list was mined from `V1/domain/` rather than re-derived.

### `adk/skills/text2sql-capital-markets/SKILL.md`
Rewritten as a routing + vocabulary layer over the four catalogs. 13 defects found and
fixed before this pass, including three factual errors about server behaviour (the
50-row default, truncation flagging, the settlement-currency predicate).

### This final pass — 17 cross-file fixes

| # | Conflict | Files | Resolution |
|---|---|---|---|
| 1 | **ECM `deal_status` vocabulary differed three ways** — deal 14 values, tranche 17, SKILL 14, for the *same source column* | deal, tranche, SKILL | Unified to **15**. `Executed` ADDED everywhere (V1 files it under execution status, and on ECM `deal_status` *is* the execution-status value). `Mandated`/`Private` REMOVED from tranche: V1 files them under DCM and Q17's complete DCM measurement contains neither, so they were attested on neither product |
| 2 | **`settlement_currency` meant two things** — "the currency the DEAL settles in" vs "the TRANCHE settles in" | deal, tranche, SKILL | One meaning (tranche-level). Deal object now discloses it is a `MAX()` collapse, so a deal with two settlement currencies shows one |
| 3 | Same field **`suggestable` on tranche, not on deal**, on a column both call a placeholder | tranche | Aligned to not-suggestable: a 0-row result no longer buys an unscoped `DISTINCT` on a column that may have nothing to suggest |
| 4 | **`tranche_count`/`order_count`/`investor_count` name two different measures** (pre-computed deal-card column vs live COUNT DISTINCT) with no single place saying so | SKILL §2 | Stated once, in the routing section read before the request is built |
| 5 | Every deal-object scalar is a `MAX()` collapse; only 2 of 12 disclosed it | deal | One `usage_note` enumerating all 12, with the 6 genuine roll-ups excluded by name |
| 6 | `requires_filters` is **invisible in `discovery()`** (verified: metrics emit only aggregation + description); 16 metrics carried an undocumented rejection | deal, tranche, order | One `usage_note` per object listing exactly which metrics are rejected without a `product` filter, and which are unit-free |
| 7 | SKILL asserted "Roadshow = anything other than No Meeting" as fact; order object calls it an interpretation to disclose | SKILL | Aligned to the order object |
| 8 | `exchange` ASX expansion: SKILL `%AUSTRALIAN%` vs tranche `%AUSTRALIA%` | SKILL | `%AUSTRALIA%` (strict superset) |
| 9 | SKILL §7b called deal `currencies` "ISO codes", contradicting its own §7c and the deal object | SKILL | Split the bullet: `currency` is resolved ISO on both products; ECM `currencies` is an identifier column |
| 10 | `esg_bond` negation trap (NULL is the majority; `ne 'GREEN'` drops every ordinary bond) was in tranche only | SKILL | Added — it returns rows, so nothing warns |
| 11 | SKILL said `product_type` is "`like` only"; the filter offers `in`, the only OR this framework has | SKILL | Reconciled |
| 12 | SKILL §3 routed "\<region\> DEALS" → `deal_region` with no note that it is ECM-only on the deal object | SKILL | 1-line qualifier at the routing table (first match wins, so §7b was too late) |
| 13 | SKILL "drop a blank name" conflicted with the entity object's family rule, and was dead advice (the mandatory name filter already excludes NULL names) | SKILL | Rewritten with the family exception |
| 14 | `use_of_proceeds` shorthand maps diverged (deal had working-capital and recap; tranche did not) — same column, same vocabulary | tranche | Aligned, marked identical |
| 15 | `(true)`/`(false)` suffix-strip rule (V1, production) survived in the tranche object only | SKILL | Added to §7 |
| 16 | SKILL quoted bare QA counts (`4,808`, `42`) in agent-surfaced text, against the diagnostics' "existence proof, never sizing" rule | SKILL | Softened |
| 17 | **Version skew** — deal/tranche `"2"`, order/entity `"3"`; `version` is emitted in `discovery()` and used nowhere else | all four | Unified to `"3"` |

Plus one **capability gap closed**: SKILL §10 told the agent to "fold the field in as a
capped list" on a grain-unsafe follow-up but never said how, and no metric can do it.
Replaced with the executable recipe (re-request with the finer field pinned by the ids
already held; keep turn one's totals; use the new rows only as a name source). This is
acceptance ask #3 — a bug that shipped twice.

**Verified clean, mechanically, after the edits:**
- **19/19 shared vocabularies are now byte-identical** in every file that carries them
  (sector 28, use_of_proceeds 19+3, deal_status ECM 15 / DCM 16, product_class 15,
  seniority, reg_category, coupon type/freq, delivery, esg, identifiers, equity_type,
  investor_category 21, investor_region, meeting_type, Citi broker codes, tranche_name).
- **Per-product applicability: 23/23 hard-NULL columns correctly tagged** in their own
  object, checked against the `CAST(NULL …)` placeholders in the three view branches.
  The only two untagged columns (`SETTLEMENT_TS`, tranche `EXECUTION_STATUS`) are
  deliberately unmodelled.
- No unsupported-intent id collides with a real field name on its object.
- 30/30 examples and 11/11 acceptance asks plan and compile.

---

## 2. What was DELETED — the headline result (spec §6)

Spec §6: *"If the four-object model is working, these should become unnecessary. Their
survival is a signal that grain leaked back in. Report which of these you were able to
remove. That count is the migration's headline result."*

| Spec §6 class | V1 | V2 | Evidence |
|---|---|---|---|
| Rules telling the agent to deduplicate, or that the result list is itself the dedup grain | **6** SQL-validation rules + per-column prose | **0** | grep over all four objects + SKILL returns only *prohibitions* ("never deduplicate") |
| Warnings that fields vary per tranche and must be aggregated in deal listings | 1 rule + prose on 14 columns | **0** | structurally impossible — no tranche column is on the deal object |
| The dedupe-inside / aggregate-outside pattern | prescribed by rule 288 | **0** | — |
| Grain-change disclosure on ordinary listings | present | **0** | retained only for deliberate breakdowns, which spec §5 requires |
| Validation rules existing purely to catch missing dedup | **6 of 55** | **0** | — |

**Deletion count: 9 governed rules retired**, and the layer they lived in went from
**55 rules to 1**.

- **6** pure grain/dedup rules: deal-level aggregate without dedupe · IPO listing
  without dedupe · ECM/DCM listing without dedupe · no self-join of the flattened view ·
  `COUNT(id)` needs DISTINCT · deal listing must collapse tranche-varying columns.
- **3** more retired by the view rewrite rather than the grain split: solo-via-DISTINCT
  syndicate-member-count (`DEAL_SHARING_TYPE` is now correct at source, on both
  products), naive whole-field `BND_BROKER` equality, and the inline-suffix
  `BND_BROKER` **index arithmetic** (`REGEXP_SUBSTR`/`INSTR` position maths) — all
  replaced by the resolved `bnd_bank` column. The *display* half of the suffix rule
  survives deliberately: strip `(true)`/`(false)` before showing a member name.
- **55 → 1.** `V1/domain/sql-validation-v2.yml` had 55 regex rules policing
  agent-authored SQL. `app/bqs/sql_validator.py` is 43 lines with one function,
  `assert_read_only`. The agent cannot author SQL at all now, so the whole layer is
  inapplicable, not merely thinner. The ~2.7k tokens of grain doctrine spec §1 measured
  in the prompt are gone from the three data objects.

**The one surviving dedup instruction is on `capital_markets_entity`, and it is correct, not a
leak.** That view really does return one row per *name variant* (Q28: 124,668 rows for
9,871 DCM investor ids), and the object declares that in its grain
(`[entity_type, product, entity_name, entity_id]`). It is disclosed, not policed.

---

## 3. Acceptance walkthrough (spec §7)

Structural 1–5 and behavioural 1–11. **All 11 behavioural asks are answerable.**
Requests marked ✅ were executed through the real planner and SQL builder.

### Structural

| # | Requirement | Result |
|---|---|---|
| 1 | Every object declares its grain; one row per grain, no agent dedup | **PASS** — all four declare `grain:`; the three data views are measured 1:1; entity's 4-part grain matches its GROUP BY |
| 2 | No object carries a finer-grain field | **PASS** — deal carries no tranche/order column; tranche carries no order column; order carries only `deal_id/deal_name/tranche_id/tranche_name/currency/pricing_date` |
| 3 | Every v1 term has a home or a stated reason | **PASS** — the exceptions are enumerated as `unsupported_intents` (17 across the four objects) plus `SETTLEMENT_TS` and `EXECUTION_STATUS`, both deliberately unmodelled with the reason inline |
| 4 | Product applicability encoded per field | **PASS** — 23/23 hard-NULL columns tagged; enumerated as closed lists in each object's `how_to_use`. **Caveat:** it is *prose*, not enforced — `DimensionSpec`/`FilterSpec` carry no product field, so an impossible combination returns 0 rows instead of being rejected (open question 7) |
| 5 | Entity scoped by entitlement; no request names an unentitled product | **PASS** — the gate injects the product filter on every request including entity resolution |

### Behavioural

| # | Ask | Object · fields | Queries | Result |
|---|---|---|---|---|
| 1 | List deals in a sector for a period | **deal** · `deal_count` + `deal_id, deal_name, issuer_name, sector, deal_status, last_priced`; filters `product`, `sector in ['Energy','Oil & Gas']`, `last_priced` gte/lt | **1** ✅ | **PASS** — one row per deal by construction; multi-tranche deals cannot repeat |
| 2 | Top 10 deals by tranche size | **tranche** · `total_tranche_size` grouped by `deal_id, deal_name, currency`; `tranche_size gt 0` | **1** ✅ | **PASS** — tranche-grain object with an explicit aggregate, exactly as the spec allows. Only possible because `TRANCHE_SIZE` is a real NUMBER now |
| 3 | Top 15 investors by allocation, **then** "include deal name" | **order** · `total_allocation` + `investor_name, investor_id` → follow-up re-request with `deal_name` added and `investor_id in [15 ids]` | **1 + 1** ✅ | **PASS with a caveat** — identical 15 totals preserved (turn one's server aggregates are kept; the re-grained rows are used only as a name source). The follow-up is a second *turn*, not a second hop. See §4 |
| 4 | Security identifiers for a multi-tranche deal | **tranche** · `tranche_count` + `tranche_name, tranche_id, identifier_type, identifier_value` | **1** ✅ | **PASS** — grouped by tranche; the two lists are zip-aligned in the view (value tiebreaker added) and displayed zipped into one cell |
| 5 | Citi B&D deals for a year | **tranche** · `deal_count` + `bnd_bank like '%CITIGROUP%'` | **1** ✅ | **PASS** — resolved B&D field. Role-list matching is refused by the `role_attribution` intent |
| 6 | Solo deals | **tranche** · `deal_count` + `deal_sharing_type eq 'SOLO'` | **1** ✅ | **PASS, and the ask is now obsolete in its original form.** The spec asked the answer to *state which reading* it used because ECM SOLO meant "Citi-led" and mislabelled 25.1% of tranches. The view now checks syndicate size on **both** products, so SOLO means "Citi was the only syndicate member". The wording duty survives ("Citi-solo", never "sole-managed") because a tranche solely managed by another bank still reads `SHARED` |
| 7 | ~90 orders for a deal, then paging | **order** · `order_count` + row-level dims, `limit 50`, then the identical request with `offset` | **1/page** ✅ | **PASS** — `truncated`/`next_offset`/`paging` are emitted by the formatter; absolute numbering continues across pages; paging ends on a known total or an executed short page |
| 8 | Deals priced in the last 12 months | **deal** · `last_priced gte start` **and** `lt tomorrow-midnight` | **1** ✅ | **PASS** — both bounds are mandated in all four files and gate-asserted; no future-dated rows |
| 9 | Entity ask as a single-product user | **entity** · `max_activity` + the four filters + six dims + `limit 10` | **1** ✅ | **PASS** — entitlement scopes resolution; no cross-product candidates. Usually **0** queries: the default is to filter the name inline on the data object |
| 10 | "Orders by investor classification" | refusal | **0** | **PASS at the prompt layer only** — see the note below |
| 11 | Any listing: brief → table → insights → follow-ups | presentation contract, SKILL §11 | n/a | **PASS** — units in headers, ids always present, 50-row cap, three doors |

**Ask #10 — the one thing not enforced in code.** `planner._check_unsupported` matches
intent ids against *field names*, and `BQSRequest` carries no natural-language question,
so the server cannot see the word "classification". The refusal comes from the
`unsupported_intents.patterns` surfaced by `discovery()` plus SKILL §3b. Verified: the
`investor_classification` intent carries 6 patterns and is gate-asserted. It is a
prompt-layer guarantee, and it should be described as one.

---

## 4. Hop audit

Unit = **`run_bqs_query` round-trips**, matching spec §5's "one resolution, one request,
one answer". `discover_business_terms` is one additional call per *object per session*
(SKILL §0 requires it scoped to one object and never re-fetched).

| Ask | Query round-trips | Over budget? |
|---|---|---|
| 1 list deals in a sector | 1 | no |
| 2 top 10 by tranche size | 1 | no |
| 3a top 15 investors | 1 | no |
| 3b "include deal name" (new user turn) | 1 | no |
| 4 identifiers per tranche | 1 | no |
| 5 Citi B&D | 1 | no |
| 6 solo deals | 1 | no |
| 7 orders for a deal | 1 per page | no |
| 8 last 12 months | 1 | no |
| 9 entity resolution | 1 (usually 0 — inline) | no |
| 10 classification refusal | 0 | no |
| 11 any listing | 1 | no |

**No acceptance ask needs more than one request.** Against v1's six round-trips for a
single-deal question, two of them wasted retries.

What made that true, in order of contribution: (a) deal attributes denormalised onto the
tranche object, so status/region/sector/purpose/issuer scoping is free; (b) the deal
roll-ups became **filterable**, so "deals with more than one tranche", "100+ orders",
"multi-currency" cost zero hops; (c) `bnd_bank` resolved at source; (d) inline name
filtering replacing entity resolution; (e) `TRANCHE_SIZE` becoming numeric, which is
what makes ask #2 a single request at all.

### The four structural 2-hop classes that remain

None is an acceptance ask, but three are common. All four trace to just **two** framework
limits: *exactly one metric per request*, and *no OR / no column-vs-column predicate*.

| Class | Cost | Cause | Cheapest fix |
|---|---|---|---|
| **Coverage** = demand ÷ tranche size | 2 requests, 2 objects | size is not on the order object | **Denormalise `TRANCHE_SIZE` onto `vw_order_detail`.** Legal at that grain (spec §2.2 — deal/tranche attributes may travel downward). This is the single highest-value remaining view change |
| **Fill rate** = allocation ÷ demand | 2 requests, same object | one metric per request | A `ratio`-style metric, or accept it |
| **Order ask scoped by sector / issuer / deal status** | 2 requests (deal → ids → order) | those columns are not on the order object | Denormalise `ISSUER_NAME`, `GFCID`, `SECTOR` onto `vw_order_detail` — same argument as coverage |
| **Exchange abbreviation retry** | up to 2 | filters are ANDed; no OR exists | Port the v1 `computed_filters` (an alias's tokens are OR-joined into one regex). Also the only NULL-safe negation, which collapses the two-step non-B&D recipe to one request |

---

## 5. Open questions — human decision required

**Measurement, one query each. Each currently forces a hedge in the files.**

1. **ECM `currencies`: ISO codes or identifiers?** `vw_deal_summary` LISTAGGs
   `TRANCHE_CURRENCY_ID`, which `vw_tranche_summary` joins as a lookup *key* to get
   `CURRENCY_NAME`. So `currencies like '%USD%'` may silently return zero on ECM. Today
   the shorthand is scoped to DCM only. One `SELECT DISTINCT` makes "ECM deals that
   priced in USD" a one-hop answer, or confirms it must stay on the tranche object.
2. **`SETTLEMENT_CURRENCY` population, either product.** Modelled on two objects as a
   real capability but never measured; the views team treats it as a placeholder. One
   `COUNT(*)` decides whether it is a field or an `unsupported_intent`.
3. **DCM population of `SECTOR` and `DEAL_REGION`.** Both wired on the DCM branch of the
   tranche view; neither measured. Today a 0-row DCM sector answer cannot be
   distinguished from "not captured", so the agent must hedge every one.
4. **Canonical `TENOR_PERIOD` spelling** (`Y` vs `YEAR`, `M` vs `MONTH`). Every tenor
   recipe currently hedges with the short token `%10-Y%` to catch both.
5. **ECM `deal_status` vocabulary.** The 15 literals are carried from V1 and have never
   been measured; DCM's 16 are measured and complete (Q17). One `DISTINCT` closes the
   last unverified enumeration in the system.
6. **Agency literals inside `ISSUER_RATINGS`** (`Moody's` vs `Moodys` vs `MOODYS`) — the
   file instructs matching a short stem because the spelling is unknown.

**Design decisions, not measurements.**

7. **Enforce per-product applicability in the planner.** The 23 hard-NULL fields are
   correctly enumerated but only in prose, so an ECM-only field under `product='DCM'`
   returns an empty result rather than a rejection. Adding `products: [ECM]` to
   `DimensionSpec`/`FilterSpec` plus one check in `_resolve_dimensions`/`_resolve_filters`
   turns a silent empty answer into a governed up-front message. Deliberately *not*
   declared today, because an inert key that looks enforced is worse than no key.
8. **Port the v1 `computed_filters`.** The four objects declare none. They are the only
   way this framework can express an **OR**, and the only **NULL-safe negation**. That
   one feature collapses the non-B&D recipe and the exchange retry to single requests.
   Port from `v1 capital_markets.yaml` rather than re-deriving — a wrong regex fails silently by
   matching the wrong rows.
9. **Surface `requires_filters` in `discovery()`.** Confirmed: `ontology.py:336-339`
   emits only aggregation and description, so 16 metrics carry a rejection the agent
   cannot see. Worked around this pass with a `usage_note` per object; the one-line code
   fix is the owner's call.
10. **`ORDER_AMOUNT` on ECM — a limit price or a limit amount?** V1 says "may be a LIMIT
    value, not an order amount". Both readings end in "never aggregate", so the guidance
    is safe either way, but it governs whether the column can ever become a metric.
11. **Row-exclusion asymmetry, explicitly deferred by the diagnostics.** ECM drops
    cancelled/deleted/passed/unowned orders and Confidential/Withdrawn/Terminated
    transactions; **DCM excludes nothing** and still carries `confidential` deals. So
    "number of orders" means a materially different population per product. Currently a
    disclosure duty in three files. Fixing it is cheap and was scheduled for a later
    batch — it needs a policy decision, not a measurement.
12. **Status case variants at source** (`priced`/`Priced`, `announced`/`Announced`).
    Every status comparison must `UPPER()` both sides and every breakdown must merge the
    pairs by hand or the buckets will not sum. Normalising at source deletes a
    disclosure duty from four files.

---

## 6. What the views would need to change to go further

Ranked by hops removed per unit of work.

1. **`TRANCHE_SIZE` → `vw_order_detail`.** Makes coverage/oversubscription — the most
   common real ask that still costs two requests — single-object. Legal at order grain.
2. **`ISSUER_NAME` / `GFCID` / `SECTOR` → `vw_order_detail`.** Kills the deal→ids→order
   two-step for every issuer- or sector-scoped investor question. Also removes the one
   asymmetry in SKILL §2's "what each object sees" table.
3. **Materialise `vw_entity_search`, or index `UPPER(ENTITY_NAME)`.** Measured 9.4 s for
   one name lookup and 79.4 s for one GROUP BY, on a plain unindexed UNION view over the
   two largest views — and `query_timeout_seconds` is **inert** on Trino, so nothing
   stops it burning a turn. This is why the entity object's own guidance is "do not call
   this object". Spec §4 asks for it explicitly; no scope rule withdrew it. It would
   change resolution from a scan to a seek.
4. **Index `OB_ORDER.ORDER_ID`** (Round 4 open risk #1) — the INVESTOR branch of the
   entity view re-derives the whole order view including its `ROW_NUMBER` dedupe.
5. **Resolve the ECM currency name on the deal branch** (join `CURRENCY_NAME` the way the
   tranche view does, instead of LISTAGGing `TRANCHE_CURRENCY_ID`). Makes `currencies`
   mean the same thing on both products and unblocks open question 1.
6. **Normalise status casing at source** — deletes the merge-the-variants duty.
7. **Align the row-exclusion policy across products** — deletes the count-honesty
   disclosure duty (needs the §5.11 policy decision first).
8. **A real per-tranche settlement currency on the deal branch**, if question 2 shows the
   column is populated — today it is a `MAX()` collapse.

Two things are **closed and should not be re-requested**: `MATCH_RANK` on the entity view
(withdrawn by diagnostics scope rule 1 — no new columns) and a real `EXECUTION_STATUS`
(one constant on ECM, NULL on DCM; the concept is `deal_status`).
