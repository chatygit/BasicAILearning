# NEW ENHANCEMENTS — UAT DCM banker feedback, batch of 2026-09-15
TAG: NEW ENHANCEMENTS (user directive 2026-09-15: recorded here, batch is
still arriving, implement as ONE config round once complete — do not re-ask
for any of this).

Context: tests run on UAT after 2026-09-09 — i.e. against the **V2 config** (the
V3 push has not happened). Items marked [PUSH] are already fixed in the pending
config push; items marked [NEW] need work; [VIEW] needs a view change; [ASK] is a
semantic question we must not guess.

## A. The DCM orderbook "standard matrix" (requirements 1–7)
Prompt that triggered it: "Give me a list of Fidelity's indications and
allocations, in shares, in all DCM priced deals over the past 6 months."
Issue: allocation column missing from the answer.

1. Two orientations for orderbook asks: investor-given (across issuers) and
   issuer-given (across investors). [NEW — SKILL template]
2. DCM deals are multi-tranche: ONE ROW PER TRANCHE, never collapsed to deal.
   [NEW — SKILL; the order view is already tranche-grain for DCM]
3. ALWAYS include Issuer Name (distinct legal entity; deal names are internal).
   [NEW — SKILL; `issuer_name` exists on the order view for both products]
4. Sort: investor-given → Issuer Name asc; issuer-given → Investor Name asc;
   top-N asks → Indication desc first, then name asc. [NEW — SKILL]
5. Indication & Allocation default in the SECURITY unit (# bonds / # notes;
   ECM # shares); notional ($10mm) only when explicitly asked. [ASK — see Q1]
6. DCM is cross-currency: ALWAYS a Tranche Currency column; indication and
   allocation are in that currency. [NEW — SKILL; `currency` on the order view
   IS the tranche currency for DCM]
7. Issuers repeat deals → ALWAYS a Pricing Date column. [NEW — SKILL;
   `pricing_ts` exists]

The two expected layouts (all columns exist on vw_order_detail today):
- investor-given: Investor Name · Issuer Name (asc) · Pricing Date · Deal Name ·
  Tranche Name · Indication · Allocation · Tranche Currency
- issuer-given: Issuer Name · Pricing Date · Deal Name · Investor Name (asc) ·
  Tranche Name · Indication · Allocation · Tranche Currency
Sample rows KEEP zero-indication / zero-allocation tranches (the book stores
explicit 0 orders) — never filter them out of these matrices. [NEW — SKILL]
Sample tranche names are tenors (3Y/5Y) — bankers think in tenor. [see Q2]

## B. Failed test cases (deal-named asks)
TC1 "Show me the top 5 investors that indicated in origination transaction id
    75043505?" — agent returned 4 investors; ~100 indications across 2 tranches.
    Expected: top 5 PER TRANCHE, Indication desc then Investor asc, with
    Transaction ID · Pricing Date · Deal Name · Tranche Name · Allocation ·
    Tranche Currency. [NEW — recipe: partition_by tranche, per_partition_limit
    5; transaction_id filter on the order object exists]
TC2 "Did BlueFin trading indicate in origination transaction ID 75043505? How
    much?" — agent said no; the client DID indicate. [PUSH — colloquial/short
    name token rule + never-refuse-after-one-attempt; retest; needs the trace to
    rule out an eq-match]
TC3 "Show me the top 5 investors that indicated in deal name The Travelers Co
    Inc?" — "no order information available". [PUSH — the six-spellings issuer
    token recipe; retest after push]
TC4 follow-up: "What is the total demand for the 5year tranche?" — "no demand
    information". Expected one row: Issuer · Pricing Date · Deal Name · Total
    Demand · Tranche Name · Tranche Currency. [see Q2 — tenor is not on the
    order object]

## C. Constraint-columns rule (separate Jira)
When a prompt carries a constraint (last 12 months, sector, high-yield, USD),
ECHO those constraint fields as columns so the user can validate. The
"USD-denominated deals/tranches by Issuer, last 12 months, DCM" answer showed
only Issuer/Deal/Tranche — no currency, no pricing date. [NEW — SKILL rule]

## Decisions taken so we never re-ask (2026-09-15)
Q1 → present DCM indication/allocation AS STORED, in the tranche currency
   (requirement 6 says exactly this); never FX-convert; 'notional in USD'
   = not available unless a USD column exists. No claim about what AMT
   'is' beyond 'the stored amount in tranche currency'.
Q2 → ferry TENORS onto vw_order_detail's DCM branch with the SAME TN join
   the hedge views already use; rides the pending handover (zero extra
   approval), makes TC4 a one-query ask.

## Original questions (kept for the record)
Q1 [ASK] DCM units: our DCM indication/allocation = OB_ORDER_SIZE.AMT /
   FINAL_ALLOC. Is AMT the FACE amount in the tranche currency (which the sample
   4,000,000 USD suggests) — i.e. already "in the security"? And does "notional
   ($10mm) only if prompted" mean a USD-converted figure? Confirm with the desk
   before any unit doctrine is written.
Q2 [VIEW or recipe] Tenor on the order object: "the 5year tranche" cannot be
   filtered on the order view today (TENORS lives on tranche + hedge views).
   Options: (a) ferry TENORS onto vw_order_detail's DCM branch — same TN join
   the hedge views use, rides the pending handover; (b) two-hop recipe (tranche
   object tenor → tranche_id → order object). (a) makes TC4 one query.
   USER DECISION.

## Status
- [ ] rest of the batch received ("more to come")
- [ ] Q1/Q2 answered
- [ ] SKILL: matrix template + constraint-columns rule + zero-row rule + sort rules
- [ ] retest TC1–TC4 after the config push (with traces for TC1/TC2)

## D. Batch continuation (2026-09-15, second drop)
E1 Constraint columns, continued: a TIME constraint → return the one key date,
   Pricing Date, sorted DESC (user may append other dates). Tranche listings
   show BOTH "Tranche" (tenor: 3Y/5Y) AND "Tranche Name" (Domestic-Dell /
   Intl Tranche) — DCM tranches differ by maturity and by name; broad prompts
   can't pick one. [SKILL rule; tranche view has both; order view now too]
E2 CUSIP 63307A3T0 resolved to THREE tranches; the agent summarized one and
   declared the other two "no demand". A CUSIP identifies ONE security —
   investigate: do tranche identifier lists repeat a deal-level CUSIP across
   tranches, or was the contains-match too loose (a 9-char CUSIP must match as
   an exact pipe element; an ISIN search embeds the CUSIP and returns the same
   tranche)? [NEW — probe + SKILL: >1 tranche for one CUSIP = a resolution
   error to diagnose, never a fact to report]
E3 Four CUSIP/ISIN prompts (demand split by geography / by investor
   classification; allocation distribution by classification / by geography):
   partial answers. Classification splits = [PUSH] (V2 refuses classification;
   V3 flipped it). Geography split worked but labelled "Total Demand (USD)" —
   must show the TRANCHE CURRENCY, never assume USD. [SKILL]
E4 "List top 5 investors by allocation across ALL Investment Grade deals in
   2024" → agent sampled 40 largest deals and said a full analysis "is not
   feasible in a single response". ROOT CAUSE: product_class (Investment Grade)
   lived only on the tranche object, forcing a tranche→order id ferry under the
   40-id cap. FIXED AT SOURCE: PRODUCT_CLASS ferried onto vw_order_detail (DCM
   branch, ODT passthrough) + exposed as order filter/dimension — one query, no
   sample, no cap. Same pass ferried TENORS (E1/TC4). [VIEW — rides the
   pending handover; config exposed]
   (57.8bn "BlackRock London" allocation in that answer = UAT test data, not ours.)
