-- ===========================================================================
-- REGION + SETTLEMENT HUNT — the remaining three fields from data-dictionary
-- ticket #100 (ISSUER_NAME is fixed in the deploying batch). 2026-08-18.
-- Candidate sources come from the table inventories in
-- _reference/base-table-columns.md — never re-desc. Measure population per
-- candidate; winners join the NEXT view batch with NVL layering, exactly the
-- issuer-name pattern.
-- ===========================================================================

-- Q1 — the SYMPTOM, measured: region population in the deployed views.
SELECT 'deal' AS V, PRODUCT, COUNT(*) AS ROWS_,
       COUNT(DEAL_REGION) AS WITH_REGION,
       ROUND(100 * COUNT(DEAL_REGION) / COUNT(*), 1) AS PCT
FROM DGSTREAM.VW_DEAL_SUMMARY GROUP BY PRODUCT
UNION ALL
SELECT 'tranche', PRODUCT, COUNT(*), COUNT(TRANCHE_REGION),
       ROUND(100 * COUNT(TRANCHE_REGION) / COUNT(*), 1)
FROM DGSTREAM.VW_TRANCHE_SUMMARY GROUP BY PRODUCT;

-- Q2 — ECM deal-region candidates (OPUS_BASE_TRANSACTION is versioned; raw
--     row counts are indicative, latest-version refinement comes after a
--     winner emerges).
SELECT COUNT(*) AS ROWS_,
       COUNT(DEAL_REGION)          AS DEAL_REGION_,
       COUNT(ASSIGNED_DEAL_REGION) AS ASSIGNED_,
       COUNT(NULLIF(TRIM(DEAL_REGION), 'Not Specified')) AS REGION_REAL
FROM   DGSTREAM.OPUS_BASE_TRANSACTION;

SELECT COUNT(*) AS ECM_TXNS, COUNT(EXEC_DEAL_REGION) AS EXEC_REGION_
FROM   DGSTREAM.OPUS_ECM_TRANSACTION;

-- Q3 — DCM region + settlement candidates on OB_DEAL_TRANCHE, one pass.
SELECT COUNT(*) AS ROWS_,
       COUNT(REGION)            AS REGION_,
       COUNT(TRANCHE_REGION)    AS TRANCHE_REGION_,
       COUNT(TARGET_MARKET)     AS TARGET_MARKET_,
       COUNT(SETTLEMENT_DATE)   AS SETTLEMENT_DATE_,
       COUNT(ISSUE_DATE)        AS ISSUE_DATE_,
       COUNT(ANNOUNCEMENT_DATE) AS ANNOUNCEMENT_DATE_,
       COUNT(TRADE_DATE)        AS TRADE_DATE_
FROM   DGSTREAM.OB_DEAL_TRANCHE;

-- Q4 — ECM settlement/announce candidates on OPUS_ECM_TRANSACTION, one pass
--     (SETTLEMENT_TS measured dead before; the siblings never were).
SELECT COUNT(*) AS ROWS_,
       COUNT(SETTLEMENT_TS) AS SETTLEMENT_TS_,
       COUNT(ANNOUNCE_TS)   AS ANNOUNCE_TS_,
       COUNT(LAUNCH_TS)     AS LAUNCH_TS_,
       COUNT(CLOSING_TS)    AS CLOSING_TS_
FROM   DGSTREAM.OPUS_ECM_TRANSACTION;

-- Q5 — value census for whichever region candidate Q2/Q3 shows populated
--     (swap the column in): are these real regions (NAM/EMEA/APAC) or junk?
SELECT REGION AS VALUE_, COUNT(*) AS ROWS_
FROM   DGSTREAM.OB_DEAL_TRANCHE
WHERE  REGION IS NOT NULL
GROUP  BY REGION
ORDER  BY ROWS_ DESC
FETCH FIRST 20 ROWS ONLY;
