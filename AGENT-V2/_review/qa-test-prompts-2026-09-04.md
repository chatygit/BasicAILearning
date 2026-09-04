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
