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
-- M. IPREO OFFERING TYPE (UAT). L1 showed OFFERING_TYPE blank on 17,307 of
-- 17,310 Ipreo Common Stock deals, so "IPOs of 2008" cannot find Visa. The
-- mirror does not carry it; the raw tables may. Column lists first (three
-- SELECTs on the dictionary — instant), values next round.
-- ===========================================================================
SELECT TABLE_NAME, COLUMN_ID, COLUMN_NAME, DATA_TYPE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME IN ('IPREO_ISSUE', 'IPREO_PRODUCT', 'IPREO_TRANCHE')
ORDER  BY TABLE_NAME, COLUMN_ID;
