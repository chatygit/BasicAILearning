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
   order object (away rows join the population).
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
