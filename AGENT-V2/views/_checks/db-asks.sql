-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on QA and
-- screenshot into ~/Desktop/ADK. SELECTs only, never session settings.
-- ===========================================================================

-- AFTER THE NEXT VIEW DEPLOY (DCM status exclusion 2026-09-28 + allocation
-- NULL 2026-09-29 — the SAME order-view file, re-copy it): views/_deploy-check.sql
-- sections B-DCM, C, D-ECM and D-DCM. New rows: 27 / 27b (deal count and no
-- excluded status), 25 / 25b (tranche), 26 / 26b / 26c (order statuses in
-- scope, row count ~1.25M, no NULL status), 28 / 28b (orders with no
-- allocation recorded, by product — INFO, expect > 0 now).

-- ===========================================================================
-- N. IPREO OFFERING TYPE — VALUES (UAT). M listed the columns: IPREO_ISSUE has
-- ISSUE_TYPE_CD / ISSUE_TYPE_NM / OFFERING_TYPE (a NUMBER code) and
-- IPREO_PRODUCT has SEC_TYPE_CD. Three statements decide the view fill; N4
-- is OPTIONAL (Citi's role per tranche, a separate lead).
-- ===========================================================================

-- N1. Issue type vocabulary (raw rows carry every DG version — read the
--     DISTINCT ISS_ID column).
SELECT ISSUE_TYPE_CD, ISSUE_TYPE_NM, OFFERING_TYPE,
       COUNT(*) AS ROWS_, COUNT(DISTINCT ISS_ID) AS ISSUES
FROM   DGSTREAM.IPREO_ISSUE
GROUP  BY ISSUE_TYPE_CD, ISSUE_TYPE_NM, OFFERING_TYPE
ORDER  BY ISSUES DESC;

-- N2. Security type code per product.
SELECT SEC_TYPE_CD, COUNT(*) AS ROWS_, COUNT(DISTINCT ISS_ID) AS ISSUES
FROM   DGSTREAM.IPREO_PRODUCT
GROUP  BY SEC_TYPE_CD
ORDER  BY ISSUES DESC;

-- N3. The mapping key: for the ~313 Ipreo deals whose mirror row DOES carry
--     an offering type, which raw issue type sits behind 'IPO' and 'FO'.
SELECT I.ISSUE_TYPE_CD, I.ISSUE_TYPE_NM, I.OFFERING_TYPE,
       ET.PRODUCT_OFFERING_TYPE_VALUE AS MIRROR_OFFERING_TYPE,
       COUNT(DISTINCT I.ISS_ID) AS ISSUES
FROM   DGSTREAM.IPREO_ISSUE I
JOIN   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION ET
       ON ET.DEAL_TRANSACTION_ID = TO_CHAR(I.ISS_ID)
WHERE  ET.PRODUCT_OFFERING_TYPE_VALUE IS NOT NULL
GROUP  BY I.ISSUE_TYPE_CD, I.ISSUE_TYPE_NM, I.OFFERING_TYPE, ET.PRODUCT_OFFERING_TYPE_VALUE
ORDER  BY ISSUES DESC;

-- N4 (OPTIONAL). Citi's role per Ipreo tranche — a direct answer to "Citi's
--     role" on 10-digit-id deals if the vocabulary is clean.
SELECT DEAL_OWNER_CALENDAR_ROLE_CD, DEAL_OWNER_CALENDAR_ROLE_NM,
       COUNT(*) AS ROWS_, COUNT(DISTINCT ISS_ID) AS ISSUES
FROM   DGSTREAM.IPREO_TRANCHE
GROUP  BY DEAL_OWNER_CALENDAR_ROLE_CD, DEAL_OWNER_CALENDAR_ROLE_NM
ORDER  BY ISSUES DESC;
