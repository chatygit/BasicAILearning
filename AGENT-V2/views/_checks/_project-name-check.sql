-- ===========================================================================
-- PROJECT NAME (Mike's observations doc, 2a — "Deal Launcher shows
-- ProjectName; is it consumed?"). 2026-08-18.
-- The column EXISTS at source: OPUS_BASE_TRANSACTION.PROJECT_NAME
-- (VARCHAR2, col 5 — see _reference/base-table-columns.md). ECM-side only;
-- no OB-world equivalent found, so DCM would be a NULL placeholder.
-- Measure-first: population + a sample decide whether it joins the next
-- view batch (MAX-over-versions rollup, same shape as DEAL_REGION).
-- ===========================================================================

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
