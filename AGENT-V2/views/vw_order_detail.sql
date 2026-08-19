-- ===========================================================================
-- VW_ORDER_DETAIL — grain: one row per PRODUCT + ORDER_ID
--
-- FIXES IN THIS REVISION (evidence: views/_docs/_diagnostics-results.md)
--   1. DCM ORDER_ALLOCATION was sourced from OB_ORDER_MATCH_GROUP joined on
--      (ROOT_ID, PARENT_ID) — deal+tranche, never the order. Q37: only 0.47%
--      of orders are reachable that way; Q8: the table has NO rows for the
--      busiest tranches, so NVL(...,0) reported allocation as ZERO for them,
--      while Q8 showed SUM(OB_ORDER.FINAL_ALLOC) reconciles to TRANCHE_SIZE.
--      -> join deleted, allocation read from OB_ORDER.FINAL_ALLOC.
--   2. Q9: 11,881,246 rows for 5,874,386 distinct orders (~2x duplication).
--      Every unguarded join below is now pre-aggregated or deduped:
--        OB_ECM_ORDER_IOI      20,739 dup ORDER_IDs  -> MAX(LIMIT_VALUE)
--        OB_ECM_ORDER             101 dup ORDER_IDs  -> ROWID dedupe
--        OB_ORDER                   6 dup ORDER_IDs  -> ROWID dedupe
--        OB_ORDER_SIZE            314 dup ORDER_IDs  -> MAX(AMT)
--        OPUS_ECM_TRANSACTION   dup ECM_TRANSACTION_ID (Q10) -> ROWID dedupe
--        OPUS_ECM_TRANSACTION_STATUS 1,356 multi-row (Q11) -> pre-aggregated
--        TRANCHE_DEMAND_CURRENCY 4,547 dups          -> MAX(CURRENCY_NAME)
--        OB_DEAL_TRANCHE        dup (DEAL_ID,TRANCHE_ID) -> ROWID dedupe
-- DELIBERATELY UNCHANGED: row-exclusion policy. Every predicate that was in
-- the deployed view is preserved verbatim, and no new exclusion is added.
-- Q19 shows DCM applies no order-status filter while ECM drops
-- CANCELLED/DELETED/PASS, and Q17 shows DCM carries a `confidential` status
-- nothing filters — both are real, both are cheap, both are a LATER batch.
-- This revision changes only grain and value correctness.
--
-- Dedupes order by ROWID: deterministic, and no assumption about which
-- columns exist for a "latest row" tiebreak. Duplicate counts are small.
--
-- ROUND 2 (2026-08-18, deploy with the batch):
--   * BILLED_BY — the per-order billing bank the source always had and no
--     view ever read. DCM: OB_ORDER.BND (74% populated; VARIES within 53% of
--     tranches, so the tranche designation was hiding real attribution).
--     ECM: OB_ECM_ORDER.BILLEDBY_BROKER_CODE — the column NAME says code,
--     the DATA is full bank names (measured 2026-08-18; ~90% populated),
--     the same value-form as DCM's BND, so BILLED_BY is uniform across
--     products. Test entities ('Citi (Test Syndicate CMG)') are excluded by
--     the existing CITIGROUP GLOBAL MARKETS stem doctrine.
--   * OFFERING_TYPE — denormalized from OPUS_ECM_TRANSACTION (existing
--     deduped T join): makes "investors in IPOs" ONE request, killing the
--     40-id ferry that corrupted a function call in QA. DCM: CAST(NULL).
--   * deal_sharing_type DEFERRED: it would need the syndicate join chain
--     added to a 5.8M-row view; "sole deals' orders" 2-hops via tranche ids.
-- Ontology/skill flips are STAGED in _review/round2-config-staged.md —
-- apply ONLY after this view deploys.
-- ===========================================================================
CREATE OR REPLACE VIEW "DGSTREAM"."VW_ORDER_DETAIL" AS
SELECT
    'ECM' AS PRODUCT,
    O.DEAL_ID AS DEAL_ID,
    T.SYNDICATE_DEAL_NAME AS DEAL_NAME,
    O.TRANCHE_ID AS TRANCHE_ID,
    TT.TRANCHE_NAME AS TRANCHE_NAME,
    O.ORDER_ID AS ORDER_ID,
    O.INVESTOR_NAME AS INVESTOR_NAME,
    O.INVESTOR_GPNUM AS INVESTOR_GP_ID,
    O.INVESTOR_REGION AS INVESTOR_REGION,
    O.INVESTOR_CATEGORY_KEY AS INVESTOR_CATEGORY_KEY,
    O.INVESTOR_CATEGORY_VALUE AS INVESTOR_CATEGORY,
    O.MEETING_TYPE_KEY AS MEETING_TYPE_KEY,
    O.MEETING_TYPE_VALUE AS MEETING_TYPE,
    O.ORDER_TYPE AS ORDER_TYPE,
    O.IOI_TYPE AS IOI_TYPE,
    NVL(OI.LIMIT_VALUE, 0) AS ORDER_AMOUNT,
    O.DEMAND_QTY AS ORDER_DEMAND_QTY,
    NVL(O.PRIVATE_ALLOC, 0) AS ORDER_ALLOCATION,
    CAST(TT.PRICING_TS AS TIMESTAMP(3)) AS PRICING_TS,
    TDC.CURRENCY_NAME AS CURRENCY,
    NVL(PCM.PARTY_NAME, NVL(OIN.ISSUER_NAME_BY_GFCID, T.ISSUER_NAME_FROM_SOURCE)) AS ISSUER_NAME,
    T.ISSUER_INDUSTRY_SECTOR AS SECTOR,
    CASE WHEN TT.TRANCHE_OFFER_SIZE IS NULL THEN 0
         WHEN REGEXP_LIKE(TO_CHAR(TT.TRANCHE_OFFER_SIZE),
                          '^\s*[+-]?[0-9]+(\.[0-9]+)?([Ee][+-]?[0-9]+)?\s*$')
         THEN TO_NUMBER(TRIM(TO_CHAR(TT.TRANCHE_OFFER_SIZE)))
         ELSE NULL END AS TRANCHE_SIZE,
    O.BILLEDBY_BROKER_CODE AS BILLED_BY,
    T.PRODUCT_OFFERING_TYPE_VALUE AS OFFERING_TYPE
FROM (
    SELECT E.*
    FROM (
        SELECT EO.*,
               ROW_NUMBER() OVER (PARTITION BY EO.ORDER_ID ORDER BY EO.ROWID) AS RN_
        FROM DGSTREAM.OB_ECM_ORDER EO
    ) E
    WHERE E.RN_ = 1
) O
INNER JOIN (
    SELECT X.*
    FROM (
        SELECT ET.ECM_TRANSACTION_ID, ET.DEAL_TRANSACTION_ID,
               ET.SYNDICATE_DEAL_NAME, ET.ISSUER_NAME_FROM_SOURCE,
               ET.ISSUER_INDUSTRY_SECTOR, ET.PRODUCT_OFFERING_TYPE_VALUE,
               ET.ISSUER_GFCID,
               ROW_NUMBER() OVER (PARTITION BY ET.ECM_TRANSACTION_ID
                                  ORDER BY ET.ROWID) AS RN_
        FROM DGSTREAM.OPUS_ECM_TRANSACTION ET
    ) X
    WHERE X.RN_ = 1
) T
    ON O.DEAL_ID = T.DEAL_TRANSACTION_ID
    AND O.IS_OWNED = 'true'
    AND O.ORDER_STATUS NOT IN ('CANCELLED', 'DELETED', 'PASS')
    AND ((O.IS_MATCHED = 'true' AND O.IS_DOMINANT = 'true') OR O.IS_MATCHED = 'false')
INNER JOIN (
    SELECT ECM_TRANSACTION_ID,
           MAX(STATUS_VALUE) AS STATUS_VALUE
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_STATUS
    WHERE STATUS_TYPE = 'Execution_Status'
      AND STATUS_VALUE NOT IN ('Confidential', 'Withdrawn', 'Terminated')
    GROUP BY ECM_TRANSACTION_ID
) S
    ON T.ECM_TRANSACTION_ID = S.ECM_TRANSACTION_ID
LEFT JOIN (
    SELECT ORDER_ID, MAX(LIMIT_VALUE) AS LIMIT_VALUE
    FROM DGSTREAM.OB_ECM_ORDER_IOI
    GROUP BY ORDER_ID
) OI
    ON O.ORDER_ID = OI.ORDER_ID
LEFT JOIN (
    SELECT W.*
    FROM (
        SELECT TTR.ECM_TRANSACTION_ID, TTR.ECM_TRANSACTION_TRANCHE_ID,
               TTR.TRANCHE_NAME, TTR.PRICING_TS, TTR.TRANCHE_CURRENCY_ID,
               TTR.TRANCHE_OFFER_SIZE,
               ROW_NUMBER() OVER (PARTITION BY TTR.ECM_TRANSACTION_ID,
                                               TTR.ECM_TRANSACTION_TRANCHE_ID
                                  ORDER BY TTR.ROWID) AS RN_
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TTR
    ) W
    WHERE W.RN_ = 1
) TT
    ON T.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
    AND TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) = O.TRANCHE_ID
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
    O.ROOT_ID AS DEAL_ID,
    ODT.DEAL_NAME AS DEAL_NAME,
    O.PARENT_ID AS TRANCHE_ID,
    ODT.NAME AS TRANCHE_NAME,
    O.ORDER_ID AS ORDER_ID,
    O.NAME AS INVESTOR_NAME,
    O.GPID AS INVESTOR_GP_ID,
    CAST(NULL AS VARCHAR2(1020)) AS INVESTOR_REGION,
    CAST(NULL AS VARCHAR2(1020)) AS INVESTOR_CATEGORY_KEY,
    CAST(NULL AS VARCHAR2(1020)) AS INVESTOR_CATEGORY,
    CAST(NULL AS VARCHAR2(1020)) AS MEETING_TYPE_KEY,
    CAST(NULL AS VARCHAR2(1020)) AS MEETING_TYPE,
    CAST(NULL AS VARCHAR2(1020)) AS ORDER_TYPE,
    CAST(NULL AS VARCHAR2(400)) AS IOI_TYPE,
    NVL(OZ.AMT, 0) AS ORDER_AMOUNT,
    NVL(OZ.AMT, 0) AS ORDER_DEMAND_QTY,
    NVL(O.FINAL_ALLOC, 0) AS ORDER_ALLOCATION,
    ODT.PRICING_TS AS PRICING_TS,
    ODT.CURRENCY AS CURRENCY,
    NVL(PCM.PARTY_NAME, ODI.NAME) AS ISSUER_NAME,
    ODT.ISSUER_SECTOR AS SECTOR,
    CASE WHEN ODT.TRANCHE_SIZE IS NULL THEN 0
         WHEN REGEXP_LIKE(TO_CHAR(ODT.TRANCHE_SIZE),
                          '^\s*[+-]?[0-9]+(\.[0-9]+)?([Ee][+-]?[0-9]+)?\s*$')
         THEN TO_NUMBER(TRIM(TO_CHAR(ODT.TRANCHE_SIZE)))
         ELSE NULL END AS TRANCHE_SIZE,
    O.BND AS BILLED_BY,
    CAST(NULL AS VARCHAR2(4000)) AS OFFERING_TYPE
FROM (
    SELECT D.*
    FROM (
        SELECT DO.ORDER_ID, DO.ROOT_ID, DO.PARENT_ID, DO.NAME, DO.GPID,
               DO.FINAL_ALLOC, DO.BND,
               ROW_NUMBER() OVER (PARTITION BY DO.ORDER_ID ORDER BY DO.ROWID) AS RN_
        FROM DGSTREAM.OB_ORDER DO
    ) D
    WHERE D.RN_ = 1
) O
INNER JOIN (
    SELECT Y.*
    FROM (
        SELECT DT.DEAL_ID, DT.TRANCHE_ID, DT.DEAL_NAME, DT.NAME,
               DT.PRICING_TS, DT.CURRENCY, DT.ISSUER_SECTOR, DT.TRANCHE_SIZE,
               ROW_NUMBER() OVER (PARTITION BY DT.DEAL_ID, DT.TRANCHE_ID
                                  ORDER BY DT.ROWID) AS RN_
        FROM DGSTREAM.OB_DEAL_TRANCHE DT
    ) Y
    WHERE Y.RN_ = 1
) ODT
    ON ODT.DEAL_ID = O.ROOT_ID
    AND ODT.TRANCHE_ID = O.PARENT_ID
LEFT JOIN (
    SELECT ORDER_ID, MAX(AMT) AS AMT
    FROM DGSTREAM.OB_ORDER_SIZE
    GROUP BY ORDER_ID
) OZ
    ON O.ORDER_ID = OZ.ORDER_ID
LEFT JOIN (
    SELECT Z.*
    FROM (
        SELECT DI.DEAL_TRANCHE_ID, DI.NAME,
               ROW_NUMBER() OVER (PARTITION BY DI.DEAL_TRANCHE_ID
                                  ORDER BY DI.ROWID) AS RN_
        FROM DGSTREAM.OB_DEAL_ISSUER DI
    ) Z
    WHERE Z.RN_ = 1
) ODI
    ON ODI.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID;

GRANT SELECT ON "DGSTREAM"."VW_ORDER_DETAIL" TO "DGLOBE_ORAAS_TABLEAU_ROLE";
GRANT SELECT ON "DGSTREAM"."VW_ORDER_DETAIL" TO "DGLOBE_ORAAS_RO_ROLE";
GRANT SELECT ON "DGSTREAM"."VW_ORDER_DETAIL" TO "DGLOBE_TABLEAU_RESTRICTED_ROLE"
LEFT JOIN (
    -- ISSUER IDENTITY MASTER for DCM too (2026-08-18): same PROD-intended
    -- source as the ECM branches (RELATED_PARTIES, Primary Client, latest
    -- version). V1's OB_DEAL_ISSUER concat join is KEPT underneath as the
    -- fallback via NVL — exactly V1 behavior when the master has no row.
    SELECT TRANSACTION_ID, PARTY_NAME, PARTY_GFCID, PARTY_TICKER
    FROM (
        SELECT TRANSACTION_ID, PARTY_NAME, PARTY_GFCID, PARTY_TICKER,
               ROW_NUMBER() OVER (PARTITION BY TRANSACTION_ID
                                  ORDER BY PUBLISHED_TS DESC) AS RN_
        FROM DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
        WHERE PARTY_ROLE = 'Primary Client'
    ) WHERE RN_ = 1
) PCM
    ON PCM.TRANSACTION_ID = O.ROOT_ID
;
GRANT SELECT ON "DGSTREAM"."VW_ORDER_DETAIL" TO "DGLOBE" WITH GRANT OPTION;
