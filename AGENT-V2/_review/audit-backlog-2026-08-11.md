# Audit backlog — Fable full-repo audit, 2026-08-11

The 6-dimension / 20-verifier audit confirmed 19 findings; all 19 are FIXED
(commit pending). This file preserves what was found but NOT fixed, ranked.
Verify each against the code before acting — some may rot as the repo moves.

## Refuted (do NOT re-report)
- **Order ontology models 3 columns (issuer_name, sector, tranche_size) that the DEPLOYED VW_ORDER_DETAIL does not have — every sector/issuer-scoped investor ask will error at runtime** — The evidence holds verbatim but the finding conflates the repo's STAGED state with the DEPLOYED state, and the exact failure it predicts is already gated by two files the auditor missed. (1) /Users/babachaitanyakothapalli/Documents/ADK-KIT/AGENT-V2/views/_docs/_DEPLOY-ORDER.md (created 2026-08-11 10:15, commit 64d861b) states the doctrine that covers this class explicitly: 'The four view files and the f

## User-side (outside this repo)
- **[low/S] CyberArk credential cache: VERIFIED implemented and live on the Trino hot path, but the executor's Oracle path imports a different, absent, untested module**
  - Fix: Change executor.py:40-41 to import fetch_key_with_fid from utils.cyberark_integration.secrets (the cached, tested implementation), keeping the try/except fallback. Confirm at next deploy that the platform's utils/starburst.py still resolves STARBURST_PASSWORD_FID through this secrets module (grep the pod log for 'CyberArk cache HIT').
- **[low/S] view-columns.md is stale relative to the 2026-08-11 redeploy while declaring itself AUTHORITATIVE — it now contradicts the ontology in the direction that would reintroduce the lexical-sort bug**
  - Fix: Re-run the all_tab_columns capture against all four views and re-date the file (one query, needs warehouse access — user-side). This is the single cheapest action that resolves finding 1's ambiguity and hardens findings 2-4 against regression.

## Below the line (unverified — treat as leads, not facts)

### [medium/S] TrinoDialect.render_literal — the one point where agent values become SQL text — has no test despite the code's own NOTE demanding one
- File: `AGENT-V2/tests/test_render_literal.py`  (auditor: test-coverage)
- Proposed: Small test importing TrinoDialect directly (no stubs needed — test_disambiguation_scope already imports it). Assert: value "x' OR '1'='1" renders as 'x'' OR ''1''=''1' (quotes doubled, quoted as one literal); ints/floats render bare; None -> NULL; bool -> TRUE/FALSE; a 'f'-named param with value '2025-01-01' renders DATE '2025-01-01' and '2025-01-01T00:00:00' renders TIMESTAMP (the typed-literal path that keeps date filters comparing as dates, not VARCHAR — a silent wrong-rows class on Trino); a 'cf'-named param gets the (?i) prefix and is NOT date-typed. Also pin _render_trino_sql (executor.p

### [medium/S] Gate test-runner is hand-wired per file — a new test file silently does not gate; replace with a glob
- File: `AGENT-V2/_review/ontology_check.py`  (auditor: test-coverage)
- Proposed: Replace the seven blocks with one loop: for t in sorted((ROOT / 'tests').glob('test_*.py')): rc = subprocess.run([sys.executable, str(t)], capture_output=True, text=True); check(rc.returncode == 0, f'[python] {t.name} FAILED — run it directly'). Strictly STRONGER than today (same seven files still run, future files auto-run), so it does not violate the no-weakening constraint; keep the two structural checks on SECRETS_TEST hygiene (ontology_check.py:1042-1052) as-is. Every test file already supports standalone execution with exit codes (each has the __main__ CASES runner), so no test changes n

### [medium/S] Discovery date-anchor BOUNDS are unasserted — the gate checks token presence, not that the upper bound is tomorrow
- File: `AGENT-V2/tests/test_discovery_date_anchor.py`  (auditor: test-coverage)
- Proposed: Test via unbound call, no YAML load (verified in prototype): OntologySpec.discovery(fake_self) with a namespace carrying the ~15 attributes discovery reads. Assert: result['current_date'] == date.today().isoformat() (computed at CALL time — catches anyone caching the discovery dict at import, which would freeze 'today' for the pod's lifetime); date_anchor contains (today+1day).isoformat() as the '<' bound and (today-365days).isoformat() as the '>=' bound; contains 'TODAY IS'; contains the never-refuse-history clause ('HISTORY'). Can live inside test_planner_contract.py to keep file count down.

### [medium/S] OntologyRegistry.resolve — the ecm_dcm_* migration shim has NO test and NO gate check; removing it breaks every pinned caller with unknown_source
- File: `AGENT-V2/tests/test_source_resolve.py`  (auditor: test-coverage)
- Proposed: Small test constructing the registry without YAML/pydantic (verified in prototype): reg = object.__new__(OntologyRegistry); reg._lock = threading.RLock(); reg._by_source = {four capital_markets_* keys: None}. Assert: resolve('ecm_dcm_order') == 'capital_markets_order'; resolve('ECM-DCM-DEAL') == 'capital_markets_deal' (normalise + shim compose); exact ids pass through; resolve('deal') sub-scope matches; resolve(None) with four sources raises code unknown_source containing "Missing 'source'" (this is the same fact SKILL.md's 'only defaults when exactly ONE source' contract check depends on, ont

### [medium/S] Executor error classification (_classify_execution_error) untested — the anti-retry-loop and timeout guidance can silently regress
- File: `AGENT-V2/tests/test_executor_classification.py`  (auditor: test-coverage)
- Proposed: New test file (verified runnable in the prototype: trino/factory stubs from test_cross_object_error.py:72-79, then 'from bqs.executor import _classify_execution_error'). Assert code per input: 'Query exceeded maximum time limit of 300.00s' -> query_timeout; 'EXCEEDED_TIME_LIMIT' -> query_timeout; 'DPI-1067: call timeout...' -> query_timeout; 'Connection refused' / 'SSL: CERTIFICATE_VERIFY_FAILED' / '401 Unauthorized' / 'Missing required environment variable: STARBURST_HOST' -> service_unavailable; a Trino semantic error ('Column x cannot be resolved') -> execution_error. Also assert service_un

### [medium/S] Template MCP components still registered: wrong server instructions, echo tool, demo resource and demo prompt cost tokens every turn
- File: `AGENT-V2/app/mcpserver.py`  (auditor: server-path)
- Proposed: Replace the instructions string with one sentence describing the Capital Markets BQS contract; gate tool_echo_user_context behind an env flag (it is a legitimate identity-debug tool); delete the demo resource and demo prompt.

### [medium/S] Generic execution errors leak raw Trino driver text (including physical column/view names) to the agent
- File: `AGENT-V2/app/bqs/executor.py`  (auditor: server-path)
- Proposed: Extend _classify_execution_error: map COLUMN_NOT_FOUND/cannot be resolved and TYPE_MISMATCH/Cannot apply operator to a governed message ("The server built SQL the warehouse rejected — this is a server-side mapping fault, not your request wording; report it, do not retry"), and cap the generic fallback to a stable message with the driver text only in the server log (which executor.py:257-262 already writes with exc_info).

### [medium/S] SKILL promises `as_of_date` on every success, but the Trino path can never produce it
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: planner-capability)
- Proposed: Fix the promise, not the plumbing: amend SKILL.md:612 to state as_of_date is absent for these sources and 'Data as of' captions come from discovery's current_date/date_anchor (ontology.py:330-348). One line, saves the contradiction and tokens. Only wire a Trino as_of branch (executor.fetch_as_of_date via execute_starburst_query + TTL cache) if a governed availability view actually exists — never as a per-query fetch, which would add a warehouse hop to the 136s latency budget.

### [medium/S] ne/not_in silently drop NULL rows — inconsistent with the engine's own NULL-safe negation; warning note exists on only 1 of 4 objects
- File: `AGENT-V2/app/bqs/ontology.py`  (auditor: planner-capability)
- Proposed: Smallest class fix, zero behavior change: move the NEGATION DROPS NULLS sentence once into _generic_how_to_use (ontology.py:289-314) so every source's discovery carries it, then shrink the duplicated per-yaml prose (net token win). Optional stronger fix requiring sign-off because it changes answers: builder emits `({col} IS NULL OR {lhs} NOT IN (...))` for ne/not_in, matching the computed-filter stance — if taken, extend the regression suite first.

### [medium/S] `like` with a list of patterns (OR within one field) — in-list only covers eq-OR
- File: `AGENT-V2/app/bqs/models.py`  (auditor: planner-capability)
- Proposed: Accept a list value for op like: models.py BQSFilter description note; planner._validate_filter shape-check (non-empty list of non-empty strings, or single string as today); sql_builder._filter_predicate emits parenthesized `(lhs LIKE b0 OR lhs LIKE b1 ...)` — one filter entry, so the ANDed-filters contract text stays true at the request level. Discovery: extend the existing filter bullet in _generic_how_to_use by one clause. Note honestly: OR of disjoint date ranges stays 2 requests. Half a day with tests.

### [medium/S] Empty in/not_in list builds malformed SQL `IN ()` — opaque warehouse error instead of a planner message
- File: `AGENT-V2/app/bqs/planner.py`  (auditor: planner-capability)
- Proposed: In _validate_filter, reject an empty list for in/not_in with code bad_filter_value and a message that tells the agent what it means: "empty list — the upstream step produced no values; report no data instead of querying". 3 lines; no builder change.

### [medium/S] LIKE values bound verbatim: `_` (and interior `%`) over-match; no ESCAPE clause exists
- File: `AGENT-V2/app/bqs/sql_builder.py`  (auditor: planner-capability)
- Proposed: For op like only: escape backslash then underscore in the bound value (`v.replace('\\','\\\\').replace('_','\\_')`) and emit `LIKE <ph> ESCAPE '\\'`. Agent-composed `%` wildcards stay live (the skill teaches %NAME%, never `_` wildcards). Trino string literals process no escapes (trino.py:102-106 note) so the backslash survives rendering; ESCAPE works on Oracle/Postgres too. ~4 lines + a unit test pinning the escaping.

### [medium/S] No scalar-answer escape hatch: a single-figure ask is forced through Brief → table → Insights & Trends → follow-ups
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Restore the escape hatch in §11: "A single figure or ≤3 rows: state the finding in one or two prose sentences (with unit and Data-as-of), then follow-ups — no table, no Insights section."

### [medium/S] Skill-internal inconsistency: §3c-bis says filter meeting_type_key ONE_TO_ONE, §7c prescribes meeting_type eq '1:1' for the same ask
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Align the §7c row to the key: "one-on-one / 1:1 → meeting_type_key eq 'ONE_TO_ONE' (display column stores '1:1'; 'One-to-One' matches nothing there). 'Other than 1x1' excludes BOTH ONE_TO_ONE and NO_MEETING — say the no-meeting orders were excluded."

### [medium/S] Bare '<bank> deals' has no route: the name-filter row and the bank-name ban collide, and V1's default-to-syndicate rule was dropped
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Restore the V1 row in §3: "Bare '<bank> deals' with no role/B&D/investor word → tranche object, syndicate_member_name like '%<STEM>%', metric deal_count; state the assumption ('deals <bank> was in the syndicate for') and offer the as-issuer view as a follow-up."

### [medium/S] Relative time windows are computed from date_anchor but never echoed as absolute dates in the answer
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Add to §9: "Every relative window states its absolute bounds in the answer — 'last 12 months (12-Aug-2025 → 11-Aug-2026)' — so a wrong anchor is visible immediately." One sentence; also gives bankers audit-ready period labels.

### [medium/S] No Data-as-of doctrine: as_of_date is in every success payload but the agent is never told to show it
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Add one line to §11's brief spec: "The brief's first line carries 'Data as of <as_of_date>' (once per answer, from the response payload — never from memory)."

### [medium/S] Count-metric 'no product filter' rule collides with product_not_applicable rejection when the count touches a product-specific field
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Append one clause to §6b (and the agents.yaml rule 5 mirror): "...unless the request touches a §3c-ter product-specific field — that field forces the product scope, so scope the product and answer for that product only."

### [medium/S] Contradiction on unbounded dumps: routing table permits a clarification turn that the answer-style doctrine (and agents.yaml) forbids
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Delete "or ask once for a product/time/sector narrow" from the §3 routing row and make it: "Unbounded dump ('all deals') → run with limit 50 (+ paired count per the capped-listing rule), caption 'showing 1-50 of N', offer the three doors — never ask first."

### [medium/S] V1's multi-turn doctrine dropped: no pronoun-binding rule and no product-flip ('same for DCM') rule, so a flip after an ECM-only ask burns a rejected round-trip
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Add ~5 lines to §10 (doctrine only, no literals): (1) pronouns bind to the last confirmed entity/window, one short question only when truly ambiguous; (2) "same for DCM/ECM" re-derives product-dependent pieces — an ECM-only field (§3c-ter list) makes the flip structurally empty: say so and offer the entitled-product equivalent, zero tool calls; (3) product-specific vocabulary auto-implies its product filter — switch silently, never run the knowably-rejected request.

### [medium/S] Book-profile headline demands 4 figures (orders, investors, demand, allocation) that one-metric-per-request cannot deliver, and hand-summing is forbidden
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Prescribe the call plan in §11: "A book profile is sanctioned as up to 3 calls: the top-N listing, total_demand, total_allocation (order_count/investor_count from one grouped count request when asked) — or trim the headline to the figures you actually fetched." Alternative (bigger, only if latency of 3 calls is unacceptable): have formatter.py attach server-computed totals to order-listing responses — an app change in this repo, no view change.

### [medium/S] Deal object's ECM 'currencies' caveat is stale against the deployed view fix — it forces a needless hop to the tranche object for every ECM currency ask
- File: `AGENT-V2/app/bqs/ontology/capital_markets_deal.yaml`  (auditor: ontology-vs-views)
- Proposed: Rewrite the two passages: 'currencies like %USD% works on BOTH products; on ECM a currency the source could not map renders as an internal id, so an unmatched code may undercount — disclose that fallback'. Optionally confirm first with one DISTINCT-token probe of ECM CURRENCIES (user-side, minutes); the tranche yaml's OPEN list is the natural place to strike the entry. Removes a whole class of unnecessary two-object plans.

### [medium/S] Security-identifier PINPOINT rule dropped: id + date-window zero rows should auto-widen once (the id is the intent, the window was a guess)
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: doctrine-diff)
- Proposed: One line in SKILL.md §7b identifier bullet or §8: when an identifier (CUSIP/ISIN/FIGI/deal id/order id) filter returns 0 rows AND the request carried a date window, re-run once without the window in the same turn and report the actual pricing date relative to the asked window.

### [medium/S] V1 comparative-investor recipes dropped: 'investors in both deals' is expressible in ONE request but the skill steers it to refusal/two requests
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: doctrine-diff)
- Proposed: Add one recipe line to SKILL.md §6: 'investors in both deal A and deal B' → order object, deal_id in [A,B], metric deal_count, having deal_count eq 2, project investor_name+investor_id (in N of a list of N deals generalizes: having eq N). Keep 'A but not B' in §3c as the honest two-request shape.

### [medium/S] agents.yaml fallback CORE CONTRACT carries stale literals the skill/ontology corrected ('1x1' and '10-YEAR not 10Y')
- File: `AGENT-V2/adk/config/agents.yaml`  (auditor: doctrine-diff)
- Proposed: Edit agents.yaml rule 10 to match the corrected doctrine: meeting type stored literal is '1:1' (prefer meeting_type_key ONE_TO_ONE), and tenors match the short hyphenated token '%10-Y%' (both '10-YEAR' and '10-Y' are stored; bare '10Y' matches nothing). Two-line edit; no token growth.

### [medium/S] Convertible-class ECM unit word 'bonds' dropped — convertible sizes will be labeled 'shares' (reverses a QA ruling)
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: doctrine-diff)
- Proposed: One line in SKILL.md §6b: header unit word by class — DCM: currency; ECM non-convertible: shares; ECM convertible/exchangeable class (equity_type like %CONVERT%/%EXCHANG%): bonds; mixed aggregate: securities.

### [medium/S] Peer-companies/competitors unsupported intent dropped from every V2 surface
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: doctrine-diff)
- Proposed: Add one row to SKILL.md §3b: peer/competitor asks → refuse (no peer relationship data on any object), offer a sector filter or a named company instead. Optionally also add the unsupported_intent block to capital_markets_deal.yaml and capital_markets_order.yaml so discovery carries it, but the skill row alone covers the routing (§3 checks §3b before discovery).

### [medium/M] Computed filters (OR-joined bank aliases, NULL-safe negate) not ported to the four-view ontologies — documented in-file but still open, and planner support already exists
- File: `AGENT-V2/app/bqs/ontology/capital_markets_tranche.yaml`  (auditor: doctrine-diff)
- Proposed: Port broker_participation / bill_and_deliver / syndicate_member (with negate) from the earlier single-source capital_markets.yaml into capital_markets_tranche.yaml verbatim (codes and pipe-anchor regex must match data), then flip the 'declares NONE' statements in SKILL.md §0b and agents.yaml rule 7 to name them. Verify with the ontology gate.

### [medium/M] agents.yaml static_instruction duplicates ~1.5-2k tokens of the skill verbatim on every turn (answer style, paging, contract), beyond what the load_skill fallback needs
- File: `AGENT-V2/adk/config/agents.yaml`  (auditor: chat-quality)
- Proposed: Compress the static_instruction fallback to rules-only: keep STEP 0, the routing list, and every literal/behavior, but cut duplicated anecdotes, duplicated examples and the second copy of the three-doors/book-profile prose to one-line pointers ("degraded mode: cap 50 rows, absolute #, ids always, offset paging, three doors, no export"). Est. 800-1,200 tokens saved on every turn with zero behavior lost when the skill loads.

### [medium/M] SKILL.md internal bloat: class-word map stated twice, plus QA-environment row counts embedded as rationale that will be false in PROD
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Keep one canonical class-word map (the §7b blockquote), shrink §3c-bis's table to the four non-class rows it uniquely owns, and point §7c's common-stock row at it. Strip the QA row counts, keeping the qualitative claim ("a real population carries several" / "most DCM orders carry no allocation"). Est. 400-700 tokens saved per query; also removes numbers a banker could quote back and be wrong in PROD.

### [medium/M] Secondary metrics sharing the GROUP BY — halves round-trips for 'count AND size by X' asks
- File: `AGENT-V2/app/bqs/models.py`  (auditor: planner-capability)
- Proposed: models.py: `metrics: list[str] = []` (extra metrics). planner: resolve each via the _resolve_having-style path (spec lookup + reject dedup_key metrics; primary must also be non-dedup), extend the order-alias allow-set. sql_builder plain path: append one agg expression per extra metric to select_parts. formatter unchanged (metric field stays the primary). Discovery: one line in _generic_how_to_use. Half a day plus tests.

### [medium/M] Serial post-query disambiguation probe adds a full second Trino round trip that could overlap the main query
- File: `AGENT-V2/app/services/domain_query_service.py`  (auditor: server-path)
- Proposed: When an entity-name filter is present and its field is NOT in req.dimensions, submit the disambiguation probe on a worker thread at the same time as the main execute(); join after formatting. Discard the probe result if the main query returns 0 rows (suggestions path takes over). Keep the free path (count from returned rows) untouched. Preserve the phase-timer log line verbatim — ontology_check pins t_build/t_exec/t_format/t_enrich and the _enrich_result call signature (ontology_check.py:697, 754-756).

### [medium/M] as_of_date is structurally impossible for Trino sources, so no ECM/DCM answer can carry an accurate 'Data as of' header
- File: `AGENT-V2/app/bqs/executor.py`  (auditor: server-path)
- Proposed: Add a Trino branch to fetch_as_of_date that runs spec.as_of_date.query through execute_starburst_query, wrapped in a small per-source TTL cache (e.g. 15 min) so it costs one extra round trip per TTL, not per query; then declare governed as_of_date queries in the four ontologies. Best-effort semantics (return None on failure) already exist.

### [low/S] Cross-object explainer test hardcodes its own field map — add ontology-derived pins so the fake registry cannot drift from the real YAMLs
- File: `AGENT-V2/tests/test_cross_object_error.py`  (auditor: test-coverage)
- Proposed: Add one dependency-free assertion tying the fake to the real YAMLs textually (the gate's own technique, no pydantic needed): read app/bqs/ontology/capital_markets_deal.yaml and assert re.search(r'^  sector:', filters-block) matches, and capital_markets_order.yaml does NOT declare sector while it DOES declare investor_category/order_allocation — i.e. the three facts FakeRegistry encodes. ~10 lines inside the existing file, keeps the fast fake for behavior cases while pinning its premises to the shipped ontology.

### [low/S] Validation-error text tells the agent 'source' defaults, which is false in the four-source deployment
- File: `AGENT-V2/app/services/domain_query_service.py`  (auditor: server-path)
- Proposed: Adopt the in-file proposal: "'source' is required whenever discovery returns more than one source." One-line message change.

### [low/S] zen entity calls hardcode verify=False on requests carrying SOEID and the IBM client secret
- File: `AGENT-V2/app/bqs/entity/zen_entity_search.py`  (auditor: server-path)
- Proposed: Pass verify=_resolve_ssl_verify() at both call sites (SSL_CERT_FILE > DISABLE_SSL_VERIFY > True), preserving local-dev escape via DISABLE_SSL_VERIFY=true.

### [low/S] Per-response token trims: 'scored' duplicates did_you_mean, and generated_sql ships in every payload the skill then forbids showing
- File: `AGENT-V2/app/bqs/formatter.py`  (auditor: server-path)
- Proposed: Drop `scored` from suggestion blocks. Gate generated_sql behind BQS_INCLUDE_SQL_IN_RESPONSE (default off) — keep the SKILL.md mention and the sql_audit note comment intact, since ontology_check.py:930-936 pins those TEXTS, not the payload key's presence.

### [low/S] discover_business_terms with an unknown source raises an unhandled BQSError instead of returning the governed error shape
- File: `AGENT-V2/app/services/domain_query_service.py`  (auditor: server-path)
- Proposed: Wrap discover() in try/except BQSError → return e.to_dict() (and a generic internal_error catch mirroring run()'s lines 275-284), so a typo'd source gets the same self-correcting message shape as run_bqs_query errors.

### [low/S] Pin NULLS LAST on ORDER BY — null placement in top-N is currently an unverified engine default
- File: `AGENT-V2/app/bqs/sql_builder.py`  (auditor: planner-capability)
- Proposed: Emit `NULLS LAST` on every ORDER BY part (one edit at sql_builder.py:223; supported by Trino, Oracle, Postgres). Makes top-N deterministic across dialects, closes the UNVERIFIED item, and lets the skill demote the is_not_null-guard from mandatory to optional (small token win). Add a builder unit test.

### [low/S] SQL limit not clamped to the response row cap — warehouse fetches rows the formatter always discards
- File: `AGENT-V2/app/services/domain_query_service.py`  (auditor: planner-capability)
- Proposed: After plan_query in domain_query_service.run (or in the planner clamp), bound the effective SQL limit to min(plan.limit, formatter.max_response_rows()) — paging semantics are preserved because next_offset advances by returned rows and filled_limit still fires on row_count >= limit. ~3 lines; extend tests/test_response_paging.py.

### [low/S] Dangling cross-references: '§14' does not exist in V2, and the 'class-word map' is cited as §3 but lives in §7b
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: chat-quality)
- Proposed: Fix the three references: 35 → "which the Confidential rule in §11 forbids"; 30 and 632 → "the §7b class-word map". Two-minute edit; prevents Gemini hunting for a nonexistent section mid-answer or applying the wrong table.

### [low/S] Stale 'NOTE TO THE PLATFORM OWNER' in the order ontology claims products: is undeclarable and unenforced — the file itself declares it and the planner enforces it
- File: `AGENT-V2/app/bqs/ontology/capital_markets_order.yaml`  (auditor: ontology-vs-views)
- Proposed: Replace the note with two lines stating the current truth: products: IS declared on the seven ECM-only fields and IS enforced by planner._check_product_applicability (product_not_applicable). Keep the 'ECM-ONLY (hard NULL on DCM)' description-prefix convention note.

### [low/S] Tranche per-product applicability roster omits ticker (and issuer_name/issuer_id/deal_name) from the BOTH-PRODUCTS list — the closed-looking list invites wrongful refusals or hops for DCM ticker asks
- File: `AGENT-V2/app/bqs/ontology/capital_markets_tranche.yaml`  (auditor: ontology-vs-views)
- Proposed: Add ticker, issuer_name, issuer_id, deal_name to the BOTH-PRODUCTS sentence, with the same unmeasured-DCM-population caveat sector carries for ticker. One line; prevents an agent treating the roster as exhaustive and refusing or re-routing a legal one-request DCM ask.

### [low/S] Coordinator role dual-spelling trap dropped — '%COORDINATOR%' may silently miss 'Co-ordinator' rows with no OR available
- File: `AGENT-V2/app/bqs/ontology/capital_markets_tranche.yaml`  (auditor: doctrine-diff)
- Proposed: In the syndicate_role filter description, change the coordinator guidance to the spelling-proof stem like '%ORDINATOR%' (catches Coordinator and Co-ordinator alike, no measurement needed). Optionally confirm 'Active Bookrunner' with one DISTINCT probe before the value list is trusted.

### [low/S] Entity-scoped context header with 'Data as of' dropped from the house reply anatomy
- File: `AGENT-V2/adk/skills/text2sql-capital-markets/SKILL.md`  (auditor: doctrine-diff)
- Proposed: One line in §11: entity-scoped answers open with '<Entity> | <id> | Data as of: <as_of_date>' and each table gets a caption naming its grain. Restores platform consistency and data-freshness disclosure for ~2 lines.

### [low/M] Declared unsupported_intents are mostly dead server-side — only field-shaped ids can ever fire
- File: `AGENT-V2/app/bqs/planner.py`  (auditor: planner-capability)
- Proposed: Extend UnsupportedIntentSpec (ontology.py:189-199) with optional `trigger_fields: list[str]` and `trigger_products: list[str]`; _check_unsupported fires when a request references any trigger_field while scoped to a trigger_product (reuse the product-scope derivation from _check_product_applicability). Keep `patterns` discovery-only. Ontology model + ~15 planner lines + yaml keys per intent; verify ontology_check stays green (it is textual, no import needed).

## View-batch candidates (queued 2026-08-13 — next 2-4 day view deploy cycle)

### Denormalize EQUITY_TYPE onto VW_TRANCHE_SUMMARY
QA 2026-08-13: "top 5 Convertible Preferred deals by tranche size with product
type" cannot filter the class axis on the tranche object — EQUITY_TYPE exists
only on VW_DEAL_SUMMARY (view-columns.md col 10). Interim doctrine (shipped):
apply the class as its product_type subtype in-list (Conv. Pfd / ADR Conv. Pref
/ Mandatory Convertible Preferred Stock) and project product_type. That proxy
holds only for the convertible-preferred class; other equity classes ranked by
tranche metrics have no product_type equivalent. The structural fix follows the
established "deal attributes never force a hop" pattern (sector, deal_status,
use_of_proceeds already denormalized down): ECM branch carries
ETX.EQUITY_TYPE, DCM branch CAST(NULL AS VARCHAR2(4000)) — plus ontology
dimension/filter (products: ["ECM"]), a products-pin in the gate, and a
class-word-map update to prefer the real column. Pairs with the existing order
view round-2 list (bnd_bank, deal_sharing_type, offering_type).

### Currencies unmapped-id fallback — READY FOR NEXT BATCH (resolved 2026-08-14)
"Currencies: 1 | 4" — the deal view's ECM currency fix (NVL to CURRENCY_NAME)
falls back to the raw internal id when TRANCHE_DEMAND_CURRENCY has no name row.
Presentation doctrine now hides ids from users ("not recorded");
_deploy-check row 4b reports the affected-deal count as INFO (view-logic
check 4 stays whole-string). MEASURED: QA = 377 ECM deals; unmapped id set is just {1, 2, 3, 4, 7, 67,
76, 139} and the affected deal names are largely test junk (2026-08-14, user
run). Next: _currency-check Q4 says whether those ids have names anywhere in
OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY — names exist -> queue the
global id->name second-fallback view change; no rows -> QA seed junk, close.
PROD Q1 count still pending — decision rule unchanged: `SELECT COUNT(DISTINCT DEAL_ID) FROM DGSTREAM.VW_DEAL_SUMMARY
WHERE PRODUCT='ECM' AND REGEXP_LIKE(CURRENCIES,'(^|\| )[0-9]+( \||$)')`.
RESOLVED: Q4 proved every leaked id has a globally known name (1=USD,
2=EUR, 3=GBP, 4=CAD, 7=AED, 67=IRR, 76=KYD, 139=TZS) — a per-tranche join
gap, not seed junk, and USD/EUR/CAD means PROD has the same shape. The
global id->name second fallback is WRITTEN into views/vw_deal_summary.sql
(deploys with the EQUITY_TYPE batch). Post-deploy check: _deploy-check 4b
drops to ~0. Presentation doctrine stays as the last-resort net.

### Order view round-2 denorm — PROMOTED by the malformed-call trace (2026-08-17)
QA: "top 15 long-only investors in IPOs over 10 years" → hop 1 returned ~100
IPO deal_ids → Gemini corrupted its own function call emitting the 100-id
in-list (MALFORMED_FUNCTION_CALL at the platform layer; the request never
reached the MCP) → agent blamed a "system limitation" and dead-ended. Interim
doctrine (shipped): id in-lists capped at 40, honest sample/narrow language,
no invented excuses. STRUCTURAL FIX: denormalize OFFERING_TYPE (plus
bnd_bank, deal_sharing_type — the original round-2 list) onto VW_ORDER_DETAIL,
same pattern as round 1's issuer_name/sector/tranche_size. That makes
"investors in IPOs" ONE request with no id list at all — the whole failure
class disappears. Deploy with the same batch as the deal-view currency
fallback (written) and tranche-view EQUITY_TYPE (queued). Ask when the batch
is scheduled and the three view diffs get written together.

### PLATFORM BUG — preset follow-ups dead-end at the root (2026-08-18)
Trace: session opened with the /capital_markets_agent_v2 PRESET (turn 1 runs
the sub-agent directly — no transfer event). Every follow-up then routes to
ask_banking_root_agent, which calls run_bqs_query ITSELF and fails with
"Tool 'run_bqs_query' not found. Available tools: transfer_to_agent" —
repeating identically on each follow-up. Mechanism: in preset sessions the
root's context contains NO example of its own transfer_to_agent call, only
the sub-agent's run_bqs_query calls, so Gemini imitates the wrong tool.
NOT fixable in this repo (root instruction + preset router are platform
components). Handoff to the platform team, either fix suffices, both is best:
  1. PRESET STICKINESS: when a session starts with a preset agent, route
     follow-up messages to that agent directly (the platform already carries
     State: preset_name), not to the root.
  2. ROOT HARDENING: add to ask_banking_root_agent's instruction: "Your ONLY
     tool is transfer_to_agent. Tool calls visible in history (run_bqs_query,
     discover_business_terms, load_skill...) belong to SUB-AGENTS — seeing
     them is not availability; never call them yourself. On 'Tool not found',
     do not retry the call — transfer to the agent that owns the domain."

### Billed-by goes ORDER-LEVEL in round 2 — DIFF WRITTEN, BOTH PRODUCTS
(final 2026-08-18: ECM has it too — OB_ECM_ORDER.BILLEDBY_BROKER_CODE,
misnamed: holds full bank NAMES, 90.2% populated [86,611/96,006]. One
uniform column; staged config in _review/round2-config-staged.md.)
OB_ORDER.BND holds a real bank NAME per order (Q1: Citigroup Global Markets
Inc. 802k orders; 1.33M NULL; name variants incl. a truncated 'J.P. Morgan P';
'DB Account 2' = QA junk). It is a SCALAR — so "orders billed by X" becomes a
one-hop like-filter AND a billed-by league table (GROUP BY) becomes possible,
which pipe lists structurally denied. Round-2 order-view spec upgrades from
"inherit tranche bnd_bank" to "pull OB_ORDER.BND AS BILLED_BY" (like-only
matching, stem doctrine transfers; NULL = 'no billing bank recorded').
Q2 (2026-08-18): 3,687,996 of 5,020,472 orders carry BND = 73.5% — viable
with the 'no billing bank recorded' disclosure for the rest. NOTE: OB_ORDER
(5.02M) has FEWER rows than the order view's measured spine (~5.87M) — the
round-2 diff joins BND via LEFT JOIN on the order key so unmatched view rows
fold into 'not recorded'. Q3 (2026-08-18): 10,042 of 18,909 tranches with
BND orders (53%) carry MORE THAN ONE distinct BND — genuine order-level
attribution, not a mirrored designation. SPEC FINAL for the round-2 diff:
  * vw_order_detail: DCM branch LEFT JOINs OB_ORDER on the order key and
    projects OB_ORDER.BND AS BILLED_BY; ECM branch CAST(NULL AS
    VARCHAR2(4000)) — Q5 (2026-08-18) proved ZERO ECM orders join to
    OB_ORDER (it is the DCM order source; 4.97M of its 5.02M rows are the
    view's DCM spine). DCM population 74%; NULL = 'no billing bank
    recorded'.
  * capital_markets_order ontology: billed_by dimension + filter with
    products: ["DCM"] (joins the gate's _PRODUCT_PINS table on ship);
    like-only, never eq (name variants incl. truncated 'J.P. Morgan P'; Citi
    stem doctrine transfers: '%CITIGROUP GLOBAL MARKETS%'), suggestable, no
    curated values (QA junk like 'DB Account 2'). Plus a token-less
    bill_and_deliver computed filter on THIS object (column billed_by, fixed
    code CITIGROUP GLOBAL MARKETS) so 'Citi non-B&D ORDERS' negates
    NULL-safely at order grain — DCM only.
  * SKILL: DCM billed-by asks at ORDER grain route here one-hop, and DCM
    billed-by league tables (GROUP BY billed_by) become possible — order-level
    truth that disagrees with the tranche's single designation on half of
    tranches. ECM billed-by stays the tranche-designation doctrine (B&D
    first-token; the 850-multi-B&D ambiguity remains and is disclosed) — a
    neat REVERSAL of the syndicate asymmetry: ECM has the rich syndicate,
    DCM has the rich per-order billing.
  * V1 COMPARISON (checked 2026-08-18): V1 never had order-level billing on
    either product — ECM was the BND_BROKER 'true'-index extraction over the
    tranche designation replicated per order row, DCM was the single
    designation string; OB_ORDER.BND sat UNUSED. So round-2 BILLED_BY is not
    V1 parity — it CORRECTS a designation-vs-actual imprecision V1 carried on
    the 53% of tranches where per-order billing varies. (V1 also asserted 'at
    most one true per row' — Q25's 850 multi-B&D tranches disprove it.)

### Issuer name — ECM FIXED via OB_DEAL_ISSUER GFCID join (2026-08-18);
### DCM source still open with Samir
RESOLVED (ECM): OB_DEAL_ISSUER maps GFCID->NAME (74,124/74,276 named;
A3: 6,892 of 7,195 GFCID-carrying ECM deals resolve = 96%; deals without
GFCID are largely QA test junk). OIN join written into ALL THREE views'
ECM branches (grouped per GFCID - no fan-out; old column kept as NVL
fallback). Samir's 'OB_DEAL_ISSUER.NAME is for ECM' was the ANSWER, not
a warning: its DEAL_TRANCHE_ID keys are I-prefixed ECM-source format, so
the DCM branches' concat join has likely NEVER matched - DCM issuer
source is the remaining open question for Samir. Deploy check: row 1e.

### (superseded) Issuer name source swap — ON HOLD, blocked on join path (2026-08-18)
MEASURED: current ECM issuer source is 100% DEAD in QA (0 of 21,195 deals
carry a name — explains every "—" in traces). But the proposed source
does not join: TRANSACTION_ID matches 2/21,195 ECM and 0/46,931 DCM deal
ids, and PARTY_NAME is NULL on ~98% of Primary Client rows (59,839 of
~61k transactions have zero non-null names; only 1,390 carry one).
BLOCKED on Dumitru: what does TRANSACTION_ID join to (bridge table —
OPUS_BASE_TRANSACTION?), and is QA's copy of PARTY_NAME populated?
DOES NOT HOLD THE BATCH — items 1-4 ship without it.

### (original notes) Issuer name source swap — batch item 5 (tech guidance, queued 2026-08-18)
Ibanescu (5/28): ECM issuer name should be PARTY_NAME from
OPUS_BASE_TRANSACTION_RELATED_PARTIES where PARTY_ROLE='Primary Client' — not
OPUS_ECM_TRANSACTION.ISSUER_NAME_FROM_SOURCE. Matches the QA symptom (Issuer
Name "—" across ECM answers). Touches the ECM branch of ALL THREE data views
(deal, tranche, order — each carries ISSUER_NAME). Measure first via
views/_checks/_issuer-name-check.sql (Q1 shape/keys, Q2 role vocabulary, Q3 grain/
dedupe, Q4 gained/lost/disagree vs current, Q5 eyeball). Swap ships in the
round-2 batch if Q4 shows net gain without losses; a MAX()/ROWID dedupe
guards grain per Q3.
BOTH PRODUCTS ARE IN SCOPE (Samir, 2026-08-18: "OB_DEAL_ISSUER.NAME is for
ECM"): all three views' DCM branches currently source ISSUER_NAME from
OB_DEAL_ISSUER.NAME via DEAL_ID||'-'||TRANCHE_ID — if that table is ECM-side,
DCM issuer names are misdirected everywhere. Measure via check Q6-Q8
(per-product population in the deployed views; table shape/keys; DCM join-hit
rate). OPEN QUESTION for Samir: if not OB_DEAL_ISSUER, what IS the DCM issuer
name source? (OB_DEAL_TRANCHE carries ISSUER_SECTOR but no known name
column.)

### SOURCE RICHES on OPUS_ECM_TRANSACTION (desc'd 2026-08-18) — future batches
Full column inventory falsifies three "not tracked" doctrines AT SOURCE
(population UNMEASURED — the dead ISSUER_NAME_FROM_SOURCE on this same table
proves existence != populated; measure before any doctrine change):
  * ANNOUNCE_TS / PITCH_TS / LAUNCH_TS / CLOSING_TS (+LAUNCH_OCCURRED,
    FILING_OCCURRED) — "announced date not tracked" may be wrong.
  * BASE_PRICE / REOFFER_LOW_PRICE / REOFFER_HIGH_PRICE / PAR_VALUE /
    CONVERSION_RATIO — pricing exists; ECM deal VALUE (shares x price), the
    banker-lens #1 gap, may be derivable.
  * FX_RATE / FX_SOURCE (+SIZE_CURRENCY_*) — "no FX column" wrong at source;
    USD-equivalent totals may be possible.
  * Also: ISSUER_LEID, ISSUER_RATING(+AGENCY), ISSUER_WEBSITE, DEAL_CAPTAIN,
    PRODUCT_EQUITY_CLASS_VALUE (3rd instrument axis), BB/DMS/CMG/DEAL_LOGIC
    cross-system deal ids, OFFERING_FORMAT, ISSUE_STATE_VALUE.
No living issuer-NAME sibling — issuer fix stays on the OB_DEAL_ISSUER GFCID
path (A1-A3).

### Issuer identity — INTENDED END-STATE per tech team (Samir, 2026-08-18 pm)
Samir: PARTY_GFCID and PARTY_TICKER from RELATED_PARTIES should also replace
GFCID and TICKER — combined with Dumitru's name guidance, RELATED_PARTIES is
the intended issuer-identity MASTER (name + GFCID + ticker). Bridge
hypothesis: RELATED_PARTIES.BASE_ID (NUMBER NOT NULL) -> OPUS_BASE_TRANSACTION
(whose TRANSACTION_ID = our DEAL_TRANSACTION_ID family — the deal view
already joins it for DEAL_REGION); my failed direct join skipped the bridge.
Confirm via F (desc OPUS_BASE_TRANSACTION) + G (named-row sample). End-state
layering once confirmed: NAME/GFCID/TICKER = NVL(party master, NVL(current
sources)). The SHIPPED OB_DEAL_ISSUER GFCID fix stays as the fallback layer —
measured working (0 -> 6,892 QA deals) and PROD-safe. QA sparseness caveat
stands: PARTY_NAME null on ~98% of Primary Client rows in QA — the master may
only shine in PROD; keep NVL fallbacks permanent.

### Issuer identity — PARTY MASTER LAYERED (2026-08-18 pm); join mystery solved
Sample G proved RELATED_PARTIES.TRANSACTION_ID IS the deal id family — the
direct join was right; QA's copy is just unloaded (~1,390 named transactions,
PARTY_GFCID null even on named rows; the 2/21,195 was real overlap, not a key
mismatch). No bridge needed. The PCM layer (Primary Client, latest VERSION by
PUBLISHED_TS, one row per transaction) is WRITTEN into all three ECM branches:
NAME/GFCID/TICKER = NVL(party master, existing chain). QA behavior unchanged
(layer joins ~nothing); PROD gets the intended master. Fallbacks permanent.

### OPUS_BASE_TRANSACTION riches (desc'd 2026-08-18) — future batches
DEAL_FEE_MM + DEAL_FEE_CURRENCY — FEES AT SOURCE (banker-lens "impossible
tier" gap may be closable!). DEAL_SIZE_MM + DEAL_SIZE_CURRENCY (deal size in
MONEY — the ECM valuation gap). PRODUCT / SUB_PRODUCT (business-line axis),
MANDATE_STATUS, PROJECT_NAME, TRANSACTION_STATUS. Population unmeasured —
measure before any doctrine or view change (the dead-column lesson).


### DCM issuer names — NEVER BROKEN (H+I, 2026-08-18 close)
OB_DEAL_ISSUER holds BOTH key families: 26,463 DCM-format rows (100% named)
+ 47,813 I-format; V1's concat join hits 74,276/74,281 DCM tranches (99.99%).
Samir's "is for ECM" and the I-format sample led us astray — the A2 FETCH
FIRST 15 surfaced only I-format rows. DCM layer final: party master (PROD) ->
V1 concat join (WORKING primary in QA). All view edits stand unchanged.
OPEN (query J): ~47.8k I-format (deal,tranche) pairs live in OB_DEAL_TRANCHE,
which the DCM branches read with NO product filter — check whether I-format
deals appear in the views as 'DCM' rows (possible cross-platform
contamination of the DCM population).


### I-format DCM population — CLOSED, legitimate (query L, 2026-08-18)
Eyeball of I-format 'DCM' view rows: bond tranches ('5 YR FXD USD', '15Y45F',
'10 yr', USD notionals, announced/draft) = IPREO-sourced DCM (OB_DEAL_TRANCHE
carries IPREO_DEAL_ID/IPREO_TRANCHE_ID; two source systems, one product). NO
contamination; DCM counts are sound; no product filter needed. Issuer
investigation fully closed — see views/_checks/_issuer-name-check.sql archive header.

### OB_DEAL_TRANCHE riches (214 cols, recorded in base-table-columns.md)
DCM-side treasure (population unmeasured): COUPON, YIELD, PRICE +
PRICE_GUIDANCE, BOOK_SIZE + ORDER_BOOK_SIZE_USD/EUR (USD-NORMALIZED book
sizes!), ALLOCATION_SIZE_USD/EUR, FX_RATE, FEES at four grains (TOTAL_FEE,
SELLING_CONSESSION_FEE, UNDERWRITING_FEE, MANAGEMENT_FEES, PRAECIPIUM_FEES,
RETAIL_UW_FEE), ANNOUNCEMENT/ISSUE/SETTLEMENT/TRADE dates, ROAD_SHOW dates +
participants, TRANCHE_CUSIP, SMC_* ratings (FITCH/MOODY/SP), IS_CONVERTIBLE,
GOVERNING_LAW, PARENT_ISSUER_NAME. Combined with the OPUS-side riches, the
fee/pricing/announced-date "not tracked" refusals are all potentially
closable in future batches — measure population first, always.

### ROUND-2 CONFIG APPLIED (2026-08-18, views deploying same day)
round2-config-staged.md executed and deleted: order yaml (billed_by dim+
filter both-products, offering_type ECM, bill_and_deliver computed filter,
applicability lists seven->eight), tranche yaml (equity_type dim+filter ECM),
SKILL (IPO ask = ONE request; class-ranked-by-tranche-metric = ONE request,
subtype approximation DEAD; billed_by order-grain doctrine + league tables),
agents.yaml routing line, gate pins (+_PRODUCT_PINS: tranche equity_type,
order offering_type; capability pins; retired the obsolete disclosure pin).
Bars: 1094/206/104. POST-DEPLOY: run _deploy-check.sql (rows 1b/1c/1d/1e);
if the view deploy ROLLS BACK, these configs must be reverted with it.

### Data-dictionary ticket #100 — remaining fields (2026-08-18)
MEASURED (Q1-Q5 results archived in views/_checks/_region-settlement-check.sql).
Per-field status:
* ISSUER_NAME — fixed, in the deploying batch (batch 2).
* DEAL_REGION ECM — the MAX-over-versions OBT join is ALREADY IN BATCH 2
  (entered adk v19/v20; Q1's 6.3% measured the old deployed view). Source
  has 95,592 real values, zero 'Not Specified' — that old claim is FALSE
  here. R1 predicts the post-deploy coverage; R2 checks the vocabulary
  against the NAM/EMEA/APAC doctrine (ontology prose changes if it differs).
* DEAL_REGION DCM + SETTLEMENT_TS DCM — were NULL placeholders; BATCH 3
  edits written in vw_deal_summary.sql: MAX(REGION) (13,978 rows, clean
  NAM/EMEA/APAC census) and MAX(SETTLEMENT_DATE) (67.6%, TIMESTAMP(3)
  cast to (6)) rolled up from OB_DEAL_TRANCHE. R3 sizes deal-grain
  expectations for the future batch-3 deploy-check rows.
* TRANCHE_REGION ECM — TT.REGION dead (3/36,352); BATCH 3 edit in
  vw_tranche_summary.sql: NVL fallback to deal region.
* TRANCHE_REGION DCM — view already reads all the source has (13,947 vs
  13,978). TARGET_MARKET is not region vocabulary; not blended. The 81%
  gap is upstream → data-team ticket is the honest close.
* SETTLEMENT_TS ECM — source NOT dead (7,763/29,514 = 26.3%), already
  wired; the remaining 74% is upstream completeness.
* ANNOUNCE_TS/LAUNCH_TS/CLOSING_TS all ZERO in QA — the "announce date
  riches" batch is DEPRIORITIZED until PROD shows data.
CLOSED 2026-08-18 (R1/R2/R3 answered; user: "dont wait, we can push the
view changes" — batch 3 + configs ship together):
* R1 = 1,457/29,384 (5%): ECM deal region is a REAL SOURCE GAP — the
  95,592 region-rich base rows are other business lines; batch 2 only
  lifts 1,340→~1,457. Close = data-team ticket (text below) + partial-
  coverage doctrine (applied).
* R2 = NAM/EMEA/APAC + rare JAPAN(768)/LATAM(68) — no vocabulary break;
  JAPAN/LATAM added to ontology prose.
* R3 = 8,260/46,931 DCM deals with region, 30,749 with settlement —
  deploy-check rows 1f/1g (added, INFO); 1h = ECM tranche-region fallback.
* CONFIG FLIP APPLIED: deal yaml settlement_ts dimension+filter (range
  ops), settlement_date unsupported-intent DELETED, announced_date refusal
  re-grounded (ANNOUNCE/LAUNCH/CLOSING_TS all zero), deal_region
  de-scoped ECM-only→both products (retired _PRODUCT_PINS entry), tranche
  yaml region prose rewritten (sparse-coverage disclosure), SKILL §3b row
  flipped to answer-it + §3a region prose + §9 announce bullet. Gate
  [round3] pins guard the flip. If the BATCH-3 VIEW DEPLOY ROLLS BACK,
  revert: the settlement_ts/deal_region configs assume the deal-view DCM
  rollups (a stale deploy just returns 0 rows for DCM — degraded, not
  broken, because the columns exist as NULL placeholders since batch 1).
* DATA-TEAM TICKET (ECM region + residual gaps), ready to paste: "ECM deal
  region: only ~5-6% of OPUS ECM deal transactions carry DEAL_REGION on
  any OPUS_BASE_TRANSACTION version (QA). DCM tranche region: 81% of
  OB_DEAL_TRANCHE rows carry no REGION/TRANCHE_REGION. ECM settlement:
  SETTLEMENT_TS populated on only 26% of OPUS_ECM_TRANSACTION rows;
  ANNOUNCE_TS/LAUNCH_TS/CLOSING_TS are 100% NULL. Please advise whether
  upstream loads can backfill these."

### Probe cache (2026-08-18, from the warrants MCP log)
0-row enrich probes measured 49.00s + 42.99s for the SAME two probes a
minute apart (the did_you_mean retry double-pays). Shipped: _cached_probe
TTL memo in bqs/suggestions.py ((sql, params) key, ECM_DCM_SUGGESTION_
CACHE_TTL_SECONDS default 300, bounded 128, also covers disambiguation
probes) + tests/test_suggestion_cache.py + [latency] gate pin. Note: the
log predates the scoped-probe hardening and the catalog rename, so
current builds are already faster on first hit; the cache removes the
retry's re-pay. Companion screenshot 100-rows.jpg shows PASSING top-N-
per-group and healthcare top-5 asks — no action.
