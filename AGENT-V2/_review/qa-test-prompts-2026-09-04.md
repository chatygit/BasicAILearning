# QA test prompts — local run, 2026-09-04 config + views

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
      PASS: top-3 limit with a mass-tie count, not a row dump.

Screenshot misbehavers to ADK as usual; triage happens as a batch.

## Batch 2026-09-15 retests (NEW ENHANCEMENTS register: uat-dcm-feedback-2026-09-15.md)
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
