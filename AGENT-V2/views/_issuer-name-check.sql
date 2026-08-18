-- ===========================================================================
-- ISSUER IDENTITY — final round: does V1's DCM join actually match?
-- 2026-08-18. State: ECM is FIXED (party master -> OB_DEAL_ISSUER GFCID ->
-- old column). DCM branches now ALSO layer the party master, with V1's
-- OB_DEAL_ISSUER concat join kept underneath as the fallback (verbatim V1
-- behavior — VIEW-SPLIT-PROPOSAL.md:158). The A2 sample showed only
-- 'I-...' ECM-format keys, but 15 rows is not a census — these two queries
-- decide whether V1's DCM join ever produced a name.
-- ===========================================================================

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
