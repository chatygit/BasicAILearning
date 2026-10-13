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

-- BEFORE THE DEPLOY: run AB below (one dictionary SELECT). It must return
-- DG_VERSION — vw_tranche_summary's fee block now orders by it (PR bot
-- 2026-10-08: ROWID is not chronological). No row = tell me, do not deploy.
-- AB. Must return DG_VERSION:
SELECT COLUMN_NAME FROM ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'IPREO_PRODUCTFEE' AND COLUMN_NAME = 'DG_VERSION';

-- THEN (census AA / AC): deploy vw_deal_summary,
-- vw_order_detail and vw_tranche_summary (all three now take the latest
-- OPUS_BASE_TRANSACTION version as a whole row) (the tranche view carries the Ipreo product-type, the
-- whole-row product / fee dedupes and the Citi regex). Then deploy-check A0,
-- A (A02 89 / A03 70), C (C11 must now PASS), D-ECM (D01 must now PASS; D15
-- limit counts). Nothing else open.

-- AD CLOSED (UAT 2026-10-08): the SOLO rule counts every real Citi label on
-- both products and correctly rejects Citizens and CITIC; the only miss is the
-- UAT-only label 'CitiTestSyndicate' (268 ECM rows, no space after CITI). No
-- view change.

-- ===========================================================================
-- AE. ECM ALLOCATION SOURCE — RUN ON PROD (the deal is a PROD deal; UAT may
-- not carry it). SELECTs only. The agent showed "Not recorded" for every
-- top investor on Space Exploration Technologies: the ECM order view reads
-- allocation from OB_ECM_ORDER.PRIVATE_ALLOC only. Which column actually
-- carries ECM allocations — on this deal and across the book? Three
-- statements, names from the 2026-08-31 table description.
-- ===========================================================================

-- AE1. The deal(s) and their status.
SELECT ET.DEAL_TRANSACTION_ID, MAX(ET.SYNDICATE_DEAL_NAME) AS DEAL_NAME,
       MAX(S.STATUS_VALUE) AS EXECUTION_STATUS
FROM   DGSTREAM.OPUS_ECM_TRANSACTION ET
LEFT JOIN DGSTREAM.OPUS_ECM_TRANSACTION_STATUS S
       ON S.ECM_TRANSACTION_ID = ET.ECM_TRANSACTION_ID AND S.STATUS_TYPE = 'Execution_Status'
WHERE  UPPER(ET.SYNDICATE_DEAL_NAME) LIKE '%SPACE EXPLORATION%'
GROUP  BY ET.DEAL_TRANSACTION_ID;

-- AE2. Every allocation column on that deal's orders.
SELECT O.DEAL_ID, O.ALLOCATION_STATUS,
       COUNT(*) AS ORDER_ROWS,
       COUNT(O.PRIVATE_ALLOC) AS PRIVATE_, SUM(O.PRIVATE_ALLOC) AS PRIVATE_SUM,
       COUNT(O.FINAL_ALLOC) AS FINAL_, SUM(O.FINAL_ALLOC) AS FINAL_SUM,
       COUNT(O.DRAFT_ALLOC) AS DRAFT_, SUM(O.DRAFT_ALLOC) AS DRAFT_SUM,
       COUNT(O.INST_ALLOCATION_QTY) AS INST_, SUM(O.INST_ALLOCATION_QTY) AS INST_SUM
FROM   DGSTREAM.OB_ECM_ORDER O
WHERE  O.DEAL_ID IN (SELECT DEAL_TRANSACTION_ID FROM DGSTREAM.OPUS_ECM_TRANSACTION
                     WHERE UPPER(SYNDICATE_DEAL_NAME) LIKE '%SPACE EXPLORATION%')
GROUP  BY O.DEAL_ID, O.ALLOCATION_STATUS
ORDER  BY O.DEAL_ID, ORDER_ROWS DESC;

-- AE3. Across the whole ECM book: how often is each column filled when
--      PRIVATE_ALLOC is blank (what a fallback would add). One full scan of
--      OB_ECM_ORDER — run it on PROD too; on UAT the shape may differ.
SELECT COUNT(*) AS ORDER_ROWS,
       COUNT(PRIVATE_ALLOC) AS PRIVATE_,
       COUNT(CASE WHEN PRIVATE_ALLOC IS NULL AND FINAL_ALLOC IS NOT NULL THEN 1 END) AS FINAL_ONLY,
       COUNT(CASE WHEN PRIVATE_ALLOC IS NULL AND DRAFT_ALLOC IS NOT NULL THEN 1 END) AS DRAFT_ONLY,
       COUNT(CASE WHEN PRIVATE_ALLOC IS NULL AND INST_ALLOCATION_QTY IS NOT NULL THEN 1 END) AS INST_ONLY,
       COUNT(CASE WHEN PRIVATE_ALLOC IS NOT NULL AND FINAL_ALLOC IS NOT NULL
                   AND PRIVATE_ALLOC <> FINAL_ALLOC THEN 1 END) AS PRIVATE_NE_FINAL
FROM   DGSTREAM.OB_ECM_ORDER;
