-- ===========================================================================
-- ISSUER IDENTITY — final round: does V1's DCM join actually match?
-- 2026-08-18. State: ECM is FIXED (party master -> OB_DEAL_ISSUER GFCID ->
-- old column). DCM branches now ALSO layer the party master, with V1's
-- OB_DEAL_ISSUER concat join kept underneath as the fallback (verbatim V1
-- behavior — VIEW-SPLIT-PROPOSAL.md:158). The A2 sample showed only
-- 'I-...' ECM-format keys, but 15 rows is not a census — these two queries
-- decide whether V1's DCM join ever produced a name.
-- RESOLVED (H+I, 2026-08-18): BOTH key families exist (26,463 DCM-format
-- 100% named; 47,813 I-format) and V1's concat join hits 74,276/74,281 DCM
-- tranches — DCM issuer names were NEVER broken; the QA "—" symptoms were
-- ECM-only. Everything as written stands. ONE integrity question remains:
-- ===========================================================================

-- J — do I-format deals leak into our views as 'DCM' rows? OB_DEAL_TRANCHE
--     holds ~47.8k I-format pairs and the DCM branches read it with NO
--     product filter. >0 here = another platform's deals mislabeled DCM.
SELECT COUNT(*) AS DCM_ROWS_WITH_I_FORMAT_DEAL_ID,
       COUNT(DISTINCT DEAL_ID) AS DISTINCT_I_DEALS
FROM   DGSTREAM.VW_TRANCHE_SUMMARY
WHERE  PRODUCT = 'DCM' AND DEAL_ID LIKE 'I-%';

-- (original H below for the record)
-- H — key-format census of OB_DEAL_ISSUER: are there any non-'I-' keys
--     (i.e. DCM 'dealid-trancheid' format) at all, and do they carry names?
SELECT CASE WHEN DEAL_TRANCHE_ID LIKE 'I-%' THEN 'I-format (ECM)'
            ELSE 'other format' END AS KEY_FORMAT,
       COUNT(*) AS ROWS_, COUNT(NAME) AS WITH_NAME
FROM   DGSTREAM.OB_DEAL_ISSUER
GROUP  BY CASE WHEN DEAL_TRANCHE_ID LIKE 'I-%' THEN 'I-format (ECM)'
               ELSE 'other format' END;

-- I — the join-hit rate itself: how many DCM tranches find an issuer row
--     via V1's concat key?
SELECT COUNT(*) AS DCM_TRANCHES,
       SUM(CASE WHEN DI.DEAL_TRANCHE_ID IS NOT NULL THEN 1 ELSE 0 END) AS WITH_ISSUER_ROW
FROM (
    SELECT DISTINCT DEAL_ID, TRANCHE_ID FROM DGSTREAM.OB_DEAL_TRANCHE
) DT
LEFT JOIN DGSTREAM.OB_DEAL_ISSUER DI
  ON DI.DEAL_TRANCHE_ID = DT.DEAL_ID || '-' || DT.TRANCHE_ID;
