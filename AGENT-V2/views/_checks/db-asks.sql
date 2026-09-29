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
-- O. CAN AN IPO BE DERIVED ON THE IPREO HISTORY? (UAT, two statements.)
-- N showed IPREO_ISSUE.OFFERING_TYPE (1 = IPO, 2 = FO) populated on the same
-- 313 issues the mirror carries; the other ~19,300 have nothing. The one
-- stored signal an IPO leaves is a FILING RANGE (IPREO_PRODUCT INIT_FILE_PX_LO
-- / _HI) — follow-ons price off the market. O1 tests that signal on the 313
-- labelled issues; O2 says how much of the history it would cover. Build the
-- derived fill only if O1 shows the range on (nearly) every IPO and (nearly)
-- no FO.
-- ===========================================================================

-- O1. Filing range vs the known label (an issue with several products may
--     count in two buckets — read proportions).
SELECT ET.PRODUCT_OFFERING_TYPE_VALUE AS LABEL,
       CASE WHEN P.INIT_FILE_PX_LO IS NOT NULL OR P.INIT_FILE_PX_HI IS NOT NULL
            THEN 'RANGE' ELSE 'NO RANGE' END AS FILING_RANGE,
       CASE WHEN P.FILE_PX IS NOT NULL THEN 'FILE_PX' ELSE 'NO FILE_PX' END AS FILE_PX_,
       COUNT(DISTINCT P.ISS_ID) AS ISSUES
FROM   DGSTREAM.IPREO_PRODUCT P
JOIN   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION ET
       ON ET.DEAL_TRANSACTION_ID = TO_CHAR(P.ISS_ID)
WHERE  ET.PRODUCT_OFFERING_TYPE_VALUE IS NOT NULL
GROUP  BY ET.PRODUCT_OFFERING_TYPE_VALUE,
          CASE WHEN P.INIT_FILE_PX_LO IS NOT NULL OR P.INIT_FILE_PX_HI IS NOT NULL
               THEN 'RANGE' ELSE 'NO RANGE' END,
          CASE WHEN P.FILE_PX IS NOT NULL THEN 'FILE_PX' ELSE 'NO FILE_PX' END
ORDER  BY 1, 2, 3;

-- O2. The same signal across the unlabelled history, with the years it spans.
SELECT CASE WHEN P.INIT_FILE_PX_LO IS NOT NULL OR P.INIT_FILE_PX_HI IS NOT NULL
            THEN 'RANGE' ELSE 'NO RANGE' END AS FILING_RANGE,
       CASE WHEN P.FILE_PX IS NOT NULL THEN 'FILE_PX' ELSE 'NO FILE_PX' END AS FILE_PX_,
       COUNT(DISTINCT P.ISS_ID) AS ISSUES,
       TO_CHAR(MIN(I.OFFER_DT), 'YYYY') AS FIRST_YEAR,
       TO_CHAR(MAX(I.OFFER_DT), 'YYYY') AS LAST_YEAR
FROM   DGSTREAM.IPREO_PRODUCT P
JOIN   DGSTREAM.IPREO_ISSUE I ON I.ISS_ID = P.ISS_ID
WHERE  I.OFFERING_TYPE IS NULL
GROUP  BY CASE WHEN P.INIT_FILE_PX_LO IS NOT NULL OR P.INIT_FILE_PX_HI IS NOT NULL
               THEN 'RANGE' ELSE 'NO RANGE' END,
          CASE WHEN P.FILE_PX IS NOT NULL THEN 'FILE_PX' ELSE 'NO FILE_PX' END
ORDER  BY ISSUES DESC;
