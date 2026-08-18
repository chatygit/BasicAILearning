-- ===========================================================================
-- ISSUER NAME HUNT — round 2. Query A found the lead: OB_DEAL_ISSUER carries
-- GFCID + NAME, and Samir's "OB_DEAL_ISSUER.NAME is for ECM" now reads as
-- the ANSWER, not a warning — our views use it only in DCM branches (wrong
-- side) and never for ECM (right side). Established: current ECM source is
-- 100% dead; ECM deals DO carry ISSUER GFCID. Four queries confirm the fix.
-- ===========================================================================

-- A1 — OB_DEAL_ISSUER full shape (we only know DEAL_TRANCHE_ID, NAME, GFCID).
SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'OB_DEAL_ISSUER'
ORDER  BY COLUMN_ID;

-- A2 — population + eyeball: are NAME and GFCID filled, and what do the
--     keys look like?
SELECT COUNT(*) AS ROWS_, COUNT(NAME) AS WITH_NAME, COUNT(GFCID) AS WITH_GFCID
FROM   DGSTREAM.OB_DEAL_ISSUER;

SELECT DEAL_TRANCHE_ID, GFCID, NAME
FROM   DGSTREAM.OB_DEAL_ISSUER
WHERE  NAME IS NOT NULL
FETCH FIRST 15 ROWS ONLY;

-- A3 (THE DECIDER) — coverage: how many ECM deals get a name via the GFCID
--     join? (Also shows how many ECM deals carry a GFCID at all.)
SELECT COUNT(*)        AS ECM_DEALS,
       COUNT(D.GFCID)  AS DEALS_WITH_GFCID,
       SUM(CASE WHEN OI.GFCID IS NOT NULL THEN 1 ELSE 0 END) AS DEALS_GETTING_A_NAME
FROM   DGSTREAM.VW_DEAL_SUMMARY D
LEFT JOIN (
    SELECT DISTINCT GFCID
    FROM   DGSTREAM.OB_DEAL_ISSUER
    WHERE  NAME IS NOT NULL AND GFCID IS NOT NULL
) OI ON OI.GFCID = D.GFCID
WHERE  D.PRODUCT = 'ECM';

-- B — still worth one look: OPUS_ECM_TRANSACTION's full column list — a
--     living sibling of the dead name column would be even simpler.
SELECT COLUMN_NAME, DATA_TYPE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'OPUS_ECM_TRANSACTION'
ORDER  BY COLUMN_ID;
