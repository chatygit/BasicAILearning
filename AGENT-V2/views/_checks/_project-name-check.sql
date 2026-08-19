-- ===========================================================================
-- PROJECT NAME (Mike's observations doc, 2a — "Deal Launcher shows
-- ProjectName; is it consumed?"). 2026-08-18.
-- The column EXISTS at source: OPUS_BASE_TRANSACTION.PROJECT_NAME
-- (VARCHAR2, col 5 — see _reference/base-table-columns.md). ECM-side only;
-- no OB-world equivalent found, so DCM would be a NULL placeholder.
--
-- P1/P2 RESULTS (2026-08-18): population LOOKS great (137,961/143,020
-- rows; 60,651/61,231 transactions = 99%) — but the value census is
-- QA LOAD-TEST JUNK: top values are 'PerfAuto_...', 'DO NOT PUBLISH TO
-- DOWNSTREAM PerfAuto...', 'test'/'test1', bare 'Project'. The QA base
-- table is polluted with perf-test transactions (which ALSO explains the
-- deal-region mystery: 61k base transactions vs 29k real ECM deal
-- transactions, and the region-rich rows that don't overlap our deals).
-- VERDICT (P3a/P3b, 2026-08-18) — CLOSED, NOT WIRED THIS BATCH:
--  * P3a: 1,737 of 29,384 real ECM deal transactions carry a project name
--    (5.9%) — same shape as the region story; the 137,961 populated base
--    rows are overwhelmingly perf-junk outside the deal spine.
--  * P3b: even the real-spine names are QA-synthetic (PerfAuto*,
--    UAT_EMEA_VAT_Client Invoicing _CGML). One telling exception —
--    'Copy of Project Soda' (18 deals) — confirms the PROD shape is real
--    confidential code names.
--  * DROPPED by user decision 2026-08-18: ProjectName is IGNORED — not
--    wired, not raised with POs, not in the Mike reply as an open item.
--    Measurements kept for the record only; do not re-open.
-- ===========================================================================

-- P3a — the decisive overlap: of OUR deal transactions, how many carry a
--       project name? (Same shape as region query R1.)
SELECT COUNT(*) AS ECM_DEALS,
       COUNT(OBT.PROJECT_NAME) AS WITH_PROJECT,
       ROUND(100 * COUNT(OBT.PROJECT_NAME) / COUNT(*), 1) AS PCT
FROM (SELECT DISTINCT DEAL_TRANSACTION_ID
      FROM DGSTREAM.OPUS_ECM_TRANSACTION
      WHERE DEAL_TRANSACTION_ID IS NOT NULL) E
LEFT JOIN (SELECT TRANSACTION_ID, MAX(PROJECT_NAME) AS PROJECT_NAME
           FROM DGSTREAM.OPUS_BASE_TRANSACTION
           WHERE PROJECT_NAME IS NOT NULL
           GROUP BY TRANSACTION_ID) OBT
  ON OBT.TRANSACTION_ID = E.DEAL_TRANSACTION_ID;

-- P3b — what do REAL deals' project names look like (junk or code names)?
SELECT OBT.PROJECT_NAME, COUNT(*) AS DEALS_
FROM (SELECT DISTINCT DEAL_TRANSACTION_ID
      FROM DGSTREAM.OPUS_ECM_TRANSACTION
      WHERE DEAL_TRANSACTION_ID IS NOT NULL) E
JOIN (SELECT TRANSACTION_ID, MAX(PROJECT_NAME) AS PROJECT_NAME
      FROM DGSTREAM.OPUS_BASE_TRANSACTION
      WHERE PROJECT_NAME IS NOT NULL
      GROUP BY TRANSACTION_ID) OBT
  ON OBT.TRANSACTION_ID = E.DEAL_TRANSACTION_ID
GROUP  BY OBT.PROJECT_NAME
ORDER  BY DEALS_ DESC
FETCH FIRST 15 ROWS ONLY;

-- (P1/P2 below — ANSWERED, kept for the record)
-- P1 — population, raw and per-transaction.
SELECT COUNT(*) AS ROWS_,
       COUNT(PROJECT_NAME) AS WITH_PROJECT_,
       COUNT(DISTINCT TRANSACTION_ID) AS TXNS_,
       COUNT(DISTINCT CASE WHEN PROJECT_NAME IS NOT NULL
                           THEN TRANSACTION_ID END) AS TXNS_WITH_PROJECT_
FROM   DGSTREAM.OPUS_BASE_TRANSACTION;

-- P2 — eyeball: do these read as real project code-names?
SELECT PROJECT_NAME, COUNT(*) AS ROWS_
FROM   DGSTREAM.OPUS_BASE_TRANSACTION
WHERE  PROJECT_NAME IS NOT NULL
GROUP  BY PROJECT_NAME
ORDER  BY ROWS_ DESC
FETCH FIRST 15 ROWS ONLY;
