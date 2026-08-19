-- ===========================================================================
-- VW_DEAL_SUMMARY — grain: one row per PRODUCT + DEAL_ID
--
-- FIXES IN THIS REVISION (evidence: views/_docs/_diagnostics-results.md)
--   1. Q9/Q9b: 43,415 rows for 39,467 deals, and the gap is ENTIRELY ECM
--      (22,347 rows / 18,399 deals; DCM was already exactly 1:1).
--      Q10 found the cause: OPUS_ECM_TRANSACTION holds 44,829 rows /
--      43,718 distinct ECM_TRANSACTION_ID / 41,779 distinct
--      DEAL_TRANSACTION_ID. So one deal legitimately spans several ECM
--      transactions AND the table repeats transaction ids. The view keyed on
--      DEAL_TRANSACTION_ID while joining on ECM_TRANSACTION_ID, which cannot
--      yield one row per deal.
--      -> the ECM branch now aggregates explicitly to DEAL_TRANSACTION_ID,
--         and every contributing subquery is re-keyed to the DEAL, not the
--         transaction, so multi-transaction deals total correctly instead of
--         producing one row each.
--   2. Q11: 1,356 transactions carry more than one Execution_Status row.
--      -> status pre-aggregated to one row per transaction.
--   3. Q12: OPUS_BASE_TRANSACTION has ~39.6k duplicate TRANSACTION_IDs and was
--      joined raw purely to fetch DEAL_REGION.  -> pre-aggregated.
--   4. DCM CURRENCIES was aggregated without DISTINCT, so a 3-tranche USD deal
--      rendered 'USD | USD | USD' where the same ECM deal rendered 'USD'
--      (Q21: 6,940 DCM deals affected). -> deduped, matching the ECM branch.
--      The DCM currency list is also lifted out of the issuer join so that
--      OB_DEAL_ISSUER duplicates (Q12: 156) can no longer inflate it.
--   5. ECM CURRENCIES listed TRANCHE_CURRENCY_ID — an INTERNAL ID, not a code.
--      Live symptom: the answer carried "For ECM deals, the currencies are
--      represented by internal identifiers", and "USD deals" could not match
--      ECM at all (0 rows -> 3 wasted hops -> wrong answer via a placeholder
--      column). CURRENCY_NAME already existed on ..._TRANCHE_DEMAND_CURRENCY,
--      which vw_tranche_summary has always used for its CURRENCY column.
--      -> ECM now lists CURRENCY_NAME, falling back to the id when unmapped,
--         so ECM and DCM currencies are finally comparable.
--      -> 2026-08-14 (NEXT BATCH): a GLOBAL id->name second fallback added —
--         the per-tranche lookup misses tranches with no demand-currency row
--         (377 QA deals leaked ids, all with globally known names, USD/EUR/
--         CAD among them). Raw id remains the last resort; agent renders
--         those "not recorded". Post-deploy: _deploy-check row 4b ~ 0.
--
-- DELIBERATELY UNCHANGED: row-exclusion policy. The ECM
-- Confidential/Withdrawn/Terminated filter is preserved verbatim and no new
-- exclusion is added on either product. Q17 shows DCM carries a
-- `confidential` status that nothing filters — real, cheap, and a LATER batch.
--
-- NOTE ON MULTI-TRANSACTION ECM DEALS: scalar deal attributes are collapsed
-- with MAX(). Where two transactions of one deal disagree (e.g. DEAL_SIZE),
-- the larger/last value wins. TRANCHE_COUNT sums across transactions and
-- FIRST/LAST_PRICED span them, which is the intended deal-level reading.
-- ===========================================================================
CREATE OR REPLACE VIEW "DGSTREAM"."VW_DEAL_SUMMARY" AS
SELECT
    'ECM' AS PRODUCT,
    T.DEAL_TRANSACTION_ID AS DEAL_ID,
    MAX(T.SYNDICATE_DEAL_NAME) AS DEAL_NAME,
    MAX(T.DEAL_SIZE) AS DEAL_SIZE,
    MAX(NVL(PCM.PARTY_NAME, NVL(OIN.ISSUER_NAME_BY_GFCID, T.ISSUER_NAME_FROM_SOURCE))) AS ISSUER_NAME,
    MAX(NVL(PCM.PARTY_GFCID, T.ISSUER_GFCID)) AS GFCID,
    MAX(NVL(PCM.PARTY_TICKER, T.ISSUER_TICKER)) AS TICKER,
    MAX(T.ISSUER_INDUSTRY_SECTOR) AS SECTOR,
    MAX(T.USE_OF_PROCEEDS) AS USE_OF_PROCEEDS,
    MAX(T.PRODUCT_EQUITY_TYPE_VALUE) AS EQUITY_TYPE,
    MAX(T.PRODUCT_OFFERING_TYPE_VALUE) AS OFFERING_TYPE,
    MAX(S.STATUS_VALUE) AS DEAL_STATUS,
    MAX(S.STATUS_TYPE) AS EXECUTION_STATUS,
    MAX(OBT.DEAL_REGION) AS DEAL_REGION,
    MAX(T.SETTLEMENT_TS) AS SETTLEMENT_TS,
    MAX(T.SETTLEMENT_CURRENCY_NAME) AS SETTLEMENT_CURRENCY,
    MAX(TR.TRANCHE_COUNT) AS TRANCHE_COUNT,
    MAX(TR.FIRST_PRICED) AS FIRST_PRICED,
    MAX(TR.LAST_PRICED) AS LAST_PRICED,
    MAX(TC.CURRENCIES) AS CURRENCIES,
    MAX(OD.ORDER_COUNT) AS ORDER_COUNT,
    MAX(OD.INVESTOR_COUNT) AS INVESTOR_COUNT
FROM (
    SELECT X.*
    FROM (
        SELECT ET.*,
               ROW_NUMBER() OVER (PARTITION BY ET.ECM_TRANSACTION_ID
                                  ORDER BY ET.ROWID) AS RN_
        FROM DGSTREAM.OPUS_ECM_TRANSACTION ET
        WHERE ET.DEAL_TRANSACTION_ID IS NOT NULL
    ) X
    WHERE X.RN_ = 1
) T
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
    SELECT ET.DEAL_TRANSACTION_ID,
           COUNT(DISTINCT TT.ECM_TRANSACTION_ID || '~' ||
                          TT.ECM_TRANSACTION_TRANCHE_ID) AS TRANCHE_COUNT,
           MIN(TT.PRICING_TS) AS FIRST_PRICED,
           MAX(TT.PRICING_TS) AS LAST_PRICED
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TT
    JOIN (SELECT DISTINCT ECM_TRANSACTION_ID, DEAL_TRANSACTION_ID
          FROM DGSTREAM.OPUS_ECM_TRANSACTION) ET
      ON ET.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
    GROUP BY ET.DEAL_TRANSACTION_ID
) TR
    ON TR.DEAL_TRANSACTION_ID = T.DEAL_TRANSACTION_ID
LEFT JOIN (
    SELECT C.DEAL_TRANSACTION_ID,
           LISTAGG(C.TRANCHE_CURRENCY_ID, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT)
             WITHIN GROUP (ORDER BY C.TRANCHE_CURRENCY_ID) AS CURRENCIES
    FROM (
        -- SECOND FALLBACK (queued 2026-08-14, deploy with the next batch):
        -- the per-(transaction, tranche, currency) TDC join misses tranches
        -- that carry no demand-currency row of their own, leaking raw ids
        -- ('1 | 4') into CURRENCIES. Measured in QA: 377 deals, and EVERY
        -- leaked id has a globally known name (1=USD 55k rows, 2=EUR, 4=CAD,
        -- 3=GBP, 7=AED, 67=IRR, 76=KYD, 139=TZS — _currency-check.sql Q4),
        -- so a global id->name lookup resolves them all. The raw id remains
        -- the LAST fallback for ids unknown even globally (e.g. a brand-new
        -- currency before its first mapped row); the agent renders those as
        -- "not recorded".
        SELECT DISTINCT ET.DEAL_TRANSACTION_ID,
               NVL(TDC.CURRENCY_NAME,
                   NVL(GC.CURRENCY_NAME, TT.TRANCHE_CURRENCY_ID)) AS TRANCHE_CURRENCY_ID
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TT
        JOIN (SELECT DISTINCT ECM_TRANSACTION_ID, DEAL_TRANSACTION_ID
              FROM DGSTREAM.OPUS_ECM_TRANSACTION) ET
          ON ET.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
        LEFT JOIN (
            SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID,
                   MAX(CURRENCY_NAME) AS CURRENCY_NAME
            FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY
            GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID
        ) TDC
          ON TDC.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
         AND TDC.ECM_TRANSACTION_TRANCHE_ID = TT.ECM_TRANSACTION_TRANCHE_ID
         AND TDC.CURRENCY_ID = TT.TRANCHE_CURRENCY_ID
        LEFT JOIN (
            SELECT CURRENCY_ID, MAX(CURRENCY_NAME) AS CURRENCY_NAME
            FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY
            GROUP BY CURRENCY_ID
        ) GC
          ON GC.CURRENCY_ID = TT.TRANCHE_CURRENCY_ID
    ) C
    GROUP BY C.DEAL_TRANSACTION_ID
) TC
    ON TC.DEAL_TRANSACTION_ID = T.DEAL_TRANSACTION_ID
LEFT JOIN (
    SELECT O.DEAL_ID,
           COUNT(DISTINCT O.ORDER_ID) AS ORDER_COUNT,
           COUNT(DISTINCT O.INVESTOR_GPNUM) AS INVESTOR_COUNT
    FROM DGSTREAM.OB_ECM_ORDER O
    WHERE O.IS_OWNED = 'true'
      AND O.ORDER_STATUS NOT IN ('CANCELLED', 'DELETED', 'PASS')
      AND ((O.IS_MATCHED = 'true' AND O.IS_DOMINANT = 'true') OR O.IS_MATCHED = 'false')
    GROUP BY O.DEAL_ID
) OD
    ON T.DEAL_TRANSACTION_ID = OD.DEAL_ID
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
GROUP BY T.DEAL_TRANSACTION_ID

UNION ALL

SELECT
    'DCM' AS PRODUCT,
    D.DEAL_ID AS DEAL_ID,
    D.DEAL_NAME AS DEAL_NAME,
    D.DEAL_SIZE AS DEAL_SIZE,
    NVL(PCM.PARTY_NAME, D.ISSUER_NAME) AS ISSUER_NAME,
    NVL(PCM.PARTY_GFCID, D.GFCID) AS GFCID,
    NVL(PCM.PARTY_TICKER, D.TICKER) AS TICKER,
    D.SECTOR AS SECTOR,
    D.USE_OF_PROCEEDS AS USE_OF_PROCEEDS,
    CAST(NULL AS VARCHAR2(4000)) AS EQUITY_TYPE,
    CAST(NULL AS VARCHAR2(4000)) AS OFFERING_TYPE,
    D.DEAL_STATUS AS DEAL_STATUS,
    CAST(NULL AS VARCHAR2(4000)) AS EXECUTION_STATUS,
    -- 2026-08-18 (BATCH 3, ticket #100): both were placeholders. OB_DEAL_TRANCHE
    -- carries REGION (13,978/74,281 rows; clean NAM/EMEA/APAC census) and
    -- SETTLEMENT_DATE (50,198/74,281, TIMESTAMP(3)) — rolled up to deal grain.
    D.DEAL_REGION AS DEAL_REGION,
    CAST(D.SETTLEMENT_TS AS TIMESTAMP(6)) AS SETTLEMENT_TS,
    D.SETTLEMENT_CURRENCY AS SETTLEMENT_CURRENCY,
    D.TRANCHE_COUNT AS TRANCHE_COUNT,
    D.FIRST_PRICED AS FIRST_PRICED,
    D.LAST_PRICED AS LAST_PRICED,
    CU.CURRENCIES AS CURRENCIES,
    D.ORDER_COUNT AS ORDER_COUNT,
    D.INVESTOR_COUNT AS INVESTOR_COUNT
FROM (
    SELECT ODT.DEAL_ID,
           MAX(ODT.DEAL_NAME) AS DEAL_NAME,
           MAX(NVL(ODT.DEAL_ISSUE_SIZE, 0)) AS DEAL_SIZE,
           MAX(ODI.NAME) AS ISSUER_NAME,
           MAX(ODI.GFCID) AS GFCID,
           MAX(ODI.TICKER) AS TICKER,
           MAX(ODT.ISSUER_SECTOR) AS SECTOR,
           MAX(ODT.USE_OF_PROCEEDS) AS USE_OF_PROCEEDS,
           MAX(ODT.STATUS) AS DEAL_STATUS,
           MAX(ODT.REGION) AS DEAL_REGION,
           MAX(ODT.SETTLEMENT_DATE) AS SETTLEMENT_TS,
           MAX(ODT.SETTLEMENT_CURRENCY) AS SETTLEMENT_CURRENCY,
           COUNT(DISTINCT ODT.TRANCHE_ID) AS TRANCHE_COUNT,
           MIN(ODT.PRICING_TS) AS FIRST_PRICED,
           MAX(ODT.PRICING_TS) AS LAST_PRICED,
           MAX(OC.ORDER_COUNT) AS ORDER_COUNT,
           MAX(OC.INVESTOR_COUNT) AS INVESTOR_COUNT
    FROM DGSTREAM.OB_DEAL_TRANCHE ODT
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
        SELECT O.ROOT_ID,
               COUNT(DISTINCT O.ORDER_ID) AS ORDER_COUNT,
               COUNT(DISTINCT O.GPID) AS INVESTOR_COUNT
        FROM DGSTREAM.OB_ORDER O
        GROUP BY O.ROOT_ID
    ) OC
        ON OC.ROOT_ID = ODT.DEAL_ID
    GROUP BY ODT.DEAL_ID
) D
LEFT JOIN (
    SELECT C.DEAL_ID,
           LISTAGG(C.CURRENCY, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT)
             WITHIN GROUP (ORDER BY C.CURRENCY) AS CURRENCIES
    FROM (
        SELECT DISTINCT DEAL_ID, CURRENCY
        FROM DGSTREAM.OB_DEAL_TRANCHE
        WHERE CURRENCY IS NOT NULL
    ) C
    GROUP BY C.DEAL_ID
) CU
    ON CU.DEAL_ID = D.DEAL_ID
LEFT JOIN (
    -- ISSUER IDENTITY MASTER for DCM too (2026-08-18): same PROD-intended
    -- source as the ECM branches (RELATED_PARTIES, Primary Client, latest
    -- version). V1's OB_DEAL_ISSUER concat join is KEPT underneath as the
    -- fallback via NVL — exactly V1 behavior when the master has no row.
    -- 2026-08-19: this block previously sat AFTER the closing semicolon
    -- and the GRANTs (a bottom-of-file paste) — the DEV migration failed
    -- ORA-00904 "PCM"."PARTY_TICKER" because the parsed CREATE had no PCM
    -- join. Moved inside the statement; the gate now polices statement
    -- structure on every view file.
    SELECT TRANSACTION_ID, PARTY_NAME, PARTY_GFCID, PARTY_TICKER
    FROM (
        SELECT TRANSACTION_ID, PARTY_NAME, PARTY_GFCID, PARTY_TICKER,
               ROW_NUMBER() OVER (PARTITION BY TRANSACTION_ID
                                  ORDER BY PUBLISHED_TS DESC) AS RN_
        FROM DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
        WHERE PARTY_ROLE = 'Primary Client'
    ) WHERE RN_ = 1
) PCM
    ON PCM.TRANSACTION_ID = D.DEAL_ID
;
GRANT SELECT ON "DGSTREAM"."VW_DEAL_SUMMARY" TO "DGLOBE_ORAAS_TABLEAU_ROLE";
GRANT SELECT ON "DGSTREAM"."VW_DEAL_SUMMARY" TO "DGLOBE_ORAAS_RO_ROLE";
GRANT SELECT ON "DGSTREAM"."VW_DEAL_SUMMARY" TO "DGLOBE_TABLEAU_RESTRICTED_ROLE";
GRANT SELECT ON "DGSTREAM"."VW_DEAL_SUMMARY" TO "DGLOBE" WITH GRANT OPTION;
