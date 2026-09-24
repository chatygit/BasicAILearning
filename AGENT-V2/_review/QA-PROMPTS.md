# QA test prompts — local run, 2026-09-04 config + views

FROM 2026-09-17: run everything on UAT ONLY (local ADK pointed at UAT); the user
will not run QA checks — never ask for them. "QA" below = historical labels.

QA data ≠ UAT/PROD: judge BEHAVIOR SHAPES, not counts. Watch the ADK trace for
QUERY COUNT per ask ("one query" is half of what shipped). Side-captures that
make the session doubly useful: OCP log timings (levers B+C live — deal-scoped
order asks should be seconds) and one Gemini trace promptTokenCount (baseline
~27k static + one catalog; wildly above = something extra loading).

## Headline fixes
- [ ] 1. "List top 10 investors by order size across all USD-denominated deals
      in the last 12 months" — U4. PASS: populated top-10 in ONE query; no
      "Rounding necessary" in server log; no self-widening to 24 months.
- [ ] 2. "For the largest 5 IPOs, show top investors with their allocation and
      indication" — U1 + presentation. PASS: indication populated (not
      all-NULL); no "(Shares)" headers; no-GP-id investors name-filtered.
- [ ] 3. "How much did BlackRock put into refinancing deals in 2025?" — the
      40-query disaster ask. PASS: ONE order-object request
      (use_of_proceeds + investor + dates); no deal-id ferry in the trace.
- [ ] 4. "Which deals are more than 2x oversubscribed this year?" — PASS: one
      deal query, subscription_ratio gt 2, NULL-ratio exclusion disclosed.

## New domains
- [ ] 5a. "Show me recent DCM deals with their transaction ids" (harvest a txn id)
- [ ] 5b. "For Transaction ID <harvested> how many investors are in the hedge
      book?" — PASS: ONE query via transaction_id on the hedge object; honest
      "predates the transaction link, here it is by deal id" is ALSO a pass.
- [ ] 5c. "What is the total hedge amount for the 5YR tranche?" — PASS: one
      query (transaction_id + tenors like-match).
- [ ] 6. "Show designations for deal <X> with firm accounts and approval status"
      — designation object end-to-end.
- [ ] 7. "Find the deal with CUSIP <real QA value>" — PASS: case-insensitive
      contains on tranche identifiers; tranche name shown beside the id.

## Taxonomy flip (test BOTH directions)
- [ ] 8. "Break down orders on deal <X> by investor classification" — PASS:
      real classification values; QA junk ('test', names) called out, not
      presented as taxonomy.
- [ ] 9. "Show investors by category for the same deal" — PASS: uses
      investor_category, DIFFERENT values from #8, no substitution either way.

## Honesty + helpers
- [ ] 10. "List all deals by The Travelers Companies, Inc." (or any QA issuer
      with name variants) — PASS: distinctive-token entity resolution, one
      list, no "narrow by year" deflection.
- [ ] 11. "What's the issuer LEI for <ECM deal>?" then "<DCM deal>?" — PASS:
      ECM answers; DCM = clean honest refusal offering GFCID/ticker.
- [ ] 12. "Show away orders for deal <ECM deal>" — PASS: answers via
      order_ownership = 'AWAY' (the stale refusal is deleted).
- [ ] 13. "Which investors placed orders but were never allocated in 2025?" —
      PASS: one grouped query with having eq 0, not a row-level filter.
- [ ] 14. "Top allocated investor on deal <many same-size allocations>" —
      PASS: VALUE FIRST — one aggregate for the MAX, then the exact set at that
      value; answered by the tie count. Never limit 1 or a limit-3 guess.

Screenshot misbehavers to ADK as usual; triage happens as a batch.

## Batch 2026-09-15 retests (NEW ENHANCEMENTS register: BACKLOG.md §4)
Needs BOTH the nine views AND the config push in QA (+ BQS_ENABLED_SOURCES / new server default).
- [ ] 15. "Give me a list of Fidelity's indications and allocations in all DCM
      priced deals over the past 6 months" — PASS: the investor-given matrix
      (investor · issuer asc · pricing date · deal · tenor · tranche name ·
      indication · allocation · tranche currency), one row per tranche, zero
      rows kept, allocation column present.
- [ ] 16. "Show me the top 5 investors that indicated in origination
      transaction id <real DCM txn id>" — PASS: top 5 PER TRANCHE (partition),
      indication desc then investor asc, not 4-of-5 across tranches.
- [ ] 17. "Did BlueFin trading indicate in origination transaction ID <same>?
      How much?" — PASS: found via a short-name token, one row.
- [ ] 18. "Show me the top 5 investors that indicated in deal name The
      Travelers Co Inc" then "What is the total demand for the 5year tranche?"
      — PASS: distinctive-token issuer match; tenor filter on the order object;
      total in the tranche currency.
- [ ] 19. "Show all USD-denominated deals/tranches by Issuer priced in the last
      12 months, DCM only" — PASS: pricing date (desc) + currency columns echoed;
      both tenor and tranche name shown.
- [ ] 20. "Show demand split by investor geography for the tranche with CUSIP
      <real one>" — PASS: total reconciles to the tranche book; a "region not
      recorded" row or an explicit excluded amount when NULL regions exist (E5).
- [ ] 21. "Show demand split by investor classification for the tranche with
      CUSIP <real one>" — PASS: classification values (hold lifted), not a refusal.
- [ ] 22. "List top 5 investors by allocation across all Investment Grade deals
      in the year 2024" — PASS: ONE order-object query with product_class; no
      "sample of 40 deals" caveat.
- [ ] 23. "List all Citi solo deals/tranches in the year 2024" — PASS: non-empty
      (QA count from _solo-rule-verify statement 3); a deal with only 'Citigroup'
      as dealer appears.
- [ ] 24. "What is the indication for <an ECM investor on an ECM deal>" — PASS:
      a share-equivalent figure (not a price), or the as-submitted amount with
      its unit when the investor bid in currency/percent; never "135 shares".
- [ ] 25. "For Origination Transaction ID 75043505, what are the allowed order
      types for each tranche?" — PASS: per tranche, "Spread, Yield (Max Price
      not allowed)" for both NACN US$ 3NC2 tranches; never "not found".

## Run 1 results — 2026-09-16 (local ADK → QA; screenshots + OCP log summary in ADK)
- 1 PASS · 3 PASS (one query; entity list after a 0 total is noise) · 4 shape
  PASS, values junk (billion-x ratios = tiny test deal sizes) · 5a PASS · 5b
  PASS (txn 75077304, 1 query, 2.7 s) · 15 one query, matrix lacks issuer +
  tenors columns · 16 flat top-5 across the txn, per-tranche unknown (needs ⚡
  args) · 17 FAIL (trade object, deal_id = txn id, 7 queries) → SKILL row ·
  18 five queries / 167 s from product guessing → SKILL row; "next N" re-runs
  the 62 s query (cache) · 23 PASS shape, 5,896 shells · 2 (ran anyway):
  largest IPOs bookless → 0 rows → deal-yaml drill-down rule ·
  metric-in-dimensions x4 (rows 10/14/22 + 2) → standalone trap row.
- Log row 2: Trino "demand_as_submitted cannot be resolved" → run
  views/_checks/db-asks.sql (section B) through Starburst.
- Not yet run: 20, 22, 24. Rerun after an ADK restart on the 16:08+ SKILL:
  17, 18, 16 (capture ⚡ args), 2.

## Run 2 results — 2026-09-17 (views re-deployed)
- 17 PASS (Amundi on 75043505; add the tranche column) · 20 PASS shape (E5
  NULL-region check pending) · 22 PASS · 16 PASS (txn 75064973, 1 investor;
  one slot slip) · 18 FAIL again (ECM guessed; catalogs' "ALWAYS set product"
  → recipe fixed in SKILL + catalogs) · 2 twelve queries, indication dropped
  (trap row rewritten as a recipe).
- Rerun after an ADK restart: 18, 2, 16 on the two-tranche txn 75043505.
  Then 24 and 15 (new columns, now that the views are in).

## Added 2026-09-17 (analysis follow-ups — each is the check for a fix)
- [ ] 26. "What are the coupon, yield, price and total fee of each tranche of
      txn 75043505?" — PASS: tranche object answers (V3 columns); never "no
      rate/fee exists".
- [ ] 27. "List the syndicate members of deal <DCM deal> and how many there are"
      — PASS: the DCM member list + count from one tranche query; no
      "single B&D bank" caveat.
- [ ] 28. "Show cancelled orders on deal <DCM deal>" — PASS: order_status filter
      on the order object; no refusal.
- [ ] 29. "List EMEA DCM deals priced in 2025" — PASS: deal object, deal_region
      eq EMEA + product DCM, one query (deal_region is both products).
- [ ] 30. "What spread over treasuries did <deal> price at?" — PASS: a governed
      refusal ("spread over benchmark is not stored"), offering coupon/yield.
- [ ] 31. "Top investors in deals by Fideltiy" (typo) — PASS: did_you_mean
      suggestion on the 0-row single-string filter, one re-ask.
- [ ] 32. "List every deal" (unscoped deal-view scan) — PASS: limit + a narrow
      offered, or a clean query_timeout — never a silent 300 s client abort.

## Token baseline BEFORE the SKILL compression (UAT/QA runs 2026-09-16/17, fresh sessions)
| Prompt | final-call promptTokenCount | session Total Prompt Tokens |
|---|---|---|
| 1 top 10 investors by order size, USD, 12 months | 61,281 | 132,325 |
| 2 largest 5 IPOs → top investors (allocation + indication) | 89,332 | 368,945 |
| 3 BlackRock in refinancing deals 2025 | 60,560 | 131,795 |
| 15 Fidelity indications/allocations, DCM, 6 months | 64,270 | 135,129 |
| 16 top 5 investors in txn (per tranche) | 61,725 | 194,364 |
| 18 top 5 investors in deal "The Travelers Co Inc" | 64,098 | 268,226 |
AFTER: re-run the same six in fresh sessions on the compressed SKILL (93,427 →
63,402 bytes) and fill a second column pair. Expect the final-call floor to drop
by ~7-8k tokens; session totals also depend on the query count.

## K baselines (UAT 2026-09-18, seconds captured) — the "before" for the view batch
| Probe | Measures | Seconds | Rows |
|---|---|---|---|
| K1 | deal-scoped DCM orders via scalar-subquery id (lever B) | 19.5 | 2 |
| K1b | same with a literal deal id (the agent's shape) | 0.6 | 7 |
| K2 | DCM deal count, no demand columns (lever C) | 28.7 | 47,297 |
| K3 | DCM total demand, full order-book scan (control) | 29.0 | 1 |
| K4 | entity search, full pass | 146.7 | 219,410 |
| K5 | deal-scoped DCM trades | 2.2 | 78 |
| K6 | investor-name-scoped DCM orders, 6 months (Fidelity) | 17.0 | 42 |
| K7 | unscoped aggregate over the order view (V1 go/no-go) | 25.1 | 2 |
K1b proves lever B: deal-scoped asks are sub-second; K1's 19.5 s was the probe's
scalar subquery. Targets: V1 (order-view anti-join) is judged on K6 and must not worsen K7;
V2 (party-master rewrite) on K2; V3 (entity from the base tables) on K4.

## Run 3 — UAT 2026-09-18, compressed SKILL live (fresh sessions)
| Prompt | final-call prompt tokens before → after | session before → after | Result |
|---|---|---|---|
| 1 | 61,281 → 54,897 | 132,325 → 120,002 | PASS, one query; header "Total Order Amount (USD)" (unit parenthetical, E8) |
| 2 | 89,332 → 85,431 | 368,945 → 334,489 | named, booked IPOs (drill-down rule works); per-deal investor tables; "(Shares)" headers |
| 3 | 60,560 → 54,332 | 131,795 → 171,700 (→ 621k after 3 menu turns) | family total given, then a "which entity?" MENU — the disambiguation hint |
| 15 | 64,270 → 55,664 | 135,129 → 120,474 (→ 293k) | per-entity aggregates + MENU; after the pick, the matrix (17 rows, correct columns minus issuer/tenor) |
| 16 / TC1 | 61,725 → 54,332 | 194,364 → 119,285 | FAIL 3rd time: flat top 5 (Investor · GP Id · amount). ⚡ args needed |
| 17 | — | — | PASS: headline with USD 5.0M total, three rows WITH tranche names |
| 20 | — | 320,447 (→ 584k) | product_not_applicable (tenors + product in [ECM,DCM]), then a MENU of three tranches with "two appear to be test entries" (forbidden), then the split; total reconciles 26.75M |
Compression effect on the final call: −6.2k to −8.6k tokens per prompt, as predicted.
Behaviour fixes shipped 2026-09-18 for the failures above: disambiguation = information not a menu
(SKILL §8, §4, agents rule 11, server hint text); product-scoped field decides the product; §3
routing row for top-N in ONE deal/txn; test-entry wording removed everywhere; header unit ban +
five-beat shape added to agents.yaml. Still to run: 18, 24; ⚡ args for 16 and 15.
- [ ] 33. "List all OTT orders in <a convertible ECM deal>" — PASS: figures
      labelled bonds (not shares), full digits with commas, Security column or
      unit stated once.
- [ ] 34. "Provide the list of REGULAR orders across all deals during the last
      5 years" — PASS: ONE table with a Security column (Common Stock /
      Convertible Bonds …) and the unit per class; no total that mixes shares
      and bonds; counts in full digits.
- [ ] 35. "Total demand across all ECM deals this year" — PASS: split by
      demand_unit (shares / bonds / currency / percent), never one number.
- [ ] 36. "top 5 investors that indicated in origination transaction id
      75076736" (TC1 retest, failed 3x) — PASS: ONE query, the per-tranche
      matrix: Investor · GP id · Transaction ID · Deal · Tranche · Indication ·
      Allocation · Tranche Currency, five rows PER TRANCHE, no Product column;
      headline + at-a-glance line above. Capture the ⚡ run_bqs_query args
      whatever the outcome.
- [ ] 37. "Show the Visa IPO deal card" (Ipreo deal 1447528575, QA) — PASS: one deal
      row with issuer VISA, Common Stock, 406,000,000 size, 2,425 orders, priced
      date filled, no "test" wording.
- [ ] 38. "Top 5 investors by allocation on the Visa IPO" — PASS: order object,
      allocation in SHARES, Investment Adviser / Hedge Fund categories shown, the
      Kuwait and Fidelity accounts, no unit in headers.
- [ ] 39. "List convertible deals priced in 2025, ECM" — PASS: both ECM sources
      appear (8-char and 10-digit ids), deal size labelled as a bare number, no
      currency assumed where it is blank.
- [ ] 40. "Long-only investors on <an Ipreo ECM deal>" — PASS: Investment
      Adviser rows included (no _key on those rows), the assumption stated.
- [ ] 41. "Fees on the Visa IPO" — PASS: tranche object; per-share amounts with
      the offer currency; gross spread = underwriting + management + selling
      concession; never a SUM of rows presented as the deal fee.

## Run 4 order (UAT, fresh session each, after the 2026-09-21 promotion)
36 (with ⚡ args) · 15 · 3 · 20 — each must be ONE turn with no "which one?"
menu — then 18 · 24 · 33 · 34 · 35. Screenshot the answer and the session
Total Prompt Tokens.

## Run 4 — UAT 2026-09-21 (SKILL + agents promoted that morning; server = 09-18 build)
| Prompt | final call | session | Result |
|---|---|---|---|
| 15 Fidelity | 64,889 | 184,988 | PASS — ONE turn, all four entities, matrix with tranche/currency/pricing date (issuer + tenor columns still missing); headline splits USD/EUR |
| 3 BlackRock | 57,577 | 234,474 | one turn (was 621k over 3 menu turns); "Allocation (Shares)" header; filler "what stands out" bullets |
| 36 TC1 75076736 | 57,664 | 123,754 | FAIL #4 — args: dimensions [investor_name, investor_id], transaction_id eq, product eq DCM, limit 5; demand aggregated across currencies. ROOT CAUSE: the order card's "Top 10 investors on a DCM deal" EXAMPLE taught this shape — rewritten + txn example added (server push) |
| 20 CUSIP | 99,668 | 425,839 | PASS behaviour — one turn, three tranches, no menu, no "test" wording, 26.75M reconciles; no share bars; two catalogs = the token cost |
| 18 Travelers | 57,867 | 177,983 | PASS — one turn, no product guess (product projected), top 5 with ids; constant Product column shown (should be prose) |
| 34 REGULAR orders 5y | 64,688 | 130,717 | FAIL — 50 rows with NO indication/allocation/unit/Security column; raw timestamps → order-listing rule added |
| 31 OTT orders ECM 1m | 64,242 | ~135k | PASS shape — full-digit figures, dates formatted; unit not stated; "OTT (Over-the-Top)" invented expansion → rule added |
Not run: 24, 35 (the file named 35 is a second shot of 18), 33 as written.

## Run 5 — 2026-09-24 (Ipreo views live on the agent's environment; server = 09-18 build; SKILL + agents = 09-21)
| Prompt | final call | session | Result |
|---|---|---|---|
| 37 Visa deal card | 60,796 | 339,654 | DATA PASS (VISA, 2008-03-18, 406,000,000, 2,425 orders, 698 investors, 14.39x — the Ipreo rows reached the agent through Starburst, so the Trino check is done). BEHAVIOUR: FIVE queries — no product filter, gate injected both, `equity_type` then `offering_type` rejected product_not_applicable (each answered "add product eq ECM or drop the field"; the agent dropped and retried). Name '%VISA%' also matched Televisa — handled by assumption, no menu. Style: "406,000,000 shares" beside Deal Size (bare-number rule), "Use of Proceeds: Not Available" (never "Not Available"), Tranches value blank (view holds 1). execute=40.19s per query (issuer-name filter = full deal-view scan) |
| 38 top 5 investors on Visa (same session) | 63,165 | 464,591 | PASS shape — one query, Fidelity / Kuwait accounts at 19,000,000, tie disclosed and "next 5" offered. Misses: "Allocation (Shares)" header (no unit parentheticals), NO indication column (order listing must carry both figures), investor ids blank |
| 39 convertibles priced 2025, ECM | 68,928 | 124,157 | PASS — one turn, product set (agent_scoped=True), 460 deals, top 50 by date. Cannot tell from the shot whether 10-digit-id deals are in the 460 (Ipreo's latest date is Mar-25, sorted to the tail); no Deal ID column visible; "9,000" and "9000" both rendered |
| 40 long-only investors, ECM 2026 (as typed) | 58,140 | 124,306 | PASS shape — two queries (count + list), 86 investors, first 50 alphabetical with GP ids. Name variants listed as separate rows (ALPINE GLOBAL MGMT LLC with and without an id; ALYESKA; Aberdeen ×2) — the per-id merge rule not applied. Ran on 2026, so no 10-digit-id rows could appear (Ipreo ends Mar-25): the Investment Adviser inclusion is untested |
| 41 fees on the Visa IPO | 13,942 (web agent) | 190,288 | FAIL — our agent ran SIX run_bqs_query calls, gave up, and the root agent handed the question to enterprise_web_search, which answered from the 2008 prospectus ($1.232 per share, $500,192,000 total, $42.768 net per share). Our tranche object holds exactly those fees (1.232 = 0.3388 + 0.3388 + 0.5544) but the deployed catalog (09-18 build) still declares 'fees / gross spread / underwriting fee' an UNSUPPORTED intent on the tranche object — rewritten in the repo 2026-09-24, ships on the train. File 42-1 is a second shot of this answer |
Run 5 complete (37-41). FIX FROM THIS RUN: server narrows a both-products scope to the product a single-product field implies (planner `narrowed_product` + response `product_note`) — prompt 37 becomes one query; ships on the train.
