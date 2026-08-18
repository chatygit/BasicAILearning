-- ===========================================================================
-- ISSUER NAME HUNT — the five queries that find the living source.
-- 2026-08-18. Established so far (previous rounds, results recorded in
-- _review/audit-backlog-2026-08-11.md):
--   * Current ECM source (OPUS_ECM_TRANSACTION.ISSUER_NAME_FROM_SOURCE) is
--     100% DEAD in QA: 0 of 21,195 ECM deals carry a name.
--   * Dumitru's table as-given does not join: RELATED_PARTIES.TRANSACTION_ID
--     matches 2/21,195 ECM and 0/46,931 DCM deal ids, and PARTY_NAME is NULL
--     on ~98% of 'Primary Client' rows.
--   * ECM deals DO carry a populated ISSUER GFCID — so ANY live GFCID->name
--     mapping fixes issuer names without solving the id mystery.
-- Run A-E, screenshot each; whichever door opens becomes the view fix.
-- ===========================================================================

-- A — every DGSTREAM table that carries a GFCID column (looking for one that
--     pairs it with a name).
SELECT TABLE_NAME, COLUMN_NAME
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND COLUMN_NAME LIKE '%GFCID%'
ORDER  BY TABLE_NAME;

-- B — full column list of OPUS_ECM_TRANSACTION: the dead name column may
--     have a living sibling we have never inventoried.
SELECT COLUMN_NAME, DATA_TYPE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'OPUS_ECM_TRANSACTION'
ORDER  BY COLUMN_ID;

-- C — candidate bridge / party / issuer tables (the missing link for
--     Dumitru's RELATED_PARTIES guidance).
SELECT TABLE_NAME
FROM   ALL_TABLES
WHERE  OWNER = 'DGSTREAM'
AND   (TABLE_NAME LIKE '%BASE_TRANSACTION%' OR TABLE_NAME LIKE '%PARTY%'
    OR TABLE_NAME LIKE '%CLIENT%' OR TABLE_NAME LIKE '%ISSUER%');

-- D — name/GFCID population per role in RELATED_PARTIES: names may live
--     under 'Client' (185k rows), not 'Primary Client'.
SELECT PARTY_ROLE, COUNT(*) AS ROWS_,
       COUNT(PARTY_NAME)  AS WITH_NAME,
       COUNT(PARTY_GFCID) AS WITH_GFCID
FROM   DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
GROUP  BY PARTY_ROLE
ORDER  BY WITH_NAME DESC;

-- E — what the NAMED rows look like: id format, and whether PARTY_GFCID
--     rides along (a GFCID join skips the id mystery entirely).
SELECT TRANSACTION_ID, PARTY_ROLE, PARTY_NAME, PARTY_GFCID
FROM   DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
WHERE  PARTY_NAME IS NOT NULL
FETCH FIRST 15 ROWS ONLY;
