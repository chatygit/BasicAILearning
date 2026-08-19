-- ===========================================================================
-- VW_TRANCHE_SUMMARY — grain: one row per PRODUCT + DEAL_ID + TRANCHE_ID
--
-- FIXES IN THIS REVISION (evidence: views/_docs/_diagnostics-results.md)
--   1. TRANCHE_SIZE deployed as VARCHAR2(480) (Q1), so "top N by tranche
--      size" sorted lexically — '900' beat '1000000'.
--      BOTH branches were character, not just ECM. V8 proved it: comparing
--      DCM TRANCHE_SIZE to a number raised ORA-01722. My earlier reasoning
--      (that 480 = 120 CHAR x 4 bytes meant only the ECM cast was widening
--      the column, so DCM was already NUMBER) was WRONG.
--      V18/V19 then showed the "bad" DCM values are not garbage — they are
--      SCIENTIFIC NOTATION held as text: '11.25E9', '2.3E9', '6.0E8', 44 rows
--      in all, of which 43 are E-notation and one is the literal '1k'.
--      -> both branches now convert with a regex that ACCEPTS E-notation, so
--         the 43 multi-billion tranches convert correctly instead of being
--         discarded. A genuinely unparseable value (the '1k') becomes NULL,
--         never a fake 0 — a missing size must not read as a zero size.
--         NULL source still maps to 0, preserving existing behaviour.
--   2. SECURITIES_MATURITY — REVERTED 2026-08-11, still VARCHAR2.
--      I changed the ECM placeholder to CAST(NULL AS DATE) on the assumption
--      that OB_DEAL_TRANCHE.MATURITY_DATE is a real DATE. Deploy failed with
--      ORA-01790 (expression must have same datatype), which proves it is NOT
--      — it is character data despite the column name. Reverted to
--      CAST(NULL AS VARCHAR2(4000)) so the branches match and the view
--      compiles. Maturity therefore remains an unsortable string; fixing it
--      needs the base column's real type and, if it is text, its date FORMAT
--      before any TO_DATE can be written. Do not retry this without both.
--   3. TENORS was TENOR_VALUE || '-' || TENOR_PERIOD. Oracle concatenation
--      treats NULL as empty, so Q26's 4,808 fully-null rows rendered as a lone
--      '-'.  -> both-null now yields NULL.
--   4. DELIVERY_TYPE was LISTAGG'd across identifier rows, but Q23 shows only
--      17 of 32,862 tranches have more than one distinct value — it is
--      per-tranche, not per-identifier. With up to 1,304 identifiers on a
--      single tranche it rendered the same word 1,304 times and risked
--      ORA-01489.  -> MAX(), not LISTAGG.
--   5. Q24: 6,223 tranches carry two or more identifiers of the SAME type, and
--      both LISTAGGs ordered by IDENTIFIER_TYPE alone, so within a tie the
--      type list and value list could zip in different orders — silently
--      pairing a CUSIP with the wrong ISIN.
--      -> IDENTIFIER_VALUE added as tiebreaker on both, both products.
--   6. Q25: 850 tranches have more than one syndicate member flagged
--      BND_BROKER='true'; MAX(CASE ...) kept only the alphabetically last.
--      -> BND_BANK is now the full pipe list of flagged banks on ECM.
--   7. Q12 unguarded joins, all now pre-aggregated or deduped:
--        TRANCHE_PRODUCT_DETAIL   1,737 dups -> pre-aggregated
--        TRANCHE_DEMAND_CURRENCY  4,547 dups -> pre-aggregated
--        OPUS_BASE_TRANSACTION   ~39.6k dups -> pre-aggregated
--        OB_DEAL_ISSUER             156 dups -> ROWID dedupe (was raw here
--                                   while vw_deal_summary already guarded it,
--                                   so co-issued bonds duplicated tranches)
--        OPUS_ECM_TRANSACTION   dup txn ids  -> ROWID dedupe
--        OPUS_ECM_TRANSACTION_STATUS  1,356  -> pre-aggregated
--
-- DELIBERATELY UNCHANGED: row-exclusion policy, verbatim, both products.
-- ALSO UNCHANGED: DCM sources both TRANCHE_STATUS and DEAL_STATUS from
-- ODT.STATUS, so a DCM deal can report a different status here than on
-- vw_deal_summary (which takes MAX across tranches). Q17 shows the column has
-- case-variant duplicates (priced/Priced), making MAX() unsound either way.
-- Deferred with the other status work.
-- ROUND 2 (2026-08-18, deploy with the batch): EQUITY_TYPE denormalized
-- down from OPUS_ECM_TRANSACTION (same deduped T join, one column added) —
-- the instrument-class axis was deal-view-only, forcing a two-step for every
-- class ask ranked by a tranche metric. DCM branch: CAST(NULL) (ECM-only
-- concept). Ontology/skill flips are STAGED in
-- _review/round2-config-staged.md — apply ONLY after this view deploys.
-- ===========================================================================
CREATE OR REPLACE VIEW "DGSTREAM"."VW_TRANCHE_SUMMARY" AS
SELECT
    'ECM' AS PRODUCT,
    T.DEAL_TRANSACTION_ID AS DEAL_ID,
    T.SYNDICATE_DEAL_NAME AS DEAL_NAME,
    NVL(PCM.PARTY_NAME, NVL(OIN.ISSUER_NAME_BY_GFCID, T.ISSUER_NAME_FROM_SOURCE)) AS ISSUER_NAME,
    NVL(PCM.PARTY_GFCID, T.ISSUER_GFCID) AS GFCID,
    NVL(PCM.PARTY_TICKER, T.ISSUER_TICKER) AS TICKER,
    T.ISSUER_INDUSTRY_SECTOR AS SECTOR,
    OBT.DEAL_REGION AS DEAL_REGION,
    TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) AS TRANCHE_ID,
    TT.TRANCHE_NAME AS TRANCHE_NAME,
    CASE WHEN TT.TRANCHE_OFFER_SIZE IS NULL THEN 0
         WHEN REGEXP_LIKE(TO_CHAR(TT.TRANCHE_OFFER_SIZE),
                          '^\s*[+-]?[0-9]+(\.[0-9]+)?([Ee][+-]?[0-9]+)?\s*$')
         THEN TO_NUMBER(TRIM(TO_CHAR(TT.TRANCHE_OFFER_SIZE)))
         ELSE NULL END AS TRANCHE_SIZE,
    CAST(TT.PRICING_TS AS TIMESTAMP(3)) AS PRICING_TS,
    TDC.CURRENCY_NAME AS CURRENCY,
    -- 2026-08-18 (BATCH 3, ticket #100): TT.REGION measured 3/36,352 — dead at
    -- the ECM tranche source. Fall back to the deal's region (ECM deals are
    -- mostly single-tranche, so the deal region IS the tranche's market).
    NVL(TT.REGION, OBT.DEAL_REGION) AS TRANCHE_REGION,
    CAST(NULL AS VARCHAR2(4000)) AS PRODUCT_CLASS,
    CAST(NULL AS VARCHAR2(400)) AS SENIORITY,
    CAST(NULL AS VARCHAR2(400)) AS REG_CATEGORY,
    CAST(NULL AS VARCHAR2(200)) AS ESG_BOND,
    CAST(NULL AS VARCHAR2(400)) AS COUPON_TYPE,
    CAST(NULL AS VARCHAR2(400)) AS COUPON_FREQ,
    T.USE_OF_PROCEEDS AS USE_OF_PROCEEDS,
    TPD.SECURITY_TYPE_NAME AS PRODUCT_TYPE,
    TPD.EXCHANGE AS EXCHANGE,
    T.SETTLEMENT_CURRENCY_NAME AS SETTLEMENT_CURRENCY,
    CAST(NULL AS VARCHAR2(4000)) AS TRANCHE_STATUS,
    S.STATUS_VALUE AS DEAL_STATUS,
    S.STATUS_TYPE AS EXECUTION_STATUS,
    SYN.SYNDICATE_MEMBER_NAME AS SYNDICATE_MEMBER_NAME,
    SYN.SYNDICATE_ROLE AS SYNDICATE_ROLE,
    SYN.BROKER_CODE AS BROKER_CODE,
    SYN.BND_BROKER AS BND_BROKER,
    SYN.BND_BANK AS BND_BANK,
    IDN.IDENTIFIER_TYPE AS IDENTIFIER_TYPE,
    IDN.IDENTIFIER_VALUE AS IDENTIFIER_VALUE,
    CAST(NULL AS VARCHAR2(4000)) AS DELIVERY_TYPE,
    CAST(NULL AS VARCHAR2(4000)) AS ISSUER_RATINGS,
    CAST(NULL AS VARCHAR2(4000)) AS TENORS,
    CAST(NULL AS VARCHAR2(4000)) AS SECURITIES_MATURITY,
    NVL(DST.DEAL_SHARING_TYPE, 'SHARED') AS DEAL_SHARING_TYPE,
    T.PRODUCT_EQUITY_TYPE_VALUE AS EQUITY_TYPE
FROM (
    SELECT W.*
    FROM (
        SELECT TTR.*,
               ROW_NUMBER() OVER (PARTITION BY ETX.DEAL_TRANSACTION_ID,
                                               TTR.ECM_TRANSACTION_TRANCHE_ID
                                  ORDER BY TTR.ROWID) AS RN_
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TTR
        JOIN (SELECT DISTINCT ECM_TRANSACTION_ID, DEAL_TRANSACTION_ID
              FROM DGSTREAM.OPUS_ECM_TRANSACTION) ETX
          ON ETX.ECM_TRANSACTION_ID = TTR.ECM_TRANSACTION_ID
    ) W
    WHERE W.RN_ = 1
) TT
INNER JOIN (
    SELECT X.*
    FROM (
        SELECT ET.ECM_TRANSACTION_ID, ET.DEAL_TRANSACTION_ID,
               ET.SYNDICATE_DEAL_NAME, ET.ISSUER_NAME_FROM_SOURCE,
               ET.ISSUER_GFCID, ET.ISSUER_TICKER, ET.ISSUER_INDUSTRY_SECTOR,
               ET.USE_OF_PROCEEDS, ET.SETTLEMENT_CURRENCY_NAME,
               ET.PRODUCT_EQUITY_TYPE_VALUE,
               ROW_NUMBER() OVER (PARTITION BY ET.ECM_TRANSACTION_ID
                                  ORDER BY ET.ROWID) AS RN_
        FROM DGSTREAM.OPUS_ECM_TRANSACTION ET
    ) X
    WHERE X.RN_ = 1
) T
    ON TT.ECM_TRANSACTION_ID = T.ECM_TRANSACTION_ID
INNER JOIN (
    SELECT ECM_TRANSACTION_ID,
           MAX(STATUS_VALUE) AS STATUS_VALUE,
           MAX(STATUS_TYPE)  AS STATUS_TYPE
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_STATUS
    WHERE STATUS_TYPE = 'Execution_Status'
      AND STATUS_VALUE NOT IN ('Confidential', 'Withdrawn', 'Terminated')
    GROUP BY ECM_TRANSACTION_ID
) S
    ON T.ECM_TRANSACTION_ID = S.ECM_TRANSACTION_ID
LEFT JOIN (
    SELECT TRANSACTION_ID, MAX(DEAL_REGION) AS DEAL_REGION
    FROM DGSTREAM.OPUS_BASE_TRANSACTION
    GROUP BY TRANSACTION_ID
) OBT
    ON T.DEAL_TRANSACTION_ID = OBT.TRANSACTION_ID
LEFT JOIN (
    SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID,
           MAX(SECURITY_TYPE_NAME) AS SECURITY_TYPE_NAME,
           MAX(EXCHANGE)           AS EXCHANGE
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL
    GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
) TPD
    ON TT.ECM_TRANSACTION_ID = TPD.ECM_TRANSACTION_ID
    AND TT.ECM_TRANSACTION_TRANCHE_ID = TPD.ECM_TRANSACTION_TRANCHE_ID
LEFT JOIN (
    SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID,
           MAX(CURRENCY_NAME) AS CURRENCY_NAME
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY
    GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID
) TDC
    ON TT.ECM_TRANSACTION_ID = TDC.ECM_TRANSACTION_ID
    AND TT.ECM_TRANSACTION_TRANCHE_ID = TDC.ECM_TRANSACTION_TRANCHE_ID
    AND TT.TRANCHE_CURRENCY_ID = TDC.CURRENCY_ID
LEFT JOIN (
    SELECT
        S.ECM_TRANSACTION_ID,
        S.ECM_TRANSACTION_TRANCHE_ID,
        LISTAGG(S.SYNDICATE_MEMBER_NAME, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT) WITHIN GROUP (ORDER BY S.BND_BROKER DESC, S.SYNDICATE_MEMBER_NAME) AS SYNDICATE_MEMBER_NAME,
        LISTAGG(S.SYNDICATE_ROLE, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT) WITHIN GROUP (ORDER BY S.BND_BROKER DESC, S.SYNDICATE_MEMBER_NAME) AS SYNDICATE_ROLE,
        LISTAGG(S.BROKER_CODE, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT) WITHIN GROUP (ORDER BY S.BND_BROKER DESC, S.SYNDICATE_MEMBER_NAME) AS BROKER_CODE,
        LISTAGG(S.BND_BROKER, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT) WITHIN GROUP (ORDER BY S.BND_BROKER DESC, S.SYNDICATE_MEMBER_NAME) AS BND_BROKER,
        LISTAGG(CASE WHEN S.BND_BROKER = 'true' THEN S.SYNDICATE_MEMBER_NAME END, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT)
          WITHIN GROUP (ORDER BY S.SYNDICATE_MEMBER_NAME) AS BND_BANK
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE S
    GROUP BY
        S.ECM_TRANSACTION_ID,
        S.ECM_TRANSACTION_TRANCHE_ID
) SYN
    ON TT.ECM_TRANSACTION_ID = SYN.ECM_TRANSACTION_ID
    AND TT.ECM_TRANSACTION_TRANCHE_ID = SYN.ECM_TRANSACTION_TRANCHE_ID
LEFT JOIN (
    SELECT
        I.ECM_TRANSACTION_ID,
        I.ECM_TRANSACTION_TRANCHE_ID,
        LISTAGG(I.IDENTIFIER_TYPE, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT)
          WITHIN GROUP (ORDER BY I.IDENTIFIER_TYPE, I.IDENTIFIER_VALUE) AS IDENTIFIER_TYPE,
        LISTAGG(I.IDENTIFIER_VALUE, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT)
          WITHIN GROUP (ORDER BY I.IDENTIFIER_TYPE, I.IDENTIFIER_VALUE) AS IDENTIFIER_VALUE
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL_IDENTIFIER I
    GROUP BY
        I.ECM_TRANSACTION_ID,
        I.ECM_TRANSACTION_TRANCHE_ID
) IDN
    ON TT.ECM_TRANSACTION_ID = IDN.ECM_TRANSACTION_ID
    AND TT.ECM_TRANSACTION_TRANCHE_ID = IDN.ECM_TRANSACTION_TRANCHE_ID
LEFT JOIN (
    SELECT
        S.ECM_TRANSACTION_ID,
        S.ECM_TRANSACTION_TRANCHE_ID,
        CASE
            WHEN COUNT(DISTINCT S.SYNDICATE_MEMBER_NAME) = 1
                AND MAX(S.SYNDICATE_MEMBER_NAME) LIKE '%Citigroup Global%'
            THEN 'SOLO'
            ELSE 'SHARED'
        END AS DEAL_SHARING_TYPE
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE S
    GROUP BY
        S.ECM_TRANSACTION_ID,
        S.ECM_TRANSACTION_TRANCHE_ID
) DST
    ON TT.ECM_TRANSACTION_ID = DST.ECM_TRANSACTION_ID
    AND TT.ECM_TRANSACTION_TRANCHE_ID = DST.ECM_TRANSACTION_TRANCHE_ID

LEFT JOIN (
    -- ISSUER NAME FIX (2026-08-18): the old ECM source column is 100% dead
    -- in QA (0 of 21,195 deals named). OB_DEAL_ISSUER maps GFCID -> NAME
    -- (99.8% of its 74k rows named; 96% of GFCID-carrying ECM deals resolve
    -- — A1-A3, views/_checks/_issuer-name-check.sql). Grouped per GFCID so the join
    -- cannot fan out the grain. Old column kept as PROD fallback via NVL.
    SELECT GFCID, MAX(NAME) AS ISSUER_NAME_BY_GFCID
    FROM DGSTREAM.OB_DEAL_ISSUER
    WHERE GFCID IS NOT NULL AND NAME IS NOT NULL
    GROUP BY GFCID
) OIN
    ON OIN.GFCID = T.ISSUER_GFCID

LEFT JOIN (
    -- ISSUER IDENTITY MASTER (tech end-state, Dumitru + Samir 2026-08-18):
    -- PARTY_NAME/PARTY_GFCID/PARTY_TICKER at PARTY_ROLE='Primary Client'.
    -- Joins DIRECTLY on TRANSACTION_ID = our deal id family (proven by
    -- sample G); QA's copy is largely unloaded (~1,390 named transactions),
    -- so in QA this layer joins almost nothing and the NVL fallbacks carry —
    -- in PROD it becomes the primary source. Latest VERSION wins (the table
    -- appends versions, up to 1,232 rows per transaction measured);
    -- PUBLISHED_TS is NOT NULL. One row per transaction — no fan-out.
    SELECT TRANSACTION_ID, PARTY_NAME, PARTY_GFCID, PARTY_TICKER
    FROM (
        SELECT TRANSACTION_ID, PARTY_NAME, PARTY_GFCID, PARTY_TICKER,
               ROW_NUMBER() OVER (PARTITION BY TRANSACTION_ID
                                  ORDER BY PUBLISHED_TS DESC) AS RN_
        FROM DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
        WHERE PARTY_ROLE = 'Primary Client'
    ) WHERE RN_ = 1
) PCM
    ON PCM.TRANSACTION_ID = T.DEAL_TRANSACTION_ID

UNION ALL

SELECT
    'DCM' AS PRODUCT,
    ODT.DEAL_ID AS DEAL_ID,
    ODT.DEAL_NAME AS DEAL_NAME,
    NVL(PCM.PARTY_NAME, ODI.NAME) AS ISSUER_NAME,
    NVL(PCM.PARTY_GFCID, ODI.GFCID) AS GFCID,
    NVL(PCM.PARTY_TICKER, ODI.TICKER) AS TICKER,
    ODT.ISSUER_SECTOR AS SECTOR,
    ODT.REGION AS DEAL_REGION,
    ODT.TRANCHE_ID AS TRANCHE_ID,
    ODT.NAME AS TRANCHE_NAME,
    CASE WHEN ODT.TRANCHE_SIZE IS NULL THEN 0
         WHEN REGEXP_LIKE(ODT.TRANCHE_SIZE,
                          '^\s*[+-]?[0-9]+(\.[0-9]+)?([Ee][+-]?[0-9]+)?\s*$')
         THEN TO_NUMBER(TRIM(ODT.TRANCHE_SIZE))
         ELSE NULL END AS TRANCHE_SIZE,
    ODT.PRICING_TS AS PRICING_TS,
    ODT.CURRENCY AS CURRENCY,
    ODT.TRANCHE_REGION AS TRANCHE_REGION,
    ODT.PRODUCT_CLASS AS PRODUCT_CLASS,
    ODT.SENIORITY AS SENIORITY,
    ODT.REG_CATEGORY AS REG_CATEGORY,
    ODT.ESG_BOND AS ESG_BOND,
    ODT.COUPON_TYPE AS COUPON_TYPE,
    ODT.COUPON_FREQ AS COUPON_FREQ,
    ODT.USE_OF_PROCEEDS AS USE_OF_PROCEEDS,
    CAST(NULL AS VARCHAR2(4000)) AS PRODUCT_TYPE,
    CAST(NULL AS VARCHAR2(4000)) AS EXCHANGE,
    ODT.SETTLEMENT_CURRENCY AS SETTLEMENT_CURRENCY,
    ODT.STATUS AS TRANCHE_STATUS,
    ODT.STATUS AS DEAL_STATUS,
    CAST(NULL AS VARCHAR2(4000)) AS EXECUTION_STATUS,
    ODT.BD_BANK AS SYNDICATE_MEMBER_NAME,
    CAST(NULL AS VARCHAR2(4000)) AS SYNDICATE_ROLE,
    CAST(NULL AS VARCHAR2(4000)) AS BROKER_CODE,
    CASE
        WHEN ODT.BD_BANK LIKE '%Citigroup Global%'
        THEN 'true'
        ELSE 'false'
    END AS BND_BROKER,
    ODT.BD_BANK AS BND_BANK,
    IDN.IDENTIFIER_TYPE AS IDENTIFIER_TYPE,
    IDN.IDENTIFIER_VALUE AS IDENTIFIER_VALUE,
    IDN.DELIVERY_TYPE AS DELIVERY_TYPE,
    RAT.ISSUER_RATINGS AS ISSUER_RATINGS,
    CASE WHEN ODT.TENOR_VALUE IS NULL AND ODT.TENOR_PERIOD IS NULL
         THEN NULL
         ELSE ODT.TENOR_VALUE || '-' || ODT.TENOR_PERIOD
    END AS TENORS,
    ODT.MATURITY_DATE AS SECURITIES_MATURITY,
    NVL(DST.DEAL_SHARING_TYPE, 'SHARED') AS DEAL_SHARING_TYPE,
    CAST(NULL AS VARCHAR2(4000)) AS EQUITY_TYPE
FROM (
    SELECT V.*
    FROM (
        SELECT DTR.*,
               ROW_NUMBER() OVER (PARTITION BY DTR.DEAL_ID, DTR.TRANCHE_ID
                                  ORDER BY DTR.ROWID) AS RN_
        FROM DGSTREAM.OB_DEAL_TRANCHE DTR
    ) V
    WHERE V.RN_ = 1
) ODT
LEFT JOIN (
    SELECT Z.*
    FROM (
        SELECT DI.DEAL_TRANCHE_ID, DI.NAME, DI.GFCID, DI.TICKER,
               ROW_NUMBER() OVER (PARTITION BY DI.DEAL_TRANCHE_ID
                                  ORDER BY DI.ROWID) AS RN_
        FROM DGSTREAM.OB_DEAL_ISSUER DI
    ) Z
    WHERE Z.RN_ = 1
) ODI
    ON ODI.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
LEFT JOIN (
    SELECT
        T.DEAL_TRANCHE_ID,
        LISTAGG(T.TYPE, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT) WITHIN GROUP (ORDER BY T.TYPE, T.VALUE) AS IDENTIFIER_TYPE,
        LISTAGG(T.VALUE, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT) WITHIN GROUP (ORDER BY T.TYPE, T.VALUE) AS IDENTIFIER_VALUE,
        MAX(T.DELIVERY_TYPE) AS DELIVERY_TYPE
    FROM DGSTREAM.OB_TRANCHE T
    GROUP BY T.DEAL_TRANCHE_ID
) IDN
    ON IDN.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
LEFT JOIN (
    SELECT
        R.DEAL_TRANCHE_ID,
        LISTAGG(R.AGENCY || ' - ' || R.VALUE ||
                CASE WHEN R.OUTLOOK IS NOT NULL
                     THEN '(' || R.OUTLOOK || ')' END, ', ' ON OVERFLOW TRUNCATE '...' WITH COUNT)
            WITHIN GROUP (ORDER BY R.AGENCY) AS ISSUER_RATINGS
    FROM DGSTREAM.OB_TRANCHE_RATING R
    GROUP BY R.DEAL_TRANCHE_ID
) RAT
    ON RAT.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
LEFT JOIN (
    SELECT
        S.DEAL_TRANCHE_ID,
        CASE
            WHEN MIN(S.DEALER) = MAX(S.DEALER)
                AND MIN(S.DEALER) LIKE '%Citigroup Global%'
            THEN 'SOLO'
            ELSE 'SHARED'
        END AS DEAL_SHARING_TYPE
    FROM DGSTREAM.OB_TRANCHE_SYNDICATE_MEMBER S
    GROUP BY S.DEAL_TRANCHE_ID
) DST
    ON DST.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
LEFT JOIN (
    -- ISSUER IDENTITY MASTER for DCM too (2026-08-18): same PROD-intended
    -- source as the ECM branches (RELATED_PARTIES, Primary Client, latest
    -- version). V1's OB_DEAL_ISSUER concat join is KEPT underneath as the
    -- fallback via NVL — exactly V1 behavior when the master has no row.
    -- 2026-08-19: this block previously sat AFTER the closing semicolon
    -- and the GRANTs (bottom-of-file paste, same bug in all three views;
    -- caught by the DEV migration failure). Moved inside the statement.
    SELECT TRANSACTION_ID, PARTY_NAME, PARTY_GFCID, PARTY_TICKER
    FROM (
        SELECT TRANSACTION_ID, PARTY_NAME, PARTY_GFCID, PARTY_TICKER,
               ROW_NUMBER() OVER (PARTITION BY TRANSACTION_ID
                                  ORDER BY PUBLISHED_TS DESC) AS RN_
        FROM DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
        WHERE PARTY_ROLE = 'Primary Client'
    ) WHERE RN_ = 1
) PCM
    ON PCM.TRANSACTION_ID = ODT.DEAL_ID
;
GRANT SELECT ON "DGSTREAM"."VW_TRANCHE_SUMMARY" TO "DGLOBE_ORAAS_TABLEAU_ROLE";
GRANT SELECT ON "DGSTREAM"."VW_TRANCHE_SUMMARY" TO "DGLOBE_ORAAS_RO_ROLE";
GRANT SELECT ON "DGSTREAM"."VW_TRANCHE_SUMMARY" TO "DGLOBE_TABLEAU_RESTRICTED_ROLE";
GRANT SELECT ON "DGSTREAM"."VW_TRANCHE_SUMMARY" TO "DGLOBE" WITH GRANT OPTION;
GRANT SELECT ON "DGSTREAM"."VW_TRANCHE_SUMMARY" TO "DGLOBE" WITH GRANT OPTION;
