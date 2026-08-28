# DCM issue round — intake (opened 2026-08-24)

Same protocol as prod-issues-2026-08-21.md: one entry per issue — trace,
root cause, fix, status. SKILL/agents.yaml fixes apply immediately;
ontology/server/view causes join the release train. Release-2 configs are
applied in-repo but NOT yet deployed — check whether a reported symptom is
already fixed by release 2 before logging it as new.

## Known DCM terrain (for fast triage — measured facts, not guesses)
- TEN fields are ECM-only and hard-NULL on every DCM row (investor
  region/category, meeting/order/IOI types, offering/equity type,
  order_ownership). A DCM ask touching them = knowably-empty; the agent
  must refuse-and-offer, never run it.
- DCM demand == order_amount (same stored number); fill rate is real but
  ~4M orders carry structural zero allocation ("nothing" vs "not
  recorded" are stored identically — gt 0 filter for "actually allocated").
- deal_status carries case variants ('priced'/'Priced'); tranche and deal
  status read the SAME source column and can disagree with the deal-card
  MAX.
- Two legitimate deal-id families (I-… Ipreo + numeric) — ids are TEXT.
- Regions ~18% populated; settlement_ts rich (~66% deals) but only after
  release 2 exposes the tranche grain.
- Syndicate on DCM is a SINGLE bank string (the B&D bank), not a member
  list; billed_by = BND, 74%.
- OB_ORDER.OWNER / ALL_OWNERS exist but are UNMAPPED (semantics unknown —
  needs census before anyone promises home/away on DCM).
- DCM money needs a single currency scope; no FX column.

## Issues

(awaiting first trace)

## D1 — DCM has no transaction id in the views (user, 2026-08-24)
- **Fact base:** ECM's deal id IS the transaction id. DCM's deal id is the
  OB world's own key — but OB_DEAL_TRANCHE carries
  ORIGINATION_TRANSACTION_ID (col 212), never read by any view, absent
  from V1, never measured. Memory holds nothing more.
- **Why it's bigger than a missing column:** the DCM party-master join is
  keyed TRANSACTION_ID = DEAL_ID on an unproven assumption (QA had the
  master unloaded, so it never mattered). If the true key is the
  origination id, that join never matches in PROD — re-keying could
  unlock the DCM issuer master AND possibly DCM deal regions via
  OPUS_BASE_TRANSACTION.
- **Next:** run _checks/_dcm-transaction-id-check.sql in PROD (T1
  population/consistency, T2 format, T3 join existence, T4 payoff:
  Primary Client + region coverage). Winners = release-train: roll the id
  up to deal grain, expose it as the DCM transaction id, re-key the DCM
  PCM joins in all three views.
- **Status:** measurement queries ready; awaiting T1-T4.

## D2 — Planned prompts assume concepts the views don't carry (2026-08-27)
Prompt sheet topics → support status:
| Concept | Today | Action |
|---|---|---|
| "Transaction ID 75041397" addressing | DCM: UNRESOLVABLE | D1 view fix (in progress): uniform TRANSACTION_ID on all 3 views |
| Hedge book (investors, amounts, managers) | ABSENT | V1/V2 source check |
| Trade book (trade id, salesperson) | ABSENT | V1/V2 source check |
| CV book (book-scoped size/alloc, firm account) | ABSENT | V1/V2 source check |
| Issuer LEI | ABSENT (have GFCID/ticker) | V3 schema search |
| DCM syndicate MEMBERS | only the B&D bank | V4 membership check |
| DCM "allowed order types" | order_type is ECM-only NULL | V2 (find the column) |
| Tranche announcement date | measured 29.5k, unexposed | release-train exposure decision |
| Deal status / tranche count+names / sectors / UoP | SUPPORTED | none |
Queries: _checks/_dcm-books-check.sql (V1-V4). Anything V1/V2 finds is a
release-train candidate; anything absent at source = honest refusal
doctrine + data-team ask.

## D3 — Ran DCM prompts: five suspicious negatives (2026-08-27, traces needed)
1. "top investors, USD, 12 months" → stale-ISIN answer (context bleed)
   then "no matching records" — suspicious; USD DCM orders exist.
2. "top 5 investors, Investment Grade 2026" → "no IG deals in 2026" —
   cross-object (order × tranche.product_class): the mandatory two-step /
   zero-claim rules apply; deployed skill may predate them.
3. "investors never allocated despite orders in 2026" → "found none" —
   near-impossible: ~4M structural-zero allocations exist.
4. "largest deal in NAM 2026" → "no DCM deals in NAM" — region sparsity
   (~18%) needs the disclosure doctrine, not a bare zero.
5. Geography refusals for DCM were CORRECT (ten-NULL-fields doctrine).
Most look like the deployed skill lagging the 2026-08-21 rules
(zero-claim, grain-collision, disclosure). RETEST after the release-2
skill deploy; pull debug traces for any that still fail.

### D2 update — V1-V4 verdicts (2026-08-27): EVERYTHING EXISTS AT SOURCE
| Concept | Verdict |
|---|---|
| Hedge book | OB_DCM_HEDGE_ORDER/TRADE exist — NEW-VIEW scope |
| Trade book (trade id, syndicate) | OB_DCM_ORDER_TRADE(_SYNDICATE) exist — NEW-VIEW scope |
| Salesperson | OB_INVESTOR_SALES + OB_ORDER.SALES_ID/SOEID/names |
| Firm accounts | VG_BCOSMOS_CUSTOMER/GENERAL_ACCOUNT |
| Issuer LEI | ECM: OPUS_ECM_TRANSACTION.ISSUER_LEID (column add). DCM: none found — honest refusal + data-team ask |
| DCM syndicate members | 376,942 rows, 100% DCM-keyed — column/view add |
| DCM investor geography | OB_ORDER COUNTRY/REGION/GEOGRAPHY — our "not available for DCM" is a VIEW placeholder, not data absence |
| DCM classification/QIB/alloc lifecycle | all on OB_ORDER (82 cols; we read 7) |
P-series population queries staged in _checks/_dcm-books-check.sql.
Design note: hedge/trade books are NEW GRAINS (likely new views), not
column adds — needs a design pass after P-series lands. The ten-NULL-
fields refusal doctrine stays until views change, but its wording should
say "not available in this dataset", never "not tracked" — the source
tracks it.
