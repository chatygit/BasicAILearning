-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on the
-- environment where the views are deployed and screenshot into ~/Desktop/ADK
-- WITH the status bar. A section is deleted once its results are recorded.
-- (N7 of 2026-09-22 is recorded; N7-2a errored on a column of mine that does
-- not exist — corrected below as N8-1.)
-- ===========================================================================


-- ===========================================================================
-- N8. 2026-09-22 — IPREO, ROUND 5 (four censuses, no view needed except N8-4).
-- ===========================================================================

-- N8-1. Non-share indication units: is the mirror's IOI_QTY a share-equivalent
--       for CURRENCY (money / offer price), PERCENT (% of deal) and FACE (bond
--       face) orders? Five orders per unit with the raw quantity, raw amount,
--       offer price, par and deal size. The views already treat CURRENCY as a
--       share-equivalent; this decides PERCENT and FACE.
SELECT * FROM (
  SELECT O.IOI_UNIT, O.INVESTOR_NAME, M.IOI_QTY AS MIRROR_QTY_, R.IOI_QTY AS RAW_QTY_, R.IOI_AMT AS RAW_AMT_,
         P.OFFER_PX, P.PAR_VALUE, T.DEAL_SIZE, T.PRODUCT_EQUITY_TYPE_VALUE AS EQUITY_TYPE_,
         ROW_NUMBER() OVER (PARTITION BY O.IOI_UNIT ORDER BY O.ORDER_ID) AS RN_
  FROM   DGSTREAM.IPREO_OB_ECM_ORDER O
  JOIN   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T ON T.DEAL_TRANSACTION_ID = O.DEAL_ID
  LEFT JOIN DGSTREAM.IPREO_OB_ECM_ORDER_IOI M ON M.ORDER_ID = O.ORDER_ID
  LEFT JOIN DGSTREAM.IPREO_ORDERIOI R ON R.ORD_ID = TO_NUMBER(O.ORDER_ID DEFAULT NULL ON CONVERSION ERROR)
  LEFT JOIN (SELECT ISS_ID, MAX(OFFER_PX) AS OFFER_PX, MAX(PAR_VALUE) AS PAR_VALUE
             FROM DGSTREAM.IPREO_PRODUCT GROUP BY ISS_ID) P
         ON P.ISS_ID = TO_NUMBER(O.DEAL_ID DEFAULT NULL ON CONVERSION ERROR)
  WHERE  O.IOI_UNIT IN ('CURRENCY', 'PERCENT', 'FACE') AND M.IOI_QTY IS NOT NULL AND R.IOI_AMT IS NOT NULL
) WHERE RN_ <= 5 ORDER BY IOI_UNIT, RN_;

-- N8-2. Tranche size vs deal size: Visa's tranche is 446,600,000 = 406,000,000
--       deal + 40,600,000 over-allotment, i.e. the active size INCLUDES the
--       shoe. Is that the rule? (Decides whether TRANCHE_SIZE subtracts it.)
SELECT CASE WHEN RT.ACTIVE_TRANCHE_SIZE_QTY = T.DEAL_SIZE THEN 'ACTIVE = DEAL'
            WHEN RT.ACTIVE_TRANCHE_SIZE_QTY - NVL(RT.OVERALLOTMENT_QTY, 0) = T.DEAL_SIZE THEN 'ACTIVE - SHOE = DEAL'
            WHEN RT.OVERALLOTMENT_QTY IS NULL THEN 'NO SHOE, OTHER'
            ELSE 'OTHER' END AS RELATION_,
       COUNT(*) AS TRANCHES_
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T
JOIN   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE TT ON TT.ECM_TRANSACTION_ID = T.ECM_TRANSACTION_ID
JOIN   DGSTREAM.IPREO_TRANCHE RT ON RT.TRN_ID = TT.ECM_TRANSACTION_TRANCHE_ID
WHERE  T.DEAL_SIZE IS NOT NULL
GROUP  BY CASE WHEN RT.ACTIVE_TRANCHE_SIZE_QTY = T.DEAL_SIZE THEN 'ACTIVE = DEAL'
            WHEN RT.ACTIVE_TRANCHE_SIZE_QTY - NVL(RT.OVERALLOTMENT_QTY, 0) = T.DEAL_SIZE THEN 'ACTIVE - SHOE = DEAL'
            WHEN RT.OVERALLOTMENT_QTY IS NULL THEN 'NO SHOE, OTHER'
            ELSE 'OTHER' END
ORDER  BY 2 DESC;

-- N8-3. Syndicate members on Ipreo are BROKER CODES (ABNROTH | BARCAP |
--       CITIUSA …), so the Citi SOLO/SHARED regex ('^CITI(GROUP|BANK)?…')
--       misses them. Every code starting with CITI, and the top 25 codes with
--       their roles (the role vocabulary decides the B&D flag too).
SELECT SYNDICATE_MEMBER_NAME, BROKER_CODE, COUNT(*) AS N
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
WHERE  UPPER(SYNDICATE_MEMBER_NAME) LIKE 'CITI%' OR UPPER(BROKER_CODE) LIKE 'CITI%'
GROUP  BY SYNDICATE_MEMBER_NAME, BROKER_CODE ORDER BY 3 DESC;
SELECT SYNDICATE_MEMBER_NAME, COUNT(*) AS N FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
GROUP  BY SYNDICATE_MEMBER_NAME ORDER BY 2 DESC FETCH FIRST 25 ROWS ONLY;
SELECT SYNDICATE_ROLE, COUNT(*) AS N FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
GROUP  BY SYNDICATE_ROLE ORDER BY 2 DESC;

-- N8-4. Allocation sanity across the Ipreo book (the deal view, ~60 s): Visa's
--       allocations sum to 2.5x its size while Qualtrics (1.11x) and Kraft
--       (0.72x) look right. How many deals are like Visa? (For the data owner.)
SELECT COUNT(*) AS DEALS_WITH_ALLOC_,
       SUM(CASE WHEN TOTAL_ALLOCATION > 1.2 * DEAL_SIZE THEN 1 ELSE 0 END) AS OVER_120PCT_,
       SUM(CASE WHEN TOTAL_ALLOCATION BETWEEN 0.5 * DEAL_SIZE AND 1.2 * DEAL_SIZE THEN 1 ELSE 0 END) AS PLAUSIBLE_,
       SUM(CASE WHEN TOTAL_ALLOCATION < 0.5 * DEAL_SIZE THEN 1 ELSE 0 END) AS UNDER_50PCT_
FROM   DGSTREAM.VW_DEAL_SUMMARY
WHERE  PRODUCT = 'ECM' AND REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') AND DEAL_SIZE > 0 AND TOTAL_ALLOCATION > 0;
