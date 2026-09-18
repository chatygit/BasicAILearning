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
