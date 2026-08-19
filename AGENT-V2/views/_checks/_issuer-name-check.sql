-- =========================================================================
-- ARCHIVE — issuer identity investigation, CLOSED 2026-08-18. Verdicts:
--  * ECM issuer names: were 100% dead; FIXED three-layer in all views
--    (party master -> OB_DEAL_ISSUER GFCID -> old column). ~6,892 QA
--    deals named on deploy; PROD higher.
--  * DCM issuer names: NEVER broken — V1 concat join hits 74,276/74,281
--    tranches; party master layered above for PROD.
--  * I-format 'DCM' rows (query L): LEGITIMATE DCM — bond tranches
--    ('5 YR FXD USD', '15Y45F', '10 yr', USD notionals) from the IPREO
--    source system (IPREO_DEAL_ID/IPREO_TRANCHE_ID exist on
--    OB_DEAL_TRANCHE). Two source systems, one product. No
--    contamination; no product filter needed.
--  * All table shapes recorded in views/_reference/base-table-columns.md
--    — never re-desc these.
-- Nothing left to run. Kept for the audit trail.
-- =========================================================================

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

-- J RESULT (2026-08-18): 47,758 'DCM' tranche rows / 31,558 distinct deals
-- carry I-format ids — two-thirds of the DCM population. NOT caused by any
-- current edit (pre-existing in the deployed views; DCM branches read
-- OB_DEAL_TRANCHE with no source discriminator). Classify before judging:
-- I-format may be Ipreo-SOURCED DCM (legitimate, second id family) or a
-- foreign population (contamination inflating every DCM total).

-- K — what discriminator does OB_DEAL_TRANCHE carry? (source system /
--     product / type columns)
SELECT COLUMN_NAME, DATA_TYPE, NULLABLE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'OB_DEAL_TRANCHE'
ORDER  BY COLUMN_ID;

-- L — eyeball the I-format 'DCM' rows: do they read as bonds (money sizes,
--     coupons-ish names, real currencies) or as something else?
SELECT DEAL_ID, DEAL_NAME, TRANCHE_NAME, CURRENCY, TRANCHE_SIZE, DEAL_STATUS
FROM   DGSTREAM.VW_TRANCHE_SUMMARY
WHERE  PRODUCT = 'DCM' AND DEAL_ID LIKE 'I-%'
FETCH FIRST 15 ROWS ONLY;
