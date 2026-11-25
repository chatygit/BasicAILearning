-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- AG / AH answered (UAT 2026-10-19): DEMAND_QTY is never the sum; the 1,566
-- 'other' scaled orders are CURRENCY / PERCENT bids where DEMAND_QTY is the
-- share-equivalent — correct. The ladder now shows the bid's unit and decimals.

-- AN answered (UAT 2026-11-12): non-zero percent IOI_QTY is a SHARE count (1,498
-- orders, min 896,525); 11,374 are 0 (no conversion). PERCENT is back in Ipreo
-- demand (vw_order_detail, vw_deal_summary).
-- AO answered (UAT 2026-11-12): the ECM Execution fields live in
-- OPUS_ECM_TRANSACTION_TRANCHE (final / current-file sizes, _PER_ fees, dates),
-- _TRANCHE_SYNDICATE (per-broker commitment, fees, retail), _TRANCHE_STABILIZATION
-- (position, over-allotment, secondary trade totals), _STABILIZATION_SECONDARY_TRADES
-- and _PRODUCT_DETAIL (share class, registration). AP settles their units.

-- ===========================================================================
-- AP. ECM EXECUTION UNITS (ORACLE, UAT, four SELECTs). Before these columns go
-- into the views: is each one a %, a share count, or $ per share?
-- ===========================================================================

-- AP1. Per-broker syndicate columns: fill and range (one row).
SELECT COUNT(*) AS ROWS_,
       COUNT(UNDERWRITING_COMMITMENT) AS UWC_N, MIN(UNDERWRITING_COMMITMENT) AS UWC_MIN, MAX(UNDERWRITING_COMMITMENT) AS UWC_MAX,
       COUNT(COMM_SHARES) AS CSH_N, MIN(COMM_SHARES) AS CSH_MIN, MAX(COMM_SHARES) AS CSH_MAX,
       COUNT(GROSS_SPREAD) AS GS_N, MIN(GROSS_SPREAD) AS GS_MIN, MAX(GROSS_SPREAD) AS GS_MAX,
       COUNT(UN_FEE_PER) AS UWP_N, MIN(UN_FEE_PER) AS UWP_MIN, MAX(UN_FEE_PER) AS UWP_MAX,
       COUNT(MANAGEMENT_FEE_PER) AS MGP_N, MAX(MANAGEMENT_FEE_PER) AS MGP_MAX,
       COUNT(SELLING_CONCESSION_PER) AS SCP_N, MAX(SELLING_CONCESSION_PER) AS SCP_MAX,
       COUNT(TOTAL_RETAIL) AS RET_N, COUNT(TOTAL_RETAIL_RETAIL) AS RETR_N,
       COUNT(PRIVATE_BANKING_RETAIL) AS PB_N, COUNT(DIRECTED_SHARES) AS DS_N
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE;

-- AP2. Tranche fee and version columns: fill and range (one row).
SELECT COUNT(*) AS ROWS_,
       COUNT(GROSS_SPREAD_PER_FEE) AS GS_N, MIN(GROSS_SPREAD_PER_FEE) AS GS_MIN, MAX(GROSS_SPREAD_PER_FEE) AS GS_MAX,
       COUNT(UNDERWRITING_PER_FEE) AS UWP_N, MAX(UNDERWRITING_PER_FEE) AS UWP_MAX,
       COUNT(MANAGEMENT_PER_FEE) AS MGP_N, MAX(MANAGEMENT_PER_FEE) AS MGP_MAX,
       COUNT(SELLING_CONCESSION_PER_FEE) AS SCP_N, MAX(SELLING_CONCESSION_PER_FEE) AS SCP_MAX,
       COUNT(INCENTIVE_FEE) AS INC_N, COUNT(GLOBAL_COORDINATOR_FEE) AS GC_N,
       COUNT(RE_ALLOWANCE_FEE) AS RA_N, COUNT(INTERNAL_SELLING_CONCESSION_FEE) AS ISC_N,
       COUNT(FINAL_TRANCHE_OFFER_SIZE) AS FIN_N, COUNT(FINAL_PRIMARY_SHARES) AS FINP_N,
       COUNT(TRANCHE_CURRENT_FILE_SIZE) AS CUR_N, COUNT(TRANCHE_CURRENT_FILE_AMOUNT) AS CURA_N,
       COUNT(BOOKS_OPEN_AT) AS BO_N, COUNT(PUBLIC_FILING_DATE) AS PF_N, COUNT(DEAL_CAPTAIN) AS CAP_N
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE;

-- AP3. Stabilization table: grain, fill, and what LOSS_OR_GAIN holds (one row).
SELECT COUNT(*) AS ROWS_, COUNT(DISTINCT ECM_TRANSACTION_TRANCHE_ID) AS TRANCHES_,
       COUNT(CURRENT_POSITION) AS POS_N, COUNT(CURRENT_NAKED_SHORT_POSITION) AS NAKED_N,
       COUNT(OVERALLOTMENT_EXERCISED) AS OAX_N, COUNT(OVERALLOTMENT_AVAILABLE) AS OAA_N,
       COUNT(OVERALLOTMENT_GRANTED_TS) AS GR_N, COUNT(OVERALLOTMENT_EXPIRY_TS) AS EXP_N,
       COUNT(SECONDARY_TRADE_TOTALS) AS ST_N, COUNT(SECONDARY_TRADE_AVERAGE_PRICE) AS SAP_N,
       MIN(SECONDARY_TRADE_LOSS_OR_GAIN) AS LG_MIN, MAX(SECONDARY_TRADE_LOSS_OR_GAIN) AS LG_MAX
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_STABILIZATION;

-- AP4. One tranche side by side: its brokers' commitment and fee columns next
--      to the tranche size and spread, newest syndicate version only. Shows
--      whether commitment is % or shares and whether _PER_ is % or $ / share.
WITH PICK AS (
    SELECT ECM_TRANSACTION_TRANCHE_ID FROM (
        SELECT ECM_TRANSACTION_TRANCHE_ID FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
        WHERE  COMM_SHARES > 0 ORDER BY DG_UPDATED_TS DESC NULLS LAST)
    WHERE ROWNUM = 1)
SELECT S.SYNDICATE_MEMBER_NAME, S.SYNDICATE_ROLE, S.DG_VERSION,
       S.UNDERWRITING_COMMITMENT, S.COMM_SHARES, S.GROSS_SPREAD, S.UN_FEE, S.UN_FEE_PER,
       S.MANAGEMENT_FEE, S.MANAGEMENT_FEE_PER, S.SELLING_CONCESSION, S.SELLING_CONCESSION_PER,
       T.FINAL_TRANCHE_OFFER_SIZE, T.FINAL_TRANCHE_OFFER_AMOUNT, T.GROSS_SPREAD_PER_FEE,
       T.UNDERWRITING_PER_FEE, T.MANAGEMENT_PER_FEE, T.SELLING_CONCESSION_PER_FEE
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE S
JOIN   PICK P ON P.ECM_TRANSACTION_TRANCHE_ID = S.ECM_TRANSACTION_TRANCHE_ID
LEFT JOIN (
    SELECT X.*, ROW_NUMBER() OVER (PARTITION BY X.ECM_TRANSACTION_TRANCHE_ID
                                   ORDER BY X.DG_VERSION DESC NULLS LAST, X.ROWID DESC) AS RN_
    FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE X
    WHERE  X.ECM_TRANSACTION_TRANCHE_ID IN (SELECT ECM_TRANSACTION_TRANCHE_ID FROM PICK)) T
       ON T.ECM_TRANSACTION_TRANCHE_ID = S.ECM_TRANSACTION_TRANCHE_ID AND T.RN_ = 1
ORDER  BY S.DG_VERSION DESC, S.COMM_SHARES DESC NULLS LAST;

-- AL answered (UAT 2026-10-23): broker table columns exist and resolve every top
-- code (CITIUSA -> Citigroup Global Markets Inc.); the issuer regex strips only
-- deal-type suffixes; Ipreo IOI_QTY is the share / bond equivalent for every unit
-- (0 when never converted). No grant to DGSTREAM on the DGLOBE table and none
-- will be given — the view now carries a maintained code -> name list instead.
-- AM answered 2026-10-23: all 42 further codes added except LADENBUR (no name in
-- the reference) — the view lists 56 codes.

-- AFTER the deploy (not before): deploy-check A0 + A (A01 43 / A02 89 / A03 73)
-- + D-ECM, and time K3 — the investor-name block (CN) aggregates the whole
-- Ipreo order table on every Ipreo query; K3 was sub-second before.

-- AK answered (UAT 2026-10-23): Source = OB_ECM_ORDER.SOURCE (ONEBOOK = '1B',
-- ISN, CMG, SALES, DA); Indication USD = cash amount / quantity x USD limit;
-- RELATIVE_INDICATION empty. Both now view columns.

-- Deploy vw_order_detail (ladder largest-first, wider number masks,
-- ORDER_SOURCE, INDICATION_USD), then deploy-check A0 + A (A03 = 73) + D-ECM.

-- ===========================================================================
-- SB. STARBURST DEV ACCESS MAP (Trino SQL, Starburst editor, DEV). No schema
-- or catalog needs selecting: every name below is fully qualified.
-- SB1 (groups) + SB3 (catalogs) answered 2026-11-25: 38 catalogs; the
-- candidates are ecm_history_data(_iceberg) (hive / iceberg), bds_iceberg_ref,
-- dataglobe_s3 / dataglobe (hive), ecm / dcm / opus (MONGODB), bds_dg_oraas
-- (oracle, today's source). Groups include app_ibcbsb-dev-ecm-bds-dp,
-- app_ibcbsb-dev-dcm-bds-dp and app_ibcbsb-dev-ranger-users (Ranger).
-- WHY THE OLD SB4-SB6 FAILED: system.jdbc.tables walks EVERY catalog, so one
-- catalog you cannot read (or a slow Mongo / SQL Server one) fails the whole
-- statement. Now: one statement per catalog — a failure only costs that line.
-- ===========================================================================

-- (SB10 dropped 2026-11-25: bds_dg_oraas is NOT a Starburst source for the new
-- design — the DG data is migrated to ecm_history_data; live events will land
-- in a new S3 / Iceberg catalog, name TBC.)

-- SB11. Schemas and table counts, one catalog per statement. Screenshot each
--       result or its error; an "Access Denied" is an answer too.
SELECT 'ecm_history_data_iceberg' AS cat_, table_schema, count(*) AS tables_
FROM   ecm_history_data_iceberg.information_schema.tables
WHERE  table_schema <> 'information_schema' GROUP BY 1, 2 ORDER BY 2;
SELECT 'ecm_history_data' AS cat_, table_schema, count(*) AS tables_
FROM   ecm_history_data.information_schema.tables
WHERE  table_schema <> 'information_schema' GROUP BY 1, 2 ORDER BY 2;
SELECT 'bds_iceberg_ref' AS cat_, table_schema, count(*) AS tables_
FROM   bds_iceberg_ref.information_schema.tables
WHERE  table_schema <> 'information_schema' GROUP BY 1, 2 ORDER BY 2;
SELECT 'dataglobe_s3' AS cat_, table_schema, count(*) AS tables_
FROM   dataglobe_s3.information_schema.tables
WHERE  table_schema <> 'information_schema' GROUP BY 1, 2 ORDER BY 2;
SELECT 'dataglobe' AS cat_, table_schema, count(*) AS tables_
FROM   dataglobe.information_schema.tables
WHERE  table_schema <> 'information_schema' GROUP BY 1, 2 ORDER BY 2;
SELECT 'ecm' AS cat_, table_schema, count(*) AS tables_
FROM   ecm.information_schema.tables
WHERE  table_schema <> 'information_schema' GROUP BY 1, 2 ORDER BY 2;
SELECT 'dcm' AS cat_, table_schema, count(*) AS tables_
FROM   dcm.information_schema.tables
WHERE  table_schema <> 'information_schema' GROUP BY 1, 2 ORDER BY 2;
SELECT 'opus' AS cat_, table_schema, count(*) AS tables_
FROM   opus.information_schema.tables
WHERE  table_schema <> 'information_schema' GROUP BY 1, 2 ORDER BY 2;

-- SB12. Our source tables by name, in the four S3 catalogs most likely to hold
--       the DataGlobe landings (run each; each is one catalog).
SELECT 'ecm_history_data_iceberg' AS cat_, table_schema, table_name
FROM   ecm_history_data_iceberg.information_schema.tables
WHERE  regexp_like(lower(table_name), 'opus|ipreo|ob_|ecm|dcm|tranche|syndicate|order')
ORDER  BY 2, 3;
SELECT 'ecm_history_data' AS cat_, table_schema, table_name
FROM   ecm_history_data.information_schema.tables
WHERE  regexp_like(lower(table_name), 'opus|ipreo|ob_|ecm|dcm|tranche|syndicate|order')
ORDER  BY 2, 3;
SELECT 'dataglobe_s3' AS cat_, table_schema, table_name
FROM   dataglobe_s3.information_schema.tables
WHERE  regexp_like(lower(table_name), 'opus|ipreo|ob_|ecm|dcm|tranche|syndicate|order')
ORDER  BY 2, 3;
SELECT 'bds_iceberg_ref' AS cat_, table_schema, table_name
FROM   bds_iceberg_ref.information_schema.tables
WHERE  regexp_like(lower(table_name), 'opus|ipreo|ob_|ecm|dcm|tranche|syndicate|order')
ORDER  BY 2, 3;

-- SB11/SB12 partial (2026-11-25): bds_iceberg_ref ALREADY HOLDS DATA PRODUCTS —
-- schema dp_deal_execution_ecm_orders (dataset ds_ecm_orders) and
-- dp_wallet_external (ds_external_dealbankcompanytranche); bds_views holds
-- Starburst ports of the OPUS base views (sb_opus_transaction_vw,
-- sb_opus_transaction_related_parties_vw, entitlements ...); dataglobe_iceberg
-- holds dealogic tranche attributes + opus dms entitlement. Convention: schema
-- dp_<product>, dataset ds_<name>. opus (MongoDB) = app databases, not ours.
-- STILL MISSING: SB11 for ecm_history_data_iceberg, ecm_history_data,
-- dataglobe_s3, dataglobe, ecm, dcm and SB12 for the first three (result or error).

-- SB16 partial + SB13/SB14 answered (2026-11-25):
-- * Catalog ecm_history_data_iceberg (assumed: schema ecm_data_iceberg) holds
--   the DG tables as *_HIST (every version): ob_ecm_order(_ioi/_allocation/
--   _book_*/_shared_*)_hist, ob_ecm_trade_book_*_hist, opus_ecm_transaction(_
--   status/_issuer_*/_document)_hist, opus_ecm_transaction_tranche(_syndicate/
--   _stabilization/_product_detail(_identifier)/_demand_currency/_fee_comment)
--   _hist. The screenshot STARTS at ob_ecm_order_allocation_hist — rows sorting
--   before it (equity_*, ipreo_*, ob_deal_*) were not in the shot.
-- * ds_ecm_orders (33,616 rows) = SECURITY DEFINER view over
--   ecm.ecmo_onebook.ecmo_orders — the LIVE OneBook MongoDB, nested columns
--   (orderioi array(row(ioiQty, limitValue, limitType)), investordetails
--   row(_id, name, type, gpnum, region)); no allocation, no deal fields.
--   NOT A SOURCE (user 2026-11-25): we never read live Mongo. The live catalog
--   will carry exactly the DGSTREAM tables, shared by all data products.

-- SB16b. The top of the same list (everything sorting before
--        ob_ecm_order_allocation_hist) — DCM (ob_deal_*, ob_order*), Ipreo
--        and opus_base tables would sit here if they were migrated.
SELECT table_schema, table_name
FROM   ecm_history_data_iceberg.information_schema.tables
WHERE  table_schema <> 'information_schema'
  AND  table_name < 'ob_ecm_order_allocation_hist'
ORDER  BY 1, 2;

-- SB16c. The Hive twin (did not come back): same question.
SELECT table_schema, table_name
FROM   ecm_history_data.information_schema.tables
WHERE  table_schema <> 'information_schema'
ORDER  BY 1, 2;

-- SB17. COLUMN NAMES of the six tables ds_deal_summary reads. Publishing failed
--       2026-11-25 with "Column 'x.ecm_transaction_id' cannot be resolved" on
--       opus_ecm_transaction_hist: the migrated names differ from DGSTREAM.
--       Screenshot every column of each (scroll the long ones).
DESCRIBE ecm_history_data_iceberg.ecm_data_iceberg.opus_ecm_transaction_hist;
DESCRIBE ecm_history_data_iceberg.ecm_data_iceberg.opus_ecm_transaction_status_hist;
DESCRIBE ecm_history_data_iceberg.ecm_data_iceberg.opus_ecm_transaction_tranche_hist;
DESCRIBE ecm_history_data_iceberg.ecm_data_iceberg.opus_ecm_transaction_tranche_demand_currency_hist;
DESCRIBE ecm_history_data_iceberg.ecm_data_iceberg.ob_ecm_order_hist;
DESCRIBE ecm_history_data_iceberg.ecm_data_iceberg.ob_ecm_order_ioi_hist;

-- SB17b. Faster alternative to the six DESCRIBEs: one list, every column.
SELECT table_name, ordinal_position, column_name, data_type
FROM   ecm_history_data_iceberg.information_schema.columns
WHERE  table_schema = 'ecm_data_iceberg'
  AND  table_name IN ('opus_ecm_transaction_hist', 'opus_ecm_transaction_status_hist',
                      'opus_ecm_transaction_tranche_hist', 'opus_ecm_transaction_tranche_demand_currency_hist',
                      'ob_ecm_order_hist', 'ob_ecm_order_ioi_hist')
ORDER  BY table_name, ordinal_position;

-- SB17c. ONE-SCREEN key map (run this first; SB17b is the full list). The order
--        table answered 2026-11-25: DGSTREAM _HIST names kept (uuid first), almost
--        every column varchar (the query now try_casts numbers / dates / versions).
--        Still unknown: the transaction key of opus_ecm_transaction_hist (no
--        ecm_transaction_id) and whether dg_version / dg_updated_ts exist.
SELECT table_name, column_name, data_type
FROM   ecm_history_data_iceberg.information_schema.columns
WHERE  table_schema = 'ecm_data_iceberg'
  AND  table_name IN ('opus_ecm_transaction_hist', 'opus_ecm_transaction_status_hist',
                      'opus_ecm_transaction_tranche_hist',
                      'opus_ecm_transaction_tranche_demand_currency_hist',
                      'ob_ecm_order_ioi_hist')
  AND  regexp_like(column_name, 'id$|version|^dg_|status|currency')
ORDER  BY table_name, column_name;

-- SB17c answered 2026-11-25: opus_ecm_transaction_hist has NO ecm_transaction_id
-- and NO dg_version (keys: deal_transaction_id, dg_entity_id, dg_event_id); status /
-- tranche / demand_currency have ecm_transaction_id decimal(38,0) + dg_version
-- decimal(20,0); ob_ecm_order_ioi_hist has only dg_created/updated_ts. ds_deal_summary
-- now keys the transaction on dg_entity_id (ASSUMED = ecm_transaction_id, SB19 checks).

-- SB19a/b answered 2026-11-25: dg_entity_id IS the ecm_transaction_id (49,016 of
-- 49,020 entities match status rows; values are plain numbers, e.g. 7840).
-- deals_ 49,113 > entities_ 49,020: ~93 transactions changed deal_transaction_id
-- across versions — the latest-version pick takes the current one.

-- SB19c answered 2026-11-25: all 38 columns ds_deal_summary reads exist, with real
-- numeric / timestamp types (deal_size decimal(38,4), demand_qty / ioi_qty
-- decimal(38,6), private_alloc decimal(38,0), prices decimal(38,8), *_ts
-- timestamp(6)); ids and flags are varchar.

-- SB18. Versions: rows vs distinct tranches, and how fresh the copy is.
SELECT count(*) AS rows_,
       count(DISTINCT ecm_transaction_tranche_id) AS tranches_,
       max(dg_version) AS max_version_,
       max(dg_updated_ts) AS last_update_
FROM   ecm_history_data_iceberg.ecm_data_iceberg.opus_ecm_transaction_tranche_hist;

-- SB15. Where the OPUS base data comes from in Starburst.
SHOW CREATE VIEW bds_iceberg_ref.bds_views.sb_opus_transaction_vw;

-- AFTER SB11-SB12 (fill in one real catalog.schema.table from the results):
-- SB7. SHOW CREATE TABLE <catalog>.<schema>.<table>;
-- SB8. SELECT grantee, table_schema, table_name, privilege_type
--      FROM <catalog>.information_schema.table_privileges ORDER BY 2, 3, 4;
-- SB9. SELECT count(*), max(dg_updated_ts), max(dg_version)
--      FROM <catalog>.<schema>.opus_ecm_transaction_tranche;

-- SB20. Deal Execution data products (live OneBook MongoDB) — the queries live in
-- starburst/DEAL-EXECUTION-PRODUCTS.md (steps 1-3), at the user's request 2026-11-25.
