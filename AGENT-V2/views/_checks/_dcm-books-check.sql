-- ===========================================================================
-- DCM BOOKS / PROMPT-SUPPORT VALIDATION (D2, 2026-08-27). The planned test
-- prompts assume concepts the views do not carry: hedge book, trade book,
-- CV book, firm accounts, salespeople, trade ids, issuer LEI, DCM
-- syndicate members, DCM "allowed order types", tranche announcement
-- dates. Measure what the SOURCE has before promising anything. Run in
-- PROD; screenshot per query.
--
-- RESULTS (PROD, 2026-08-27) — EVERYTHING EXISTS AT SOURCE:
--  * V1: dedicated tables for every concept — DCM hedge book
--    (OB_DCM_HEDGE_ORDER/TRADE), DCM trade book (OB_DCM_ORDER_TRADE
--    +_SYNDICATE), ECM book/trade-book family, OB_INVESTOR_SALES,
--    VG_BCOSMOS_*_ACCOUNT. Full census in _reference/base-table-columns.md.
--  * V2: OB_ORDER has 82 columns (we read 7). DCM investor GEOGRAPHY
--    (COUNTRY/REGION/GEOGRAPHY), CLASSIFICATION, QIB, salesperson
--    (SALES_ID/SOEID/names), allocation lifecycle (DRAFT/SOFT/ISN_ALLOC,
--    RATIONALE), OBO identity, LEGAL_ID all EXIST — the "not available
--    for DCM" refusals are OUR VIEW placeholders, not data absence.
--  * V3: LEI exists — INVESTOR_LEID (ECM order, hedge orders),
--    ISSUER_LEID (OPUS_ECM_TRANSACTION — ECM issuer LEI answerable).
--    No DCM issuer LEI found.
--  * V4: 376,942 syndicate-member rows, 100% DCM-keyed — DCM syndicate
--    membership fully exists; views show only the B&D today.
-- NEXT: population/grain measurement per table (P-series below) before
-- any view design; this is NEW-VIEW scope (hedge/trade grains), not
-- column adds.
-- ===========================================================================

-- P-SERIES — population + join-rate per new table (run when convenient).
-- P1 — row counts in one pass.
SELECT 'OB_DCM_HEDGE_ORDER' AS T, COUNT(*) AS ROWS_ FROM DGSTREAM.OB_DCM_HEDGE_ORDER
UNION ALL SELECT 'OB_DCM_HEDGE_TRADE', COUNT(*) FROM DGSTREAM.OB_DCM_HEDGE_TRADE
UNION ALL SELECT 'OB_DCM_ORDER_TRADE', COUNT(*) FROM DGSTREAM.OB_DCM_ORDER_TRADE
UNION ALL SELECT 'OB_DCM_ORDER_TRADE_SYNDICATE', COUNT(*) FROM DGSTREAM.OB_DCM_ORDER_TRADE_SYNDICATE
UNION ALL SELECT 'OB_HEDGE_ORDER', COUNT(*) FROM DGSTREAM.OB_HEDGE_ORDER
UNION ALL SELECT 'OB_HEDGE_TRADE', COUNT(*) FROM DGSTREAM.OB_HEDGE_TRADE
UNION ALL SELECT 'OB_INVESTOR_SALES', COUNT(*) FROM DGSTREAM.OB_INVESTOR_SALES
UNION ALL SELECT 'VG_BCOSMOS_CUSTOMER_ACCOUNT', COUNT(*) FROM DGSTREAM.VG_BCOSMOS_CUSTOMER_ACCOUNT;

-- P2 — OB_ORDER riches population (the DCM geography/classification story).
SELECT COUNT(*) AS ROWS_,
       COUNT(COUNTRY_NAME) AS COUNTRY_,
       COUNT(REGION) AS REGION_,
       COUNT(GEOGRAPHY) AS GEOGRAPHY_,
       COUNT(SALES_ID) AS SALES_,
       COUNT(LEGAL_ID) AS LEGAL_ID_,
       COUNT(RATIONALE) AS RATIONALE_,
       COUNT(DRAFT_ALLOC) AS DRAFT_ALLOC_
FROM   DGSTREAM.OB_ORDER;

-- P3 — ECM issuer LEI population.
SELECT COUNT(*) AS ECM_TXNS, COUNT(ISSUER_LEID) AS WITH_LEI
FROM   DGSTREAM.OPUS_ECM_TRANSACTION;

-- P4 — hedge/trade key shapes (grain design input): sample 10 each.
SELECT * FROM DGSTREAM.OB_DCM_HEDGE_ORDER FETCH FIRST 10 ROWS ONLY;
SELECT * FROM DGSTREAM.OB_DCM_ORDER_TRADE FETCH FIRST 10 ROWS ONLY;

-- V1 — are there book/hedge/trade tables at all?
SELECT table_name
FROM   all_tables
WHERE  owner = 'DGSTREAM'
AND    (table_name LIKE '%HEDGE%' OR table_name LIKE '%BOOK%'
     OR table_name LIKE '%TRADE%' OR table_name LIKE '%SALES%'
     OR table_name LIKE '%ACCOUNT%')
ORDER  BY table_name;

-- V2 — the full OB_ORDER column list (never desc'd; OWNER/ALL_OWNERS came
--      from a LIKE probe). Book type, trade id, salesperson, firm account,
--      order type and hedge fields would live here if anywhere.
SELECT column_id, column_name, data_type
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM' AND table_name = 'OB_ORDER'
ORDER  BY column_id;

-- V3 — LEI anywhere in the schema?
SELECT table_name, column_name
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM' AND column_name LIKE '%LEI%'
ORDER  BY table_name;

-- V4 — DCM syndicate membership: does OB_TRANCHE_SYNDICATE_MEMBER carry
--      rows for DCM-keyed tranches, or is it ECM-only?
SELECT COUNT(*) AS SYND_ROWS,
       COUNT(CASE WHEN DT.DEAL_ID IS NOT NULL THEN 1 END) AS DCM_KEYED_ROWS
FROM   DGSTREAM.OB_TRANCHE_SYNDICATE_MEMBER S
LEFT JOIN (SELECT DISTINCT DEAL_ID, TRANCHE_ID FROM DGSTREAM.OB_DEAL_TRANCHE) DT
  ON S.DEAL_TRANCHE_ID = DT.DEAL_ID || '-' || DT.TRANCHE_ID;

-- V5 — tranche announcement date is ALREADY MEASURED (29,534/74,281) —
--      no query needed; it is a release-train exposure decision.
