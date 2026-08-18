-- ===========================================================================
-- ISSUER NAME SOURCE CHECK — tech guidance (Ibanescu, 5/28): ECM issuer name
-- should be PARTY_NAME from OPUS_BASE_TRANSACTION_RELATED_PARTIES where
-- PARTY_ROLE = 'Primary Client', not OPUS_ECM_TRANSACTION.ISSUER_NAME_FROM_
-- SOURCE (which shows as "—" on many QA answers). Measure before the swap —
-- it touches the ECM branch of ALL THREE data views (deal, tranche, order).
-- ===========================================================================

-- Q1 — the table's shape (join keys are unknown; adjust Q2-Q5 to match).
SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH, NULLABLE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM'
AND    TABLE_NAME = 'OPUS_BASE_TRANSACTION_RELATED_PARTIES'
ORDER  BY COLUMN_ID;

-- Q2 — the role vocabulary (is 'Primary Client' the exact literal? case?).
SELECT PARTY_ROLE, COUNT(*) AS ROWS_
FROM   DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
GROUP  BY PARTY_ROLE
ORDER  BY ROWS_ DESC;

-- ---------------------------------------------------------------------------
-- Q3-Q5 assume the join key is the base/deal transaction id — CONFIRM the
-- actual key column from Q1 and adjust (candidates: TRANSACTION_ID,
-- DEAL_TRANSACTION_ID, TRANSACTION_ID).
-- ---------------------------------------------------------------------------

-- Q3 — grain: multiple 'Primary Client' rows per transaction? (dedupe need)
SELECT MULTI_ROWS, COUNT(*) AS TRANSACTIONS
FROM (
    SELECT TRANSACTION_ID, COUNT(*) AS MULTI_ROWS
    FROM   DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
    WHERE  PARTY_ROLE = 'Primary Client'
    GROUP  BY TRANSACTION_ID
)
GROUP  BY MULTI_ROWS
ORDER  BY MULTI_ROWS;

-- Q4 — coverage vs the CURRENT source, over the deal view's ECM population:
-- how many deals gain a name, how many disagree, how many lose one.
SELECT COUNT(*) AS ECM_DEALS,
       COUNT(D.ISSUER_NAME)                        AS CURRENT_HAS_NAME,
       COUNT(P.PARTY_NAME)                         AS PROPOSED_HAS_NAME,
       SUM(CASE WHEN D.ISSUER_NAME IS NULL AND P.PARTY_NAME IS NOT NULL
                THEN 1 ELSE 0 END)                 AS GAINED,
       SUM(CASE WHEN D.ISSUER_NAME IS NOT NULL AND P.PARTY_NAME IS NULL
                THEN 1 ELSE 0 END)                 AS LOST,
       SUM(CASE WHEN D.ISSUER_NAME IS NOT NULL AND P.PARTY_NAME IS NOT NULL
                 AND UPPER(D.ISSUER_NAME) <> UPPER(P.PARTY_NAME)
                THEN 1 ELSE 0 END)                 AS DISAGREE
FROM   DGSTREAM.VW_DEAL_SUMMARY D
LEFT JOIN (
    SELECT TRANSACTION_ID, PARTY_NAME
    FROM (
        SELECT TRANSACTION_ID, PARTY_NAME,
               ROW_NUMBER() OVER (PARTITION BY TRANSACTION_ID
                                  ORDER BY PUBLISHED_TS DESC) AS RN_
        FROM   DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
        WHERE  PARTY_ROLE = 'Primary Client'
    ) WHERE RN_ = 1
) P ON P.TRANSACTION_ID = D.DEAL_ID
WHERE  D.PRODUCT = 'ECM';

-- Q5 — eyeball the disagreements (which source looks right?).
SELECT D.DEAL_ID, D.DEAL_NAME, D.ISSUER_NAME AS CURRENT_NAME,
       P.PARTY_NAME AS PROPOSED_NAME
FROM   DGSTREAM.VW_DEAL_SUMMARY D
JOIN (
    SELECT TRANSACTION_ID, PARTY_NAME
    FROM (
        SELECT TRANSACTION_ID, PARTY_NAME,
               ROW_NUMBER() OVER (PARTITION BY TRANSACTION_ID
                                  ORDER BY PUBLISHED_TS DESC) AS RN_
        FROM   DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
        WHERE  PARTY_ROLE = 'Primary Client'
    ) WHERE RN_ = 1
) P ON P.TRANSACTION_ID = D.DEAL_ID
WHERE  D.PRODUCT = 'ECM'
AND    D.ISSUER_NAME IS NOT NULL
AND    UPPER(D.ISSUER_NAME) <> UPPER(P.PARTY_NAME)
FETCH FIRST 20 ROWS ONLY;

-- ===========================================================================
-- PART 2 — DCM side (Samir, 2026-08-18): "OB_DEAL_ISSUER.NAME is for ECM".
-- ALL THREE views' DCM branches source ISSUER_NAME from OB_DEAL_ISSUER.NAME;
-- if the table is ECM-side, DCM issuer names are misdirected everywhere.
-- ===========================================================================

-- Q6 — the symptom, measured: issuer-name population per product, per view.
SELECT 'deal' AS V, PRODUCT, COUNT(*) AS ROWS_, COUNT(ISSUER_NAME) AS WITH_NAME,
       ROUND(100 * COUNT(ISSUER_NAME) / COUNT(*), 1) AS PCT
FROM DGSTREAM.VW_DEAL_SUMMARY GROUP BY PRODUCT
UNION ALL
SELECT 'tranche', PRODUCT, COUNT(*), COUNT(ISSUER_NAME),
       ROUND(100 * COUNT(ISSUER_NAME) / COUNT(*), 1)
FROM DGSTREAM.VW_TRANCHE_SUMMARY GROUP BY PRODUCT
UNION ALL
SELECT 'order', PRODUCT, COUNT(*), COUNT(ISSUER_NAME),
       ROUND(100 * COUNT(ISSUER_NAME) / COUNT(*), 1)
FROM DGSTREAM.VW_ORDER_DETAIL GROUP BY PRODUCT;

-- Q7 — what OB_DEAL_ISSUER actually holds: shape + key format + sample.
SELECT COLUMN_NAME, DATA_TYPE, DATA_LENGTH
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'OB_DEAL_ISSUER'
ORDER  BY COLUMN_ID;

SELECT DEAL_TRANCHE_ID, NAME
FROM   DGSTREAM.OB_DEAL_ISSUER
FETCH FIRST 20 ROWS ONLY;

-- Q8 — join-hit rate: how many DCM tranches actually find an issuer row via
-- the views' join key (DEAL_ID || '-' || TRANCHE_ID)?
SELECT COUNT(*) AS DCM_TRANCHES,
       SUM(CASE WHEN DI.DEAL_TRANCHE_ID IS NOT NULL THEN 1 ELSE 0 END) AS WITH_ISSUER_ROW
FROM (
    SELECT DISTINCT DEAL_ID, TRANCHE_ID FROM DGSTREAM.OB_DEAL_TRANCHE
) DT
LEFT JOIN DGSTREAM.OB_DEAL_ISSUER DI
  ON DI.DEAL_TRANCHE_ID = DT.DEAL_ID || '-' || DT.TRANCHE_ID;

-- Q4b — DOES THIS TABLE COVER DCM TOO? 143k Primary Client rows dwarf the
-- ECM deal count, and the name says BASE transaction — if TRANSACTION_ID
-- also matches DCM deal ids, this table answers Samir's open question (the
-- DCM issuer source) in the same swap.
SELECT COUNT(*) AS DCM_DEALS,
       SUM(CASE WHEN P.TRANSACTION_ID IS NOT NULL THEN 1 ELSE 0 END) AS MATCHED
FROM   DGSTREAM.VW_DEAL_SUMMARY D
LEFT JOIN (
    SELECT DISTINCT TRANSACTION_ID
    FROM   DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
    WHERE  PARTY_ROLE = 'Primary Client'
) P ON P.TRANSACTION_ID = D.DEAL_ID
WHERE  D.PRODUCT = 'DCM';

-- Q3b — is the multi-row tail VERSIONING or genuinely several primary
-- clients? Q3 found up to 1,232 rows per transaction — if DISTINCT names per
-- transaction is ~1 almost everywhere, the rows are versions and
-- latest-wins dedupe is safe; several DISTINCT names would mean joint
-- issuers and a different design.
SELECT MULTI_NAMES, COUNT(*) AS TRANSACTIONS
FROM (
    SELECT TRANSACTION_ID, COUNT(DISTINCT UPPER(PARTY_NAME)) AS MULTI_NAMES
    FROM   DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
    WHERE  PARTY_ROLE = 'Primary Client'
    GROUP  BY TRANSACTION_ID
)
GROUP  BY MULTI_NAMES
ORDER  BY MULTI_NAMES;
