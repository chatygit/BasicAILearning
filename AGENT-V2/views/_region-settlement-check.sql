-- ===========================================================================
-- REGION + SETTLEMENT (data-dictionary ticket #100) — MEASURED 2026-08-18.
-- Q1-Q5 verdicts:
--  * ECM deal region: OPUS_BASE_TRANSACTION.DEAL_REGION has 95,592 REAL
--    values (zero 'Not Specified' — the old ~98% claim is FALSE in this QA
--    copy). The MAX-over-versions OBT join already exists in the views and
--    entered in adk v19/v20 — i.e. it is IN THE BATCH DEPLOYING NOW. Q1's
--    6.3% measured the OLD deployed view. R1 below predicts the post-deploy
--    number. ASSIGNED_DEAL_REGION duplicates DEAL_REGION (identical counts);
--    EXEC_DEAL_REGION is dead (416/29,514).
--  * DCM deal region: was a NULL placeholder. FIXED (batch 3) — MAX(REGION)
--    rolled up from OB_DEAL_TRANCHE (13,978/74,281 rows; census is clean:
--    NAM 11,971 / EMEA 1,561 / APAC 446 — no junk values).
--  * ECM tranche region: TT.REGION is dead (3/36,352). FIXED (batch 3) —
--    NVL fallback to the deal's region.
--  * DCM tranche region: view already reads all the source has (13,947 vs
--    13,978). TARGET_MARKET (7,771) is NOT region vocabulary — not blended.
--    Remaining gap is upstream: data-team ticket.
--  * SETTLEMENT_TS: ECM source is NOT dead — 7,763/29,514 (26.3%), already
--    wired in the view. DCM was a NULL placeholder. FIXED (batch 3) —
--    MAX(SETTLEMENT_DATE) from OB_DEAL_TRANCHE (50,198/74,281 = 67.6%,
--    stored TIMESTAMP(3), cast to TIMESTAMP(6) for the UNION pairing).
--  * ANNOUNCE_TS / LAUNCH_TS / CLOSING_TS: ALL ZERO in QA — the "announce
--    date riches" are deprioritized until PROD shows otherwise.
-- Batch-3 edits live in vw_deal_summary.sql (DCM branch) and
-- vw_tranche_summary.sql (ECM branch). Hand over AFTER batch 2 verifies.
-- ===========================================================================

-- R1/R2/R3 RESULTS (2026-08-18) — ALL ANSWERED, ticket #100 CLOSED our side:
--  * R1: 1,457 of 29,384 ECM deal transactions (5%) find a region. The
--    95,592 region-rich base rows belong to OTHER business lines — batch 2's
--    pre-aggregated join only lifts ECM from 1,340 to ~1,457 (batch 1
--    already had a raw join). ECM deal region is a REAL DATA GAP at the
--    source -> data-team ticket is the close; ontology now teaches partial
--    coverage instead of promising the field.
--  * R2: vocabulary is NAM 20,366 / EMEA 19,249 / APAC 55,141 + JAPAN 768 +
--    LATAM 68 — same family as DCM, no doctrine break; JAPAN/LATAM added to
--    the ontology as rare-but-real values.
--  * R3: deal-grain DCM coverage — 8,260/46,931 deals with region (17.6%),
--    30,749 with settlement (65.5%). These are deploy-check rows 1f/1g.
-- CONFIG FLIP APPLIED SAME DAY (user: push views, don't wait): deal object
-- gains settlement_ts (dimension+filter, range ops); settlement_date
-- unsupported-intent DELETED; deal_region de-scoped from ECM-only to both
-- products; announced_date refusal re-grounded on the all-zero
-- ANNOUNCE/LAUNCH/CLOSING_TS measure; SKILL 3b refusal row flipped to
-- answer-it; sparse-coverage disclosure doctrine added everywhere. Gate
-- [round3] pins guard all of it.

-- R1 — the ECM overlap: of the deals actually in the view, how many find a
--      region via the OBT join? This is the number _deploy-check should
--      expect for ECM DEAL_REGION after the CURRENT deploy lands.
SELECT COUNT(*) AS ECM_DEALS,
       COUNT(OBT.DEAL_REGION) AS WITH_REGION,
       ROUND(100 * COUNT(OBT.DEAL_REGION) / COUNT(*), 1) AS PCT
FROM (SELECT DISTINCT DEAL_TRANSACTION_ID
      FROM DGSTREAM.OPUS_ECM_TRANSACTION
      WHERE DEAL_TRANSACTION_ID IS NOT NULL) E
LEFT JOIN (SELECT TRANSACTION_ID, MAX(DEAL_REGION) AS DEAL_REGION
           FROM DGSTREAM.OPUS_BASE_TRANSACTION
           GROUP BY TRANSACTION_ID) OBT
  ON OBT.TRANSACTION_ID = E.DEAL_TRANSACTION_ID;

-- R2 — ECM region VOCABULARY: the doctrine promises NAM/EMEA/APAC. If ECM
--      stores 'North America' etc., cross-product region filters miss one
--      side and the ontology prose must say so.
SELECT DEAL_REGION AS VALUE_, COUNT(*) AS ROWS_
FROM   DGSTREAM.OPUS_BASE_TRANSACTION
WHERE  DEAL_REGION IS NOT NULL
GROUP  BY DEAL_REGION
ORDER  BY ROWS_ DESC
FETCH FIRST 20 ROWS ONLY;

-- R3 — DCM deal-grain coverage of the two batch-3 rollups: the numbers
--      _deploy-check should expect after BATCH 3 lands.
SELECT COUNT(DISTINCT DEAL_ID) AS DCM_DEALS,
       COUNT(DISTINCT CASE WHEN REGION IS NOT NULL
                           THEN DEAL_ID END) AS DEALS_WITH_REGION,
       COUNT(DISTINCT CASE WHEN SETTLEMENT_DATE IS NOT NULL
                           THEN DEAL_ID END) AS DEALS_WITH_SETTLEMENT
FROM   DGSTREAM.OB_DEAL_TRANCHE;
