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

### D2 update 2 — P-series results (2026-08-28)
* OB_DCM_* book tables = EMPTY SHELLS; the GENERIC tables are live
  (OB_HEDGE_ORDER 300,741 / OB_HEDGE_TRADE 155,693). Trade-book counts
  still pending (P1b: OB_ORDER_TRADE etc.).
* OB_ORDER COUNTRY = 95% populated — DCM INVESTOR COUNTRY IS RICH; the
  "geography not available for DCM" refusal hides it. REGION/GEOGRAPHY
  sparse (1.2/10.7%); SALES_ID 30%; RATIONALE/LEGAL_ID near-dead.
* ECM ISSUER_LEID = 83% — one-column release-3 add.
* OB_INVESTOR_SALES = 19 rows: a salesperson REFERENCE table (id->name),
  joins OB_ORDER.SALES_ID.
* TYPE/SUB_TYPE/IS_FIRM_ORDER/IS_POT = the "allowed order types"
  candidates — P6 census staged.
* RELEASE-3 SHAPE EMERGING: (a) column wave on vw_order_detail — DCM
  INVESTOR_COUNTRY (95%), salesperson (30%), order TYPE fields pending
  P6; (b) ECM ISSUER_LEID on deal/tranche; (c) DCM syndicate members
  exposure (376,991 rows); (d) hedge/trade NEW VIEWS pending P1b/P5
  grain samples. CV book still unlocated (maybe OB_ECM_ORDER_BOOK_* —
  P1b counts them).

### D2 CLOSE — full prompt-to-source map (2026-08-28; numbers approximate
### per user note, some null columns unscreenshotted)
| Prompt concept | Source, confirmed |
|---|---|
| Hedge book: investor count / total hedge amount / "managed by X" | OB_HEDGE_ORDER (300,741): INVESTOR_*, HEDGESIZE_AMOUNT, BND |
| Trade book: trade id / B&D / salesperson | OB_ORDER_TRADE (489,400): ORDER_TRADE_ID, BND; sales via OB_ORDER/HEDGE SALES_* |
| CV book | NOT located by name — candidates: book/trade TYPE columns ('Institutional Pot'/'SyndicateBilled Pot' vocab), OB_ECM_ORDER_BOOK_*; one census at design time |
| Firm account | VG_BCOSMOS_* EMPTY; OBO_NAME/OBO_LEGAL_ENTITY_ID + ACCOUNT_X_PM_ID on orders are the live candidates |
| DCM investor type | OB_ORDER.TYPE (~67%): Asset managers/Banks/... — another "unavailable" field that EXISTS |
| DCM order types | IS_FIRM_ORDER x IS_POT (firm/pot; case variants) |
| Salesperson | OB_ORDER SALES_ID/SOEID/names (30%) + OB_INVESTOR_SALES (19-row ref) + hedge-order SALES_* |
| Issuer LEI | ECM 83% (ISSUER_LEID); DCM absent — data-team ask |
| DCM syndicate members | OB_TRANCHE_SYNDICATE_MEMBER 376,991 rows, 100% DCM-keyed |
| DCM investor country | OB_ORDER.COUNTRY 95% |
GRAIN + ENTITLEMENT DESIGN NOTES for release 3: hedge/trade rows key
deal+tranche+ORDER (SIBLING_ID) — new views join our world directly;
hedge rows are CLASSIFICATION='Confidential' (entitlement gate design
input). Release-3 candidates now fully measured except CV-book naming
and firm-account population.
