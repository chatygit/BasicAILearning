# View documentation — extracted from the SQL files (2026-08-19)

User doctrine 2026-08-19: **view files ship comment-free** — the view team
transcribes them into migration scripts, and comment blocks both bloat the
merge surface and obscure statement boundaries (the ORA-00904 PCM paste
hid behind one). All prior in-file documentation lives HERE now, per view,
in original order. The [views] gate rejects any `--` line in vw_*.sql.


## vw_deal_summary.sql


VW_DEAL_SUMMARY — grain: one row per PRODUCT + DEAL_ID

FIXES IN THIS REVISION (evidence: views/_docs/_diagnostics-results.md)
  1. Q9/Q9b: 43,415 rows for 39,467 deals, and the gap is ENTIRELY ECM
     (22,347 rows / 18,399 deals; DCM was already exactly 1:1).
     Q10 found the cause: OPUS_ECM_TRANSACTION holds 44,829 rows /
     43,718 distinct ECM_TRANSACTION_ID / 41,779 distinct
     DEAL_TRANSACTION_ID. So one deal legitimately spans several ECM
     transactions AND the table repeats transaction ids. The view keyed on
     DEAL_TRANSACTION_ID while joining on ECM_TRANSACTION_ID, which cannot
     yield one row per deal.
     -> the ECM branch now aggregates explicitly to DEAL_TRANSACTION_ID,
        and every contributing subquery is re-keyed to the DEAL, not the
        transaction, so multi-transaction deals total correctly instead of
        producing one row each.
  2. Q11: 1,356 transactions carry more than one Execution_Status row.
     -> status pre-aggregated to one row per transaction.
  3. Q12: OPUS_BASE_TRANSACTION has ~39.6k duplicate TRANSACTION_IDs and was
     joined raw purely to fetch DEAL_REGION.  -> pre-aggregated.
  4. DCM CURRENCIES was aggregated without DISTINCT, so a 3-tranche USD deal
     rendered 'USD | USD | USD' where the same ECM deal rendered 'USD'
     (Q21: 6,940 DCM deals affected). -> deduped, matching the ECM branch.
     The DCM currency list is also lifted out of the issuer join so that
     OB_DEAL_ISSUER duplicates (Q12: 156) can no longer inflate it.
  5. ECM CURRENCIES listed TRANCHE_CURRENCY_ID — an INTERNAL ID, not a code.
     Live symptom: the answer carried "For ECM deals, the currencies are
     represented by internal identifiers", and "USD deals" could not match
     ECM at all (0 rows -> 3 wasted hops -> wrong answer via a placeholder
     column). CURRENCY_NAME already existed on ..._TRANCHE_DEMAND_CURRENCY,
     which vw_tranche_summary has always used for its CURRENCY column.
     -> ECM now lists CURRENCY_NAME, falling back to the id when unmapped,
        so ECM and DCM currencies are finally comparable.
     -> 2026-08-14 (NEXT BATCH): a GLOBAL id->name second fallback added —
        the per-tranche lookup misses tranches with no demand-currency row
        (377 QA deals leaked ids, all with globally known names, USD/EUR/
        CAD among them). Raw id remains the last resort; agent renders
        those "not recorded". Post-deploy: _deploy-check row 4b ~ 0.

DELIBERATELY UNCHANGED: row-exclusion policy. The ECM
Confidential/Withdrawn/Terminated filter is preserved verbatim and no new
exclusion is added on either product. Q17 shows DCM carries a
`confidential` status that nothing filters — real, cheap, and a LATER batch.

NOTE ON MULTI-TRANSACTION ECM DEALS: scalar deal attributes are collapsed
with MAX(). Where two transactions of one deal disagree (e.g. DEAL_SIZE),
the larger/last value wins. TRANCHE_COUNT sums across transactions and
FIRST/LAST_PRICED span them, which is the intended deal-level reading.

SECOND FALLBACK (queued 2026-08-14, deploy with the next batch):
the per-(transaction, tranche, currency) TDC join misses tranches
that carry no demand-currency row of their own, leaking raw ids
('1 | 4') into CURRENCIES. Measured in QA: 377 deals, and EVERY
leaked id has a globally known name (1=USD 55k rows, 2=EUR, 4=CAD,
3=GBP, 7=AED, 67=IRR, 76=KYD, 139=TZS — _currency-check.sql Q4),
so a global id->name lookup resolves them all. The raw id remains
the LAST fallback for ids unknown even globally (e.g. a brand-new
currency before its first mapped row); the agent renders those as
"not recorded".
ISSUER NAME FIX (2026-08-18): the old ECM source column is 100% dead
in QA (0 of 21,195 deals named). OB_DEAL_ISSUER maps GFCID -> NAME
(99.8% of its 74k rows named; 96% of GFCID-carrying ECM deals resolve
— A1-A3, views/_checks/_issuer-name-check.sql). Grouped per GFCID so the join
cannot fan out the grain. Old column kept as PROD fallback via NVL.
ISSUER IDENTITY MASTER (tech end-state, Dumitru + Samir 2026-08-18):
PARTY_NAME/PARTY_GFCID/PARTY_TICKER at PARTY_ROLE='Primary Client'.
Joins DIRECTLY on TRANSACTION_ID = our deal id family (proven by
sample G); QA's copy is largely unloaded (~1,390 named transactions),
so in QA this layer joins almost nothing and the NVL fallbacks carry —
in PROD it becomes the primary source. Latest VERSION wins (the table
appends versions, up to 1,232 rows per transaction measured);
PUBLISHED_TS is NOT NULL. One row per transaction — no fan-out.
2026-08-18 (BATCH 3, ticket #100): both were placeholders. OB_DEAL_TRANCHE
carries REGION (13,978/74,281 rows; clean NAM/EMEA/APAC census) and
SETTLEMENT_DATE (50,198/74,281, TIMESTAMP(3)) — rolled up to deal grain.
ISSUER IDENTITY MASTER for DCM too (2026-08-18): same PROD-intended
source as the ECM branches (RELATED_PARTIES, Primary Client, latest
version). V1's OB_DEAL_ISSUER concat join is KEPT underneath as the
fallback via NVL — exactly V1 behavior when the master has no row.
2026-08-19: this block previously sat AFTER the closing semicolon
and the GRANTs (a bottom-of-file paste) — the DEV migration failed
ORA-00904 "PCM"."PARTY_TICKER" because the parsed CREATE had no PCM
join. Moved inside the statement; the gate now polices statement
structure on every view file.

## vw_tranche_summary.sql


VW_TRANCHE_SUMMARY — grain: one row per PRODUCT + DEAL_ID + TRANCHE_ID

FIXES IN THIS REVISION (evidence: views/_docs/_diagnostics-results.md)
  1. TRANCHE_SIZE deployed as VARCHAR2(480) (Q1), so "top N by tranche
     size" sorted lexically — '900' beat '1000000'.
     BOTH branches were character, not just ECM. V8 proved it: comparing
     DCM TRANCHE_SIZE to a number raised ORA-01722. My earlier reasoning
     (that 480 = 120 CHAR x 4 bytes meant only the ECM cast was widening
     the column, so DCM was already NUMBER) was WRONG.
     V18/V19 then showed the "bad" DCM values are not garbage — they are
     SCIENTIFIC NOTATION held as text: '11.25E9', '2.3E9', '6.0E8', 44 rows
     in all, of which 43 are E-notation and one is the literal '1k'.
     -> both branches now convert with a regex that ACCEPTS E-notation, so
        the 43 multi-billion tranches convert correctly instead of being
        discarded. A genuinely unparseable value (the '1k') becomes NULL,
        never a fake 0 — a missing size must not read as a zero size.
        NULL source still maps to 0, preserving existing behaviour.
  2. SECURITIES_MATURITY — REVERTED 2026-08-11, still VARCHAR2.
     I changed the ECM placeholder to CAST(NULL AS DATE) on the assumption
     that OB_DEAL_TRANCHE.MATURITY_DATE is a real DATE. Deploy failed with
     ORA-01790 (expression must have same datatype), which proves it is NOT
     — it is character data despite the column name. Reverted to
     CAST(NULL AS VARCHAR2(4000)) so the branches match and the view
     compiles. Maturity therefore remains an unsortable string; fixing it
     needs the base column's real type and, if it is text, its date FORMAT
     before any TO_DATE can be written. Do not retry this without both.
  3. TENORS was TENOR_VALUE || '-' || TENOR_PERIOD. Oracle concatenation
     treats NULL as empty, so Q26's 4,808 fully-null rows rendered as a lone
     '-'.  -> both-null now yields NULL.
  4. DELIVERY_TYPE was LISTAGG'd across identifier rows, but Q23 shows only
     17 of 32,862 tranches have more than one distinct value — it is
     per-tranche, not per-identifier. With up to 1,304 identifiers on a
     single tranche it rendered the same word 1,304 times and risked
     ORA-01489.  -> MAX(), not LISTAGG.
  5. Q24: 6,223 tranches carry two or more identifiers of the SAME type, and
     both LISTAGGs ordered by IDENTIFIER_TYPE alone, so within a tie the
     type list and value list could zip in different orders — silently
     pairing a CUSIP with the wrong ISIN.
     -> IDENTIFIER_VALUE added as tiebreaker on both, both products.
  6. Q25: 850 tranches have more than one syndicate member flagged
     BND_BROKER='true'; MAX(CASE ...) kept only the alphabetically last.
     -> BND_BANK is now the full pipe list of flagged banks on ECM.
  7. Q12 unguarded joins, all now pre-aggregated or deduped:
       TRANCHE_PRODUCT_DETAIL   1,737 dups -> pre-aggregated
       TRANCHE_DEMAND_CURRENCY  4,547 dups -> pre-aggregated
       OPUS_BASE_TRANSACTION   ~39.6k dups -> pre-aggregated
       OB_DEAL_ISSUER             156 dups -> ROWID dedupe (was raw here
                                  while vw_deal_summary already guarded it,
                                  so co-issued bonds duplicated tranches)
       OPUS_ECM_TRANSACTION   dup txn ids  -> ROWID dedupe
       OPUS_ECM_TRANSACTION_STATUS  1,356  -> pre-aggregated

DELIBERATELY UNCHANGED: row-exclusion policy, verbatim, both products.
ALSO UNCHANGED: DCM sources both TRANCHE_STATUS and DEAL_STATUS from
ODT.STATUS, so a DCM deal can report a different status here than on
vw_deal_summary (which takes MAX across tranches). Q17 shows the column has
case-variant duplicates (priced/Priced), making MAX() unsound either way.
Deferred with the other status work.
ROUND 2 (2026-08-18, deploy with the batch): EQUITY_TYPE denormalized
down from OPUS_ECM_TRANSACTION (same deduped T join, one column added) —
the instrument-class axis was deal-view-only, forcing a two-step for every
class ask ranked by a tranche metric. DCM branch: CAST(NULL) (ECM-only
concept). Ontology/skill flips are STAGED in
_review/round2-config-staged.md — apply ONLY after this view deploys.

2026-08-18 (BATCH 3, ticket #100): TT.REGION measured 3/36,352 — dead at
the ECM tranche source. Fall back to the deal's region (ECM deals are
mostly single-tranche, so the deal region IS the tranche's market).
ISSUER NAME FIX (2026-08-18): the old ECM source column is 100% dead
in QA (0 of 21,195 deals named). OB_DEAL_ISSUER maps GFCID -> NAME
(99.8% of its 74k rows named; 96% of GFCID-carrying ECM deals resolve
— A1-A3, views/_checks/_issuer-name-check.sql). Grouped per GFCID so the join
cannot fan out the grain. Old column kept as PROD fallback via NVL.
ISSUER IDENTITY MASTER (tech end-state, Dumitru + Samir 2026-08-18):
PARTY_NAME/PARTY_GFCID/PARTY_TICKER at PARTY_ROLE='Primary Client'.
Joins DIRECTLY on TRANSACTION_ID = our deal id family (proven by
sample G); QA's copy is largely unloaded (~1,390 named transactions),
so in QA this layer joins almost nothing and the NVL fallbacks carry —
in PROD it becomes the primary source. Latest VERSION wins (the table
appends versions, up to 1,232 rows per transaction measured);
PUBLISHED_TS is NOT NULL. One row per transaction — no fan-out.
ISSUER IDENTITY MASTER for DCM too (2026-08-18): same PROD-intended
source as the ECM branches (RELATED_PARTIES, Primary Client, latest
version). V1's OB_DEAL_ISSUER concat join is KEPT underneath as the
fallback via NVL — exactly V1 behavior when the master has no row.
2026-08-19: this block previously sat AFTER the closing semicolon
and the GRANTs (bottom-of-file paste, same bug in all three views;
caught by the DEV migration failure). Moved inside the statement.

## vw_order_detail.sql


VW_ORDER_DETAIL — grain: one row per PRODUCT + ORDER_ID

FIXES IN THIS REVISION (evidence: views/_docs/_diagnostics-results.md)
  1. DCM ORDER_ALLOCATION was sourced from OB_ORDER_MATCH_GROUP joined on
     (ROOT_ID, PARENT_ID) — deal+tranche, never the order. Q37: only 0.47%
     of orders are reachable that way; Q8: the table has NO rows for the
     busiest tranches, so NVL(...,0) reported allocation as ZERO for them,
     while Q8 showed SUM(OB_ORDER.FINAL_ALLOC) reconciles to TRANCHE_SIZE.
     -> join deleted, allocation read from OB_ORDER.FINAL_ALLOC.
  2. Q9: 11,881,246 rows for 5,874,386 distinct orders (~2x duplication).
     Every unguarded join below is now pre-aggregated or deduped:
       OB_ECM_ORDER_IOI      20,739 dup ORDER_IDs  -> MAX(LIMIT_VALUE)
       OB_ECM_ORDER             101 dup ORDER_IDs  -> ROWID dedupe
       OB_ORDER                   6 dup ORDER_IDs  -> ROWID dedupe
       OB_ORDER_SIZE            314 dup ORDER_IDs  -> MAX(AMT)
       OPUS_ECM_TRANSACTION   dup ECM_TRANSACTION_ID (Q10) -> ROWID dedupe
       OPUS_ECM_TRANSACTION_STATUS 1,356 multi-row (Q11) -> pre-aggregated
       TRANCHE_DEMAND_CURRENCY 4,547 dups          -> MAX(CURRENCY_NAME)
       OB_DEAL_TRANCHE        dup (DEAL_ID,TRANCHE_ID) -> ROWID dedupe
DELIBERATELY UNCHANGED: row-exclusion policy. Every predicate that was in
the deployed view is preserved verbatim, and no new exclusion is added.
Q19 shows DCM applies no order-status filter while ECM drops
CANCELLED/DELETED/PASS, and Q17 shows DCM carries a `confidential` status
nothing filters — both are real, both are cheap, both are a LATER batch.
This revision changes only grain and value correctness.

Dedupes order by ROWID: deterministic, and no assumption about which
columns exist for a "latest row" tiebreak. Duplicate counts are small.

ROUND 2 (2026-08-18, deploy with the batch):
  * BILLED_BY — the per-order billing bank the source always had and no
    view ever read. DCM: OB_ORDER.BND (74% populated; VARIES within 53% of
    tranches, so the tranche designation was hiding real attribution).
    ECM: OB_ECM_ORDER.BILLEDBY_BROKER_CODE — the column NAME says code,
    the DATA is full bank names (measured 2026-08-18; ~90% populated),
    the same value-form as DCM's BND, so BILLED_BY is uniform across
    products. Test entities ('Citi (Test Syndicate CMG)') are excluded by
    the existing CITIGROUP GLOBAL MARKETS stem doctrine.
  * OFFERING_TYPE — denormalized from OPUS_ECM_TRANSACTION (existing
    deduped T join): makes "investors in IPOs" ONE request, killing the
    40-id ferry that corrupted a function call in QA. DCM: CAST(NULL).
  * deal_sharing_type DEFERRED: it would need the syndicate join chain
    added to a 5.8M-row view; "sole deals' orders" 2-hops via tranche ids.
Ontology/skill flips are STAGED in _review/round2-config-staged.md —
apply ONLY after this view deploys.

ISSUER NAME FIX (2026-08-18): the old ECM source column is 100% dead
in QA (0 of 21,195 deals named). OB_DEAL_ISSUER maps GFCID -> NAME
(99.8% of its 74k rows named; 96% of GFCID-carrying ECM deals resolve
— A1-A3, views/_checks/_issuer-name-check.sql). Grouped per GFCID so the join
cannot fan out the grain. Old column kept as PROD fallback via NVL.
ISSUER IDENTITY MASTER (tech end-state, Dumitru + Samir 2026-08-18):
PARTY_NAME/PARTY_GFCID/PARTY_TICKER at PARTY_ROLE='Primary Client'.
Joins DIRECTLY on TRANSACTION_ID = our deal id family (proven by
sample G); QA's copy is largely unloaded (~1,390 named transactions),
so in QA this layer joins almost nothing and the NVL fallbacks carry —
in PROD it becomes the primary source. Latest VERSION wins (the table
appends versions, up to 1,232 rows per transaction measured);
PUBLISHED_TS is NOT NULL. One row per transaction — no fan-out.
ISSUER IDENTITY MASTER for DCM too (2026-08-18): same PROD-intended
source as the ECM branches (RELATED_PARTIES, Primary Client, latest
version). V1's OB_DEAL_ISSUER concat join is KEPT underneath as the
fallback via NVL — exactly V1 behavior when the master has no row.
2026-08-19: this block previously sat AFTER the closing semicolon
and the GRANTs (bottom-of-file paste, same bug in all three views;
caught by the DEV migration failure). Moved inside the statement.

# RELEASE 2 (staged 2026-08-21, NOT yet deployed — PROD holds release 1)

Four changes, one batch. Comment-free files; this is their documentation.

## vw_order_detail.sql
1. **Away orders included (user directive):** the ECM branch's
   `IS_OWNED = 'true'` predicate is REMOVED. Safe by design: the
   `(IS_MATCHED and IS_DOMINANT) or not IS_MATCHED` guard is what dedupes
   home/away representations of the SAME order, so inclusion adds only
   genuinely-away rows, no double count. New column ORDER_OWNERSHIP
   (HOME/AWAY from IS_OWNED; NULL when the flag is neither; DCM NULL —
   no such flag on OB_ORDER).
   NOTE FOR RELEASE REVIEW: this changes every ECM total/count on the
   order object (away rows join the population; measured +21,836 rows,
   ~+45%). ORDER_OWNERSHIP IS exposed in the ontology (user confirmed
   2026-08-21 after a brief reversal) — "our orders" = HOME filter; the
   staged config carries the entry.
2. **EQUITY_TYPE denormalized** (PROD issue #3): ET.PRODUCT_EQUITY_TYPE_
   VALUE via the existing deduped T join; DCM CAST(NULL). Collapses the
   "investor X in convertible deals" two-step to ONE request, mirroring
   round-2 OFFERING_TYPE.
3. **CURRENCY global fallback** (PROD issue #2): NVL(TDC.CURRENCY_NAME,
   GC.CURRENCY_NAME) + the GC global lookup join — heals rows where the
   per-tranche demand-currency row is missing. Raw id deliberately NOT a
   fallback at scalar grain (NULL renders "not recorded").

## vw_tranche_summary.sql
4. **CURRENCY global fallback** — same GC join + NVL as the order view
   (the deal/tranche asymmetry of PROD issue #2, healed).

## vw_deal_summary.sql
5. **CURRENCIES in pricing order** (PROD issue #5): both branches' LISTAGG
   now orders WITHIN GROUP BY each currency's MIN(PRICING_TS) (NULLS
   LAST, currency tiebreak) — lead currency first ("USD | CAD"), replacing
   alphabetical. ECM C subquery: SELECT DISTINCT → GROUP BY + MIN(ts);
   DCM CU likewise.
6. **OD counts include away orders** — same predicate change as the order
   view so deal-card ORDER_COUNT/INVESTOR_COUNT count the same population
   as the order object. NOTE FOR RELEASE REVIEW: ECM deal-card counts
   will rise.

Verification: deploy-check rows 1i (structural) + 1j (home/away split);
UNION alias alignment is now gate-enforced ([views] check, branch alias
sequences parsed per file: deal 22/22, tranche 40/40, order 27/27).
Post-deploy config flips are staged in _review/release2-config-staged.md
— apply ONLY after these views deploy.

7. **Tranche-grain SETTLEMENT_TS (added 2026-08-21 when the release was
   confirmed):** DCM = CAST(ODT.SETTLEMENT_DATE AS TIMESTAMP(6)) — UAT
   measured 50,198/74,281 tranches (67.6%); ECM = CAST(NULL AS
   TIMESTAMP(6)) (no measured tranche-level settlement at the ECM source;
   deal-grain settlement_ts already covers ECM at 26%). Enables
   "tranches settling this week" at the natural grain. Ontology exposure
   (products ["DCM"]) is in release2-config-staged.md.

## RELEASE 2 addendum — D1: uniform TRANSACTION_ID (2026-08-27)
All three views gained a TRANSACTION_ID column as the LAST projection:
ECM = DEAL_TRANSACTION_ID (same value as DEAL_ID — the concept made
uniform), DCM = OB_DEAL_TRANCHE.ORIGINATION_TRANSACTION_ID (MAX per deal
in the deal view; direct at tranche/order grain via the ODT join).
PROD-measured 2026-08-27: one otid per deal (T1=0 multis), OPUS 75xxxxxx
family (T2), 88% resolve in OPUS_BASE_TRANSACTION + RELATED_PARTIES (T3);
FORWARD-POPULATED (~890 ids, 2026 Ipreo vintage onward) — historical DCM
deals carry NULL, which the NVL layering absorbs.
THE RE-KEY: all three DCM PCM (party master) joins now key on
ORIGINATION_TRANSACTION_ID instead of DEAL_ID/ROOT_ID — the old key
compared different id families and NEVER matched (proven by format);
OB_DEAL_ISSUER fallbacks unchanged underneath. Bankers address deals as
"Transaction ID 75041397" (test prompt sheet) — this column resolves
those asks on both products.

## RELEASE 3 (staged 2026-08-28 — D1 + the measured DCM wave; deploy
## after release 2 verifies)
1. TRANSACTION_ID on all three views (D1): ECM = the deal id itself;
   DCM = ORIGINATION_TRANSACTION_ID (deal view: MAX rollup — one per
   deal proven, T1). Forward-populated (~945 PROD deals, 2026 Ipreo
   vintage onward). DCM PCM (party master) joins RE-KEYED to it — the
   old TRANSACTION_ID = DEAL_ID guess never matched a row (format
   mismatch proven); OB_DEAL_ISSUER fallbacks unchanged underneath.
2. ISSUER_LEI (deal + tranche): ECM = OPUS_ECM_TRANSACTION.ISSUER_LEID
   (~83% PROD); DCM = CAST(NULL) (no source column found — data-team
   ask stands).
3. Order view DCM branch: INVESTOR_REGION = OB_ORDER.COUNTRY_NAME (~95%
   source), INVESTOR_CATEGORY = OB_ORDER.TYPE (~67%; Asset managers/
   Banks/... vocabulary, case variants) — two of the "ten ECM-only NULL"
   placeholders now carry real DCM data. INVESTOR_CATEGORY_KEY stays
   NULL on DCM.
4. Order view both branches: SALES_PERSON — DCM = TRIM(FIRST_NAME || ' '
   || LAST_NAME) from OB_ORDER (~30% via SALES_ID census; both-null
   trims to NULL, the tenors lesson); ECM = CAST(NULL) (OB_ECM_ORDER
   sales columns unmeasured — measure before wiring).
5. Tranche view DCM: SYNDICATE_MEMBER_NAME = NVL(full member pipe list
   from OB_TRANCHE_SYNDICATE_MEMBER [DISTINCT per tranche, 376,991 rows
   100% DCM-keyed], BD_BANK fallback). SEMANTIC CHANGE: the DCM value
   was the single B&D bank; it is now the syndicate list when members
   exist. BND_BANK/BND_BROKER unchanged — B&D asks unaffected.
CONFIG COUPLING (post-deploy round): investor_region + investor_category
lose their ECM-only scoping (retire 2 _PRODUCT_PINS, ten-list -> eight);
transaction_id/issuer_lei/sales_person exposure; syndicate_member_name
DCM prose rewrite. Do NOT apply before this batch deploys.

## RELEASE 3b (drafted 2026-08-28 from CLEAN descs — the OCR-guess ban held)
NEW VIEW vw_hedge_order (OB_HEDGE_ORDER, 300,741 rows): grain = one row
per HEDGE_ORDER_ID (latest PUBLISHED_TS wins, ROWID tiebreak). PRODUCT =
'DCM'. Keys DEAL_ID/TRANCHE_ID/ORDER_ID = ROOT/PARENT/SIBLING_ID — joins
the existing views directly. HEDGE_MANAGER = BND ("hedges managed by
Wells Fargo" = filter it). HEDGE_STATUS includes 'cancelled' — kept
queryable, not filtered. Naming mirrors the order view (INVESTOR_REGION =
country name, INVESTOR_CATEGORY = type, SALES_PERSON trimmed-name).
NEW VIEW vw_trade_detail (OB_ORDER_TRADE, 489,400 rows): grain = one row
per ORDER_TRADE_ID (latest PUBLISHED_TS). TRADE_ID + TRADE_REFERENCE
(external ref), counterparty block, TRADE_SIZE/TRADE_ALLOCATION, price
basis, BILLED_BY = BND (consistent with the order view).
ENTITLEMENT: PROVISIONAL (2026-08-28, team confirmation pending) — the
working conclusion: the existing product-level
DCM entitlement covers both new views; no new machinery. CLASSIFICATION
is the DataGlobe FEED-SENSITIVITY label (metadata block), NOT the deal
lifecycle status the ECM branches filter — it reads 'Confidential' on
~every hedge row AND on OB_ORDER, which the existing views have always
served unfiltered. Filtering it would empty the view; it stays
unfiltered, consistent with precedent. Exposure hold LIFTED — hedge/
trade ontology objects join the post-deploy config round.
Deferred: ECONOMIC_* money columns (semantics unmeasured), sales
override block, comments blocks, FROM/TO account columns (firm-account
design pending), OB_ORDER_TRADE_SYNDICATE (43,608 rows — second batch).

## RELEASE 3 — WAVE A "fat views" (2026-08-28, user direction: maximize
## the view surface NOW; whitelisting is the slow gate, configs are ours)
Every column below EXISTS at source (desc'd inventories); populations
mostly UNMEASURED — deliberate: an empty column costs nothing, a missing
one costs a whitelist cycle. Ontology exposure = post-deploy config
rounds, incremental, no view change needed.
* vw_tranche_summary DCM (+16, ECM typed NULLs): COUPON, YIELD, PRICE,
  PRICE_GUIDANCE, ORDER_BOOK_SIZE_USD (VARCHAR2 at source — no TO_NUMBER
  until measured), TOTAL/UNDERWRITING/MANAGEMENT/SELLING_CONCESSION
  (source spelling CONSESSION, aliased corrected)/PRAECIPIUM/RETAIL_UW
  fees, ANNOUNCEMENT/ISSUE/TRADE_TS, TARGET_MARKET, FRN_COUPON_INDEX.
* vw_deal_summary: ECM DEAL_FEE_MM+CURRENCY, DEAL_SIZE_MM+CURRENCY (the
  OPUS money size; DCM NULLs); FIRST_ANNOUNCED (DCM = MIN tranche
  announcement — MIN is dup-safe over the raw table; ECM NULL, source
  all-zero). DCM deal-grain fee SUMs deliberately SKIPPED (raw-table dup
  inflation risk) — deal fee totals come from the tranche object's SUM
  over the deduped view at config time.
* vw_order_detail (+22): ECM real: INVESTOR_LEI, ORDER_STATUS. DCM real:
  ORDER_STATUS, INVESTOR_QIB_STATUS, INVESTOR_SUB_TYPE, IS_FIRM_ORDER,
  IS_POT (the order-type pair; case variants), DRAFT/SOFT/ISN_ALLOC
  (VARCHAR2 at source), RETENTION, RATIONALE(+TYPE), FX_CURRENCY,
  OBO_NAME, OBO_LEGAL_ENTITY_ID (firm-account candidates), ESG_TAG,
  ORDER_SIZE_CHANGE, IS_AFFILIATED, ONE_OFF_INVESTOR, SALES_SOEID.
PRE-HANDOVER: run _checks/_wave-a-name-validation.sql (WHERE 1=0 compile
check on every new source name — instant ORA-00904 on any transcription
typo). WAVE B (needs descs): _checks/_wave-b-desc-requests.sql — unlocks
ECM order riches, ECM trade branch, hedge-trades + trade-syndicate views,
firm accounts, salesperson reference.

## RELEASE 3 — FINAL WAVE (2026-08-31, Wave B complete): NINE VIEWS,
## FULL DOMAIN
NEW: vw_hedge_trade (155,693 — hedge executions; SIBLING = hedge order),
vw_designation (ECM designation cards, 10,696 — firm account, pot
splits, per-card fee economics), vw_trade_syndicate (DCM dealer
designations — SCHEMA-ONLY/EMPTY today; created for the whitelist
window; P1b's 43,608 was a count misalignment, actual 0).
vw_trade_detail is now TWO branches: DCM (OB_ORDER_TRADE) + ECM
(OB_ECM_TRADE_BOOK_INVESTOR_TRADE, 724 rows — the FINRA-style blotter);
+5 columns both branches: TRADE_PRICE, FIRM_ACCOUNT_NUMBER/TYPE,
COMMISSION_RATE, EXECUTION_TS.
ECM FILLS from the Wave B descs: order view — SALES_PERSON =
INVESTOR_SALESPERSON_NAME, SALES_SOEID, IS_FIRM_ORDER, IS_POT
(source IS_POT_ORDER), DRAFT_ALLOC (TO_CHAR of NUMBER), +5 new both
branches: WALL_CROSSED, INVESTOR_CLASSIFICATION (DCM real too),
EXISTING_HOLDER, ACTIVE_PRICE, BOOK_STATUS (kills the book-summary
view — state lives at order grain). Tranche view — six ECM fee fills
(name landmines respected: MANAGEMENT_FEE sing., PRAEPICIUM_FEE,
SELLING_CONCESSION correct on ECM), ANNOUNCEMENT/TRADE_TS fills, +6 new:
GROSS_SPREAD_PER_FEE, DESIGNATION_FEE, OVER_ALLOTMENT_AUTHORIZED/
EXERCISED_SHARES (GREENSHOE — the refusal dies at config time),
FIRST_TRADE_TS, LOCKUP_TS. Deal view — FIRST_ANNOUNCED ECM fill
(ANNOUNCE_TS), +7 new: BASE_PRICE, REOFFER_LOW/HIGH_PRICE (price
range), FX_RATE, ISSUER_COUNTRY, ISSUER_DOMICILE (refusal dies),
OFFERING_FORMAT.
NOT built (recorded): MOGA splits (70 rows — doctrine footnote, not a
view), match-group split (thin), OB_INVESTOR_SALES (contact-email
routing — not analytics), OB_TRANCHE_HEDGE_SECURITY (already
denormalized on hedge rows), VG accounts (out of domain).
PRE-HANDOVER: _checks/_wave-a-name-validation.sql (now 12 statements)
must ALL return "no rows selected". CONFIG ROUNDS AFTER WHITELIST:
hedge_trade/designation/trade_syndicate objects, ECM trade branch
de-scoping, new-column exposure, refusal flips (greenshoe, domicile,
price range, classification-after-census).

## V3 ADDENDUM (2026-08-31, whitelist window): order view + DEAL_REGION
## + TRANCHE_REGION (both branches; ECM = OBT rollup / NULL tranche, DCM
## = ODT.REGION / TRANCHE_REGION — all deploy-proven names). Kills the
## region id-ferry: "investors in NAM deals" = ONE query. Re-hand
## vw_order_detail.

## V3 ADDENDUM 2 (2026-08-31): HELPER-COLUMN ANALYSIS — the ferry dies
Principle: BQS has no query-time joins, so the views carry them. Audit of
every remaining multi-step ask class -> columns added (all source names
deploy-proven; ISSUE_NAME newly validated):
* ORDER VIEW +6: DEAL_REGION/TRANCHE_REGION (addendum 1), DEAL_STATUS
  (both branches — joins already existed), DEAL_SIZE, USE_OF_PROCEEDS,
  SETTLEMENT_TS (DCM). RESULT: NO deal attribute needs the id-ferry any
  more — "investors in priced/NAM/billion-dollar/refi deals" are all ONE
  query once configs expose them.
* TRANCHE VIEW +2: OFFERING_TYPE (ECM — "IPO tranches"), DEAL_SIZE.
* DEAL VIEW +3: TOTAL_DEMAND, TOTAL_ALLOCATION (pre-computed full-book
  roll-ups; the ECM OD subquery also DROPPED the leftover IS_OWNED filter
  release 2 had specified — deal cards now away-inclusive, consistent
  with the order view; ECM counts grow ~45%), SUBSCRIPTION_RATIO
  (demand/size, unit-consistent per product, NULL-safe) — "most
  oversubscribed deals" is one sorted query.
* HEDGE ORDER/TRADE + TRADE VIEWS +1 each: DEAL_NAME (DCM via grouped
  OB_DEAL_TRANCHE name rollup; ECM trade branch = ISSUE_NAME) — readable
  listings, name-scoped asks resolve on the object itself.
CONFIG ROUND AFTER DEPLOY: expose all of the above; SKILL two-step list
becomes EMPTY (mechanism stays as fallback for exotic combos); the
"materiality sample" path then applies only to genuinely exotic asks.

## ADDENDUM 3 — 2026-09-02 latency wave (levers B + C, after index census)

Census facts driving this (screenshots index-1..4, _review/index-review-2026-09-02.md):
OB_ORDER = 5,001,148 rows / OB_ORDER_SIZE = 4,848,439 — and OB_ORDER already carries
IX_OB_ORDER_ROOT_PARENT_ORDER (ROOT_ID, PARENT_ID, ORDER_ID) plus (ORDER_ID), (GPID),
(NAME). Parent-key stability check (census stmt 4): 0 conflicted ids on all five
tables — the PARTITION BY widening below is semantics-preserving.

**Lever B — dedupe PARTITION BY widened with parent keys** so Oracle can push
deal/tranche filters inside the window blocks (pushdown only works on partition
columns) and use the existing indexes:
- vw_order_detail ECM: PARTITION BY EO.DEAL_ID, EO.TRANCHE_ID, EO.ORDER_ID
- vw_order_detail DCM: PARTITION BY DO.ROOT_ID, DO.PARENT_ID, DO.ORDER_ID
  (matches IX_OB_ORDER_ROOT_PARENT_ORDER exactly)
- vw_trade_detail DCM: PARTITION BY OT.ROOT_ID, OT.ORDER_TRADE_ID
- vw_hedge_order: PARTITION BY HO.ROOT_ID, HO.HEDGE_ORDER_ID
- vw_hedge_trade: PARTITION BY HT.ROOT_ID, HT.HEDGE_TRADE_ID
ORDER BY tiebreaks unchanged; dedupe keeps the same single row per id.

**Lever C — vw_deal_summary DCM order aggregate hoisted.** The OC block
(OB_ORDER × OB_ORDER_SIZE, both multi-million-row) moved from INSIDE the deal
derived table D to a top-level LEFT JOIN on OC.ROOT_ID = D.DEAL_ID, mirroring the
ECM branch's OD shape. Values are identical (OC is unique per ROOT_ID; the old
MAX(OC.x) over duplicated tranche rows returned the same single value). Gain:
Oracle can eliminate the unreferenced outer join, so DCM deal questions that don't
touch order_count/investor_count/total_demand/total_allocation/subscription_ratio
no longer pay the 5M-row order-book aggregation (measured 401s for a deal_count).

Files re-handed in this wave: vw_deal_summary, vw_order_detail, vw_trade_detail,
vw_hedge_order, vw_hedge_trade.
