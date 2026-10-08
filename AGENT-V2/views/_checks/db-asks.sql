-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on QA and
-- screenshot into ~/Desktop/ADK. SELECTs only, never session settings.
-- ===========================================================================

-- VIEWS DEPLOYED 2026-09-29 (status exclusion + allocation NULL). RUN NOW:
-- views/_deploy-check.sql A0, then sections B-DCM, C, D-ECM, D-DCM. Rows to
-- read: 27 / 27b (deal count, no excluded status), 25 / 25b (tranche),
-- 26 / 26b / 26c (order statuses in scope, ~1.25M rows, no NULL status),
-- 28 / 28b (orders with no allocation recorded, by product — expect > 0).
--
-- ONE MORE DEPLOY, vw_deal_summary ONLY (PR bot 2026-09-29): the DCM currency
-- roll-up (CU block) now drops cancelled / postponed / deleted / archived
-- tranches like the rest of the branch. After it: A0 + B-DCM again (27 / 27b
-- unchanged; the CURRENCIES column of a deal with a cancelled tranche loses
-- that tranche's currency).

-- BATCH C IS CLEARED TO DEPLOY (db-asks P0, 2026-10-05: all 21 source names
-- valid; the Ipreo mirror carries ISSUER_COUNTRY_NAME, nothing else of the
-- batch). Deploy vw_deal_summary, vw_tranche_summary, vw_order_detail (the
-- deal view also carries the currency roll-up fix from 2026-09-29), then run
-- views/_deploy-check.sql (rewritten 2026-10-05): A0, A (A01-A03 = the three
-- views' column counts 43 / 89 / 65), B-ECM (B08), B-DCM (B14), C (C08 / C09).
-- Sections D-ECM / D-DCM are unchanged by this batch.

-- CLEARED (2026-10-08, census AA / AB / AC): deploy vw_deal_summary,
-- vw_order_detail and vw_tranche_summary (all three now take the latest
-- OPUS_BASE_TRANSACTION version as a whole row) (the tranche view carries the Ipreo product-type, the
-- whole-row product / fee dedupes and the Citi regex). Then deploy-check A0,
-- A (A02 89 / A03 70), C (C11 must now PASS), D-ECM (D01 must now PASS; D15
-- limit counts). Nothing else open.

-- AD. CITI-SOLO REGEX COVERAGE (UAT, two statements). The OPUS ECM and DCM
-- branches decide SOLO with '^CITI(GROUP|BANK)?([ _]|$)', so a label such as
-- 'Citibank, N.A.' (comma after CITIBANK) is NOT Citi and turns a Citi-only
-- tranche SHARED. List every Citi-looking label and whether the rule sees it.
SELECT 'ECM' AS SRC, S.SYNDICATE_MEMBER_NAME AS LABEL_, COUNT(*) AS ROWS_,
       CASE WHEN REGEXP_LIKE(S.SYNDICATE_MEMBER_NAME, '^CITI(GROUP|BANK)?([ _]|$)', 'i') THEN 'counted' ELSE 'MISSED' END AS RULE_
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE S
WHERE  UPPER(S.SYNDICATE_MEMBER_NAME) LIKE 'CITI%'
GROUP  BY S.SYNDICATE_MEMBER_NAME
ORDER  BY RULE_, ROWS_ DESC;

SELECT 'DCM' AS SRC, S.DEALER AS LABEL_, COUNT(*) AS ROWS_,
       CASE WHEN REGEXP_LIKE(S.DEALER, '^CITI(GROUP|BANK)?([ _]|$)', 'i') THEN 'counted' ELSE 'MISSED' END AS RULE_
FROM   DGSTREAM.OB_TRANCHE_SYNDICATE_MEMBER S
WHERE  UPPER(S.DEALER) LIKE 'CITI%'
GROUP  BY S.DEALER
ORDER  BY RULE_, ROWS_ DESC;
