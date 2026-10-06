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
- [ ] 28. "Show cancelled orders on deal <DCM deal>" — PASS (flipped 2026-09-28):
      says cancelled / deleted orders are excluded by construction on both
      products, so the answer is structurally zero — no doomed query, no
      "none found".
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
      labelled bonds (not shares), full digits with commas, Deal Type column or
      unit stated once.
- [ ] 34. "Provide the list of REGULAR orders across all deals during the last
      5 years" — PASS: ONE table with a Deal Type column (Common Stock /
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
- [ ] 42. "Top 5 investors by allocation on <a convertible ECM deal>" — PASS:
      the FIRST answer says bonds (equity_type in the rows, unit_note in the
      response); no correction needed, no "Allocation (Shares)" header.
- [ ] 41. "Fees on the Visa IPO" — PASS: tranche object; per-share amounts with
      the offer currency; gross spread = underwriting + management + selling
      concession; never a SUM of rows presented as the deal fee.
- [ ] 43. DUAL-ENTITLED login: "demand and allocations for FIDELITY MANAGEMENT
      & RESEARCH in the past 2 years … Deal Name, Pricing Date, Deal Size,
      Offering Type, Deal Type, the BnD Bank, Citi's Role, and the order and
      allocation" — PASS: ONE run_bqs_query on the order object across both
      products (product projected, no per-product split, no "cannot fulfil"),
      one table with a Product column, Offering Type "-" on DCM rows and Deal
      Type = product_class there / equity_type on ECM, B&D bank + Citi role
      from the tranche object as the second step. `column_note` in the response.
- [ ] 44. "Fidelity's indications and allocations on ECM deals priced in
      2025" — PASS: a Deal Type column (equity_type), every cell a bare full-digit
      number, the unit said once per class in prose ("shares for Common Stock,
      bonds for Convertible Bonds"); never "12,000 shares" inside a cell.
- [ ] 45. (after the view deploy) "Show the orderbook for <an ECM deal whose
      book is not yet allocated>" — PASS: Allocation reads "Not recorded" exactly
      like a blank Indication; never "0 shares"; a stored 0 still shows 0.

## FOCUSED RUN — SPACs and the filters bankers actually ask (written 2026-10-04)
Run each prompt TWICE: now (views without batch C — the honest answer is "not
available yet", never a name search or a guess) and after batch C deploys
(the column answers). UAT, fresh session each, ⚡ args captured.
- [ ] 46. "How many SPAC IPOs did we price in 2025?" — NOW: "not available yet"
      (no deal class; never deal_name like '%SPAC%'). AFTER: deal object,
      deal_class like '%SPAC%' + product ECM, a count with the caveat that
      10-digit-id deals carry no class.
- [ ] 47. "List block trades and bought deals in the last 12 months with size
      and issuer" — AFTER: deal_class in ['Blocktrade','Bought Deal'], Deal Class
      column shown, size_unit beside deal_size, no unit in cells.
- [ ] 48. "Accelerated bookbuilds vs fully marketed deals, count by year since
      2023" — AFTER: deal_count by deal_class × year (time_grain), two classes.
- [ ] 49. "Top investors in SPAC IPOs in 2025" — AFTER: order object, ONE
      request (deal_class ferried), equity_type projected (Equity Units).
- [ ] 50. "PIPEs and registered directs priced in 2026" — AFTER: both PIPE
      spellings matched (like '%PIPE%'), 'Registered Direct' second filter in
      the same in-list.
- [ ] 51. "Rights issues in EMEA since 2024" — AFTER: deal_class like '%RIGHTS%'
      + deal_region (sparse — say so) or issuer_country.
- [ ] 52. "ECM deals that priced at more than a 10% discount to last close" —
      AFTER: tranche object, last_close_before_offer is_not_null + price,
      discount computed in the answer per row, population caveat (~27%).
- [ ] 53. "Which deals were upsized in 2025?" — AFTER: initial_deal_size vs
      tranche_size, both figures shown, never a bare 'upsized' label.
- [ ] 54. "Pure secondary sell-downs (no primary shares) last 2 years" — AFTER:
      primary_shares eq 0 / is_null caveat + secondary_shares gt 0.
- [ ] 55. "ECM tranches over $500m in 2025" — AFTER: tranche_offer_amount gte
      500000000 with currency (never deal_size, which is shares).
- [ ] 56. "Callable high-yield bonds priced in 2025 with their first call date"
      — AFTER: is_callable eq 'Y', call_date / non_call_period shown.
- [ ] 57. "NC3 bonds issued this year" — AFTER: non_call_period like '3-Y%'
      ('<value>-<unit>'); under 1% populated — the answer says so.
- [ ] 58. "Taps and re-openings in 2026" — AFTER: is_tap eq 'Y'.
- [ ] 59. "Perpetual bonds priced since 2024" — AFTER: is_perpetual (never a
      parse of securities_maturity).
- [ ] 60. "Mexican issuers, both products, last 12 months" — AFTER: deal object,
      issuer_country in ['Mexico', 'MX'] (ECM names, DCM ISO-2 codes) across
      both products in ONE request (Product column, no split); DCM adds
      country_of_risk when it differs.
- [ ] 61. "New York law bonds vs English law, count 2025" — AFTER: governing_law
      like '%NEW YORK%' vs '%ENGLAND%' (stored 'England and Wales'), two
      buckets, the ~87% NULL bucket disclosed.
- [ ] 62. "Convertibles: deal sizes in 2025 — are they shares or par?" — AFTER:
      size_unit projected beside deal_size ('bonds' = PAR), never totalled
      with common stock.
Works TODAY (control prompts, run once): "greenshoe exercised in 2025"
(over_allotment_exercised_shares), "lockups expiring next month" (lockup_ts),
"IPOs priced below the range" (reoffer_low_price vs base_price), "144A deals
2025" (reg_category / delivery_type), "green bonds 2026" (esg_bond),
"floating-rate notes 2025" (coupon_type / frn_coupon_index), "US-listed ECM
deals" (exchange like '%NYSE%' / '%NASDAQ%'), "IG USD benchmarks over $1bn"
(product_class + currency + tranche_size).

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

## PROD quick test — 2026-09-25 21:22 (everything promoted 25-Sep: SKILL + agents by hand, server build with the 24-Sep catalogs + product narrowing + entitlement wording; OCP log screenshots only, no answer shots)
| Ask (bk42867, ECM-only in PROD) | object · metric | execute | enrich | Notes |
|---|---|---|---|---|
| "top investors by allocation in Healthcare deals over the last 2 years, grouped by Investor Type" | order · total_allocation, LIMIT 10 | 37.7 s | 0.0 s | product set by the agent (agent_scoped=True); first CyberArk fetch in this pod (FID ecm_starburst_prod), cache after |
| "demand and allocations for FIDELITY MANAGEMENT & RESEARCH in the past 2 years … Deal Name, Pricing Date, Deal Size, Offering Type, Deal Type, the BnD Bank, Citi's Role, and the order and allocation" | order · row_count, 50 rows | 22.5 s | **20.1 s** | DISCOVERY HOPS warning: order + tranche catalogs fetched (B&D bank / Citi role are tranche-grain — the two-step is legitimate here). investor_name NOT projected → the disambiguation probe ran as a second serial scan (§0b rule "always PROJECT the name field you filter on" ignored). 50 rows = the default limit → truncated |
| "the Indications and Allocations for GQG Partners on equity deals" | order · row_count | (not in shot) | | investor_name projected this time (probe free). DISCOVERY HOPS again: tranche catalog fetched for an order-only question — pure token cost |
What the log proves: the PROD entitlement API answers (1.6 s, then cached), the gate scopes to ECM, the promoted product rule holds (no unscoped query), nine catalogs load. What it cannot show: answer shape/style, whether the Ipreo views are the PROD revision (needs deploy-check A0 by an access holder), narrowing (never triggered — every ask carried a product filter).

## Dual-entitlement failure — 2026-09-29 (test user with ECM + DCM; screenshots BIG-issue / big-issue-2)
Prompt 43 as typed. The agent's request listed `offering_type` (ECM-only) as a
dimension on the both-products scope → `product_not_applicable` ("exists only on
ECM … add product eq 'ECM' or drop it"). It then planned an ECM query + a DCM
query (product_class instead), never added the product filter, hit the same
rejection and surfaced it verbatim: "I am sorry, I cannot fulfill this request".
User: "It's one view. The user didn't ask to filter on offering type — list it
as '-' for DCM. Tons of test users have both entitlements. This answer is bad."
FIX (repo 2026-09-29, SRV-10): a LISTED single-product column never narrows or
rejects (planner `blank_dims` + response `column_note`); only filters and the
metric decide the product; SKILL §3c-ter rewritten (list freely, filter scoped;
the old "add product eq whenever you touch one" rule removed); order/deal cards
say a listed column is blank, never split. Re-run 43 after the server push.

## PO UAT feedback — 2026-09-29 (ECM labelling, chat 4edda2f5; screenshots labelling-1 / labelling-2)
| # | PO item | Verdict | Fix |
|---|---|---|---|
| 1 | Convertible Preferred indications / allocations shown as shares, not bonds | known — SRV-9 first-pass failure; the promoted SKILL says bonds but the rows carried no equity_type | server: equity_type auto-projected + unit_note (repo 2026-09-28, undeployed); QA 42 |
| 2 | blank indication → "Not recorded", but allocation → "0 shares" — expected? | NO — ours: the order view wrapped the allocation in NVL(…, 0) on every branch, so "nothing recorded" became a zero | NVL dropped (pending view batch); order card: NULL = not recorded, 0 = stored zero; deploy-check 28/28b; census L3; QA 45 |
| 3 | "shares / units / bonds" behind every value in the rows — expected? | NO — headers were bare by rule, and the agent moved the unit into the cells; the PO's own option 2 (a Security column) carries the unit | SKILL §6b "TABLE CELLS ARE BARE NUMBERS", agents.yaml "cells are bare numbers"; QA 44 |
| 4 | deal types recorded in the Security column | census L1/L2 (UAT 2026-09-29): deals since Oct-2025 carry equity type 'Equity' and a compound offering type ('Common Stk - Block Trade', 'Capital Markets Advisory'…) — a new OPUS source shape, not an agent guess | catalogs: vocabulary + like '%IPO%' + 'Equity' = read the security from the offering-type prefix (train); view SECURITY MAP staged (BACKLOG §3); source questions ASKS-external §5; PROD census |
| 5 | (user 2026-10-05) table headed 'Security' with 'preferred shares' prose — "we should always show the type as Deal Type" | OURS: I named MA's product-type column 'Security' on 2026-09-18 and carried it into the SKILL, agents, cards and unit_note; PO item 4 was about this header, not the data | renamed everywhere: equity_type = 'Deal Type', deal_class = 'Deal Class'; Convertible Preferred counts in bonds, never 'preferred shares' (order card + unit_note); gate [label] |
Census L (UAT 2026-09-29, screenshots 1-5): L1 ECM deals by security × deal type — Common Stock 17,310 (17,307 Ipreo, offering type blank; latest date 2099-02-15 = a source placeholder) + 6,283 IPO + 3,425 FO; Equity Units 3,974 FO / 2,284 IPO / 273 blank; Convertible Bonds 3,881 blank (1,229 Ipreo) / 688 FO / 249 IPO; Convertible Preferred 1,315 / 193 / 102; Warrants 365 FO / 292 IPO; Exchangable Notes 162 / 61 / 46; NEW SHAPE 'Equity' × 'Capital Markets Advisory' 49, 'Common Stk - Follow on' 36, '- IPO' 8, '- Block Trade', '- ADR', '- Broking', '- Private Equity' 2, '- AEO' 1, '- SPAC IPO' 1, '- COP' 1, 'Convertible - Debt' (Oct-2025 → Sep-2026); one 'IPO' × 'IPO' deal (2023-08-12). L2: the 20 newest 'Equity' deals are EMEA ECM sprint deals (75076060-75078113), deal size NULL. L3: allocation NULL / ZERO / POSITIVE — OB_ECM_ORDER ~97k NULL (61,926 UNACKNOWLEDGED + 35,246) / 392 zero; IPREO_OB_ECM_ORDER 113,749 / 104,624 / 458,828; OB_ORDER non-RQ 1,107,717 / 12,257 / 196,264.
Census P (UAT 2026-10-05, shots P0-P5): P0 all 21 source names valid (+ the Ipreo mirror's ISSUER_COUNTRY_NAME); BASE_PRIMARY/SECONDARY_SHARES are VARCHAR2. P1 DCM flags: CALL_IND / IS_TAP / IS_CONVERTIBLE = 'Y' or NULL; MAKE_WHOLE_CALLABLE / PERPETUAL_MATURITY / PUT_IND = 'true' / 'false' / NULL (perpetual true 210). P2: NON_CALL_PERIOD is a unit (M/Y) — value in NON_CALL_VALUE; GOVERNING_LAW 'State of New York' 9,514 / 'England and Wales' 42; EXCHANGE_LISTING_VENUE free text; SMC_ISSUER_COUNTRY ISO-2 codes (US 12,479). P3 ECM tranche populations: primary 72%, secondary 72%, last close 27% / 34%, initial 80%, offer amount 78%. P4: OFFERING_FORMAT = '144A only' or NULL; deal class counts (Marketed 14,705, PIPE 4,235 over two spellings, Rights 999, SPAC 606, Blocktrade 154). P5: SFC_ROLE = HK SFC intermediary capacity, not Citi's role — lead closed.
Batch C deploy on QA (2026-10-05 10:52, shots A0 / A / B-1 / C): A0 three views recreated; A 12/12 PASS (43 / 89 / 65); B-ECM 8/8 PASS in 7 s — B07 6,530 of 19,583 Ipreo deals with orders, B08 18,542 classed / 6,648 bonds-unit of 39,696 ECM deals; C 9/9 PASS in 15 s — C06 36,241 DCM tranches, C07 8,794 fee / 10,548 price of 19,973 Ipreo tranches, C08 6,553 / 26,210 / 34,388 / 32,056 of 55,767 ECM tranches, C09 36,241 / 36,241 / 388 / 407 / 21,627 of 36,241 (callable and tap non-NULL on EVERY QA row — QA stores a negative value where UAT stores NULL; db-asks Q). B-DCM hung (the order-book aggregate, QA PGA limit) — the row that needs it, B11, is now a separate optional statement. Rerun of the split B-DCM: 62 s, B09 / B10 / B12 PASS, B13 21,058 DCM deals, B14 20,860 class / 13,145 country. Batch C verified on QA: A0, A, B-ECM, B-DCM, C all PASS.
Census Q (QA 2026-10-06, shots 1-2): IS_CALLABLE and IS_TAP store 'N' / 'Y' (UAT: NULL / 'Y'); IS_PUTTABLE, MAKE_WHOLE_CALLABLE, IS_PERPETUAL 'true' / 'false' / NULL — cards now name 'N' as the negative. Census R (shots 3-6): R1 group table ~104k rows, allocations concentrated in 'new | SBB' (42,914 positive), deleted rows have no primary id; R2 850,910 in-scope orders → 28,087 with a group, 5,740 with a group allocation, 263,313 with an order allocation; R3 167 equal / 27 differ where both exist; R4 OB_ORDER carries the rest of the allocation block. Open: why most allocated groups do not match an in-scope order (db-asks S).
Census S (2026-10-06, shots S1 / S1-2 / S2 / S3): S1 — allocated groups with NO OB_ORDER row for the primary id: SBB 42,967, ISN 3,024, DRB 240, GSP 214, GB 40; matched groups sit in GB→GB new 1,129, SBB→SBB updated 924 / new 706, ISN→ISN updated 614, DRB 347, GSP 257 and smaller cross-source buckets (66 rows). S2 — 54,848 primaries with an allocation, 24 lost by taking the latest version. S3 — group primary ids 'I-240722-…' and order ids 'I-220427-…' share one shape; EXTERNAL_ORDER_ID is numeric, DRB id blank. Verdict: join key and dedupe right; the orders are missing from OB_ORDER (db-asks T, ASKS-external §5 (7)).
Census T (UAT 2026-10-06, shots T1-1 / T2 / T2-2): orphaned allocated groups by deal — SBB: Pembina Pipeline Corp 23,930 groups / 285,868,066,120 (no pricing date, no orders), Air France-KLM 6,010 / 70.9bn, Apple Financial Holdings ×5 (26-28 Nov 2024: 2,587 / 1,392 / 1,392 / 1,293 / 1,293 / 264), Microsoft Corp Test 2,585, Apple Inc Test 1,392, Punjab National Bank 2,000 — the UAT volume loads. Real residue: ISN 2026 deals WITH other orders 1,654 / 423 / 141 / 131 groups, ISN 2024 221 (13.4bn), ISN 2025 deals with NO orders 185 / 138, DRB 89 / 55 / 39 / 13 / 11, GSP 79 / 37 / 25 / 22, GB 39. Next: db-asks U (secondary-list match).
Census U (UAT 2026-10-06, shots U1 / U2): secondary lists are comma-separated 8-digit ids (EXTERNAL_ORDER_ID shape); ISN_ALLOC = FINAL_ALLOC; 3,184 orphaned non-SBB groups carry a list, 0 name one of our orders by ORDER_ID. Next: db-asks V (match on EXTERNAL_ORDER_ID).
Census V (UAT 2026-10-06, shots V1-V3): V1 only 36 of 3,184 orphaned groups name our order by external id (54 orders) — the rest belong to other banks; V2 EXTERNAL_ORDER_ID on 844,940 of 864,019 non-RQ orders, 843,077 distinct keys within deal/tranche; V3 across all allocated groups the external-id match reaches 2,129 in-scope orders, 1,986 not the primary, 1,983 with no allocation of their own → built as the third NVL source. Batch C.1 cleared to deploy.
Batch C.1 deploy (2026-10-06 11:51, shots A0 / A1 / A2 / D): A0 three views recreated; A 12/12 PASS; D-DCM 14.5 s — D06-D09 PASS, D11 807,095 DCM orders, D12 541,171 with no allocation, D13 204,513 allocated (196k own + ~8k from the match group, as census V predicted); D10 reported NULL-status orders present — my row was PASS/FAIL on a UAT-only expectation, now INFO with the count.
