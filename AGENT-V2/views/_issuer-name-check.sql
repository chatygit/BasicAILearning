-- ===========================================================================
-- ISSUER IDENTITY — round 3: confirm the RELATED_PARTIES bridge.
-- 2026-08-18. State so far:
--   * ECM ISSUER NAME IS FIXED in the view diffs: OB_DEAL_ISSUER GFCID join
--     (0 -> ~6,892 named QA deals; 96% of GFCID-carrying deals). Shipping.
--   * Tech end-state (Dumitru + Samir): RELATED_PARTIES is the issuer-
--     identity MASTER — PARTY_NAME, PARTY_GFCID, PARTY_TICKER should feed
--     NAME, GFCID, TICKER. But the direct join failed (TRANSACTION_ID
--     matched 2/21,195 ECM deals) — hypothesis: the real path is the BRIDGE
--     RELATED_PARTIES.BASE_ID -> OPUS_BASE_TRANSACTION, whose TRANSACTION_ID
--     is our deal id family (the deal view already joins it for DEAL_REGION).
--   * QA caveat: PARTY_NAME is null on ~98% of Primary Client rows in QA —
--     the master may only shine in PROD; NVL fallbacks stay permanent.
-- Run F then G; two screenshots finish the design.
-- ===========================================================================

-- F — the bridge table's keys: which column does RELATED_PARTIES.BASE_ID
--     point at, and confirm TRANSACTION_ID is the deal id family.
SELECT COLUMN_NAME, DATA_TYPE, NULLABLE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'OPUS_BASE_TRANSACTION'
ORDER  BY COLUMN_ID;

-- G — the NAMED party rows: id families on both keys, and whether
--     PARTY_GFCID / PARTY_TICKER are filled where names are.
SELECT TRANSACTION_ID, BASE_ID, PARTY_ROLE, PARTY_NAME, PARTY_GFCID, PARTY_TICKER
FROM   DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
WHERE  PARTY_NAME IS NOT NULL
FETCH FIRST 15 ROWS ONLY;
