-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on QA and
-- screenshot into ~/Desktop/ADK. SELECTs only, never session settings.
-- ===========================================================================

-- AFTER THE NEXT VIEW DEPLOY (DCM status exclusion, repo 2026-09-28):
-- views/_deploy-check.sql sections B-DCM, C and D-DCM. New rows: 27 / 27b
-- (deal count and no excluded status), 25 / 25b (tranche), 26 / 26b / 26c
-- (order statuses in scope, row count ~1.25M, no NULL status). That is all.
