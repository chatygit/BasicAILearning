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
--
-- P-SERIES RESULTS (PROD, 2026-08-28):
--  * P1: the OB_DCM_* book tables are EMPTY SHELLS (all 0 rows). The
--    GENERIC tables are live: OB_HEDGE_ORDER 300,741 / OB_HEDGE_TRADE
--    155,693. OB_INVESTOR_SALES = 19 rows (salesperson REFERENCE table,
--    joins via OB_ORDER.SALES_ID). VG_BCOSMOS_CUSTOMER_ACCOUNT = 0.
--    NOT YET COUNTED (P1b below): OB_ORDER_TRADE(_SYNDICATE),
--    OB_TRANCHE_HEDGE_SECURITY, OB_ECM_ORDER_BOOK_*, OB_ECM_TRADE_BOOK_*,
--    VG_BCOSMOS_GENERAL_ACCOUNT.
--  * P2 (OB_ORDER, 5,021,143 rows): COUNTRY 4,767,836 (95%!) — DCM
--    investor country is RICH; REGION 1.2%; GEOGRAPHY 10.7%; SALES_ID
--    30%; LEGAL_ID 0.5%; RATIONALE 0.1%; DRAFT_ALLOC 2.4%.
--  * P3: ECM ISSUER_LEID 24,581/29,564 (83%) — easy release-3 column.
--  * P4: empty (DCM_ shells) — re-sample from the GENERIC tables (P1b).
--  * Id-series exact: 74,505 tranche rows / 1,916 with otid / 47,060
--    deals / 945 with otid / 891 otids / 786 join base+RP / 777 with
--    Primary Client. Syndicate census re-run: 376,991.
-- ===========================================================================

-- P1b — the LIVE tables the first pass missed + grain samples.
SELECT 'OB_ORDER_TRADE' AS T, COUNT(*) AS ROWS_ FROM DGSTREAM.OB_ORDER_TRADE
UNION ALL SELECT 'OB_ORDER_TRADE_SYNDICATE', COUNT(*) FROM DGSTREAM.OB_ORDER_TRADE_SYNDICATE
UNION ALL SELECT 'OB_TRANCHE_HEDGE_SECURITY', COUNT(*) FROM DGSTREAM.OB_TRANCHE_HEDGE_SECURITY
UNION ALL SELECT 'OB_ECM_ORDER_BOOK_DETAILS', COUNT(*) FROM DGSTREAM.OB_ECM_ORDER_BOOK_DETAILS
UNION ALL SELECT 'OB_ECM_ORDER_BOOK_SUMMARY', COUNT(*) FROM DGSTREAM.OB_ECM_ORDER_BOOK_SUMMARY
UNION ALL SELECT 'OB_ECM_TRADE_BOOK_INVESTOR_TRADE', COUNT(*) FROM DGSTREAM.OB_ECM_TRADE_BOOK_INVESTOR_TRADE
UNION ALL SELECT 'OB_ECM_TRADE_BOOK_UNDERWRITING_TRADE', COUNT(*) FROM DGSTREAM.OB_ECM_TRADE_BOOK_UNDERWRITING_TRADE
UNION ALL SELECT 'VG_BCOSMOS_GENERAL_ACCOUNT', COUNT(*) FROM DGSTREAM.VG_BCOSMOS_GENERAL_ACCOUNT;

-- P5 — grain/key samples from the LIVE hedge + trade tables.
SELECT * FROM DGSTREAM.OB_HEDGE_ORDER FETCH FIRST 10 ROWS ONLY;
SELECT * FROM DGSTREAM.OB_ORDER_TRADE FETCH FIRST 10 ROWS ONLY;

-- P6 — DCM order-type vocabulary (prompt: "allowed order types"):
SELECT TYPE, SUB_TYPE, IS_FIRM_ORDER, IS_POT, COUNT(*) AS ROWS_
FROM   DGSTREAM.OB_ORDER
GROUP  BY TYPE, SUB_TYPE, IS_FIRM_ORDER, IS_POT
ORDER  BY ROWS_ DESC
FETCH FIRST 20 ROWS ONLY;

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
