-- ===========================================================================
-- DCM TRANSACTION ID (DCM round D1, 2026-08-24). ECM's deal id IS the
-- transaction id; DCM's is not — but OB_DEAL_TRANCHE carries
-- ORIGINATION_TRANSACTION_ID (col 212, VARCHAR2), never read by any view
-- and absent from V1. If it keys into the OPUS transaction family, it
-- (a) gives DCM the missing transaction id, (b) FIXES the DCM party-master
-- join (currently guessed as TRANSACTION_ID = DEAL_ID — never proven), and
-- (c) may unlock DCM deal regions via OPUS_BASE_TRANSACTION.
-- Run in PROD. Winners are release-train view changes.
--
-- RESULTS (PROD, 2026-08-27): THE KEY IS REAL.
--  * T1: DEALS_WITH_MULTIPLE_OTIDS = 0 — one txn per deal, rollup-safe.
--  * T2: otid values ARE the OPUS transaction family (75xxxxxx); every
--    sample row is a 2026-vintage I-format (Ipreo) deal -> the column is
--    FORWARD-POPULATED: sparse history (~890 ids vs ~47k deals), likely
--    complete going forward.
--  * T3: 890 distinct otids; 785 (88%) exist in BOTH OPUS_BASE_TRANSACTION
--    and RELATED_PARTIES.
--  * T4: DCM_DEALS_JOINED=944, WITH_PRIMARY_CLIENT=776 (82%) — resolved
--    by consistency (WITH_* <= JOINED; deals can share an otid, so 944
--    deals over 890 otids is sound). WITH_BASE_REGION was cut off in the
--    shot — treat as unmeasured; deploy-check 1n + the region INFO rows
--    will show the real number post-deploy. DO NOT re-ask.
--  * CONSEQUENCE: the DCM party-master join keyed TRANSACTION_ID=DEAL_ID
--    is PROVEN WRONG (id families don't even share a format — it has
--    never matched a row). Release-train: roll otid to deal grain, expose
--    as the DCM transaction id, re-key the DCM PCM joins in all three
--    views (existing OB_DEAL_ISSUER fallbacks stay underneath).
-- ===========================================================================

-- T1 — population + per-deal consistency (a deal must map to ONE txn).
SELECT COUNT(*) AS ROWS_,
       COUNT(ORIGINATION_TRANSACTION_ID) AS WITH_OTID,
       COUNT(DISTINCT DEAL_ID) AS DEALS_,
       COUNT(DISTINCT CASE WHEN ORIGINATION_TRANSACTION_ID IS NOT NULL
                           THEN DEAL_ID END) AS DEALS_WITH_OTID,
       COUNT(DISTINCT ORIGINATION_TRANSACTION_ID) AS DISTINCT_OTIDS
FROM   DGSTREAM.OB_DEAL_TRANCHE;

SELECT COUNT(*) AS DEALS_WITH_MULTIPLE_OTIDS
FROM (
    SELECT DEAL_ID
    FROM   DGSTREAM.OB_DEAL_TRANCHE
    WHERE  ORIGINATION_TRANSACTION_ID IS NOT NULL
    GROUP  BY DEAL_ID
    HAVING COUNT(DISTINCT ORIGINATION_TRANSACTION_ID) > 1
);

-- T2 — eyeball the format: does it look like the OPUS TRANSACTION_ID family?
SELECT DEAL_ID, ORIGINATION_TRANSACTION_ID
FROM   DGSTREAM.OB_DEAL_TRANCHE
WHERE  ORIGINATION_TRANSACTION_ID IS NOT NULL
FETCH FIRST 15 ROWS ONLY;

-- T3 — the join tests: do origination ids EXIST in the transaction world?
SELECT COUNT(DISTINCT ODT.ORIGINATION_TRANSACTION_ID) AS OTIDS_,
       COUNT(DISTINCT CASE WHEN OBT.TRANSACTION_ID IS NOT NULL
                           THEN ODT.ORIGINATION_TRANSACTION_ID END)
         AS IN_BASE_TRANSACTION,
       COUNT(DISTINCT CASE WHEN RP.TRANSACTION_ID IS NOT NULL
                           THEN ODT.ORIGINATION_TRANSACTION_ID END)
         AS IN_RELATED_PARTIES
FROM   DGSTREAM.OB_DEAL_TRANCHE ODT
LEFT JOIN (SELECT DISTINCT TRANSACTION_ID
           FROM DGSTREAM.OPUS_BASE_TRANSACTION) OBT
  ON OBT.TRANSACTION_ID = ODT.ORIGINATION_TRANSACTION_ID
LEFT JOIN (SELECT DISTINCT TRANSACTION_ID
           FROM DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES) RP
  ON RP.TRANSACTION_ID = ODT.ORIGINATION_TRANSACTION_ID
WHERE  ODT.ORIGINATION_TRANSACTION_ID IS NOT NULL;

-- T4 — the payoff: of DCM deals whose origination id joins, how many find
--      a Primary Client (issuer master) and a real DEAL_REGION?
SELECT COUNT(DISTINCT ODT.DEAL_ID) AS DCM_DEALS_JOINED,
       COUNT(DISTINCT CASE WHEN RP.PARTY_NAME IS NOT NULL
                           THEN ODT.DEAL_ID END) AS WITH_PRIMARY_CLIENT,
       COUNT(DISTINCT CASE WHEN OBT.DEAL_REGION IS NOT NULL
                           THEN ODT.DEAL_ID END) AS WITH_BASE_REGION
FROM   DGSTREAM.OB_DEAL_TRANCHE ODT
LEFT JOIN (SELECT TRANSACTION_ID, MAX(DEAL_REGION) AS DEAL_REGION
           FROM DGSTREAM.OPUS_BASE_TRANSACTION
           GROUP BY TRANSACTION_ID) OBT
  ON OBT.TRANSACTION_ID = ODT.ORIGINATION_TRANSACTION_ID
LEFT JOIN (SELECT DISTINCT TRANSACTION_ID, PARTY_NAME
           FROM DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
           WHERE PARTY_ROLE = 'Primary Client') RP
  ON RP.TRANSACTION_ID = ODT.ORIGINATION_TRANSACTION_ID
WHERE  ODT.ORIGINATION_TRANSACTION_ID IS NOT NULL;
