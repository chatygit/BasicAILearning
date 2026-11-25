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
-- SB. STARBURST DEV ACCESS MAP (Trino SQL, run in the STARBURST editor, DEV).
-- Not Oracle: in SQL Developer these fail with ORA-00933. Read-only metadata,
-- no CREATE / INSERT. One round: run top to bottom, screenshot each result.
-- If a statement fails naming a catalog you are not authorised for, add that
-- catalog to the NOT IN list of SB4 / SB5 and re-run just that statement.
-- ===========================================================================

-- SB1. Who Starburst thinks you are.
SELECT current_user AS user_, current_groups() AS groups_;

-- SB2. Your roles.
SHOW CURRENT ROLES;

-- SB3. Every catalog you can see, and what kind it is (iceberg / hive /
--      oracle / ...). The ECM, DCM and OPUS buckets should appear here.
SELECT catalog_name, connector_name FROM system.metadata.catalogs ORDER BY 1;

-- SB4. Schemas and table counts per catalog you can read.
SELECT table_cat, table_schem, count(*) AS tables_
FROM   system.jdbc.tables
WHERE  table_cat NOT IN ('system', 'wl_sb_lds')
  AND  table_schem <> 'information_schema'
GROUP  BY 1, 2
ORDER  BY 1, 2;

-- SB5. Where the 38 tables our views read live today (any catalog, any schema).
SELECT table_cat, table_schem, table_name, table_type
FROM   system.jdbc.tables
WHERE  table_cat NOT IN ('system', 'wl_sb_lds')
  AND  lower(table_name) IN (
    'ipreo_issue', 'ipreo_ob_ecm_order', 'ipreo_ob_ecm_order_ioi',
    'ipreo_opus_ecm_transaction', 'ipreo_opus_ecm_transaction_status',
    'ipreo_opus_ecm_transaction_tranche', 'ipreo_opus_ecm_transaction_tranche_product_detail',
    'ipreo_opus_ecm_transaction_tranche_syndicate', 'ipreo_order', 'ipreo_orderioi',
    'ipreo_product', 'ipreo_productfee', 'ipreo_tranche',
    'ob_deal_issuer', 'ob_deal_tranche', 'ob_ecm_order', 'ob_ecm_order_ioi',
    'ob_ecm_trade_book_designation', 'ob_ecm_trade_book_investor_trade',
    'ob_hedge_order', 'ob_hedge_trade', 'ob_order', 'ob_order_match_group',
    'ob_order_size', 'ob_order_trade', 'ob_order_trade_syndicate', 'ob_tranche',
    'ob_tranche_rating', 'ob_tranche_syndicate_member',
    'opus_base_transaction', 'opus_base_transaction_related_parties',
    'opus_ecm_transaction', 'opus_ecm_transaction_status', 'opus_ecm_transaction_tranche',
    'opus_ecm_transaction_tranche_demand_currency',
    'opus_ecm_transaction_tranche_product_detail',
    'opus_ecm_transaction_tranche_product_detail_identifier',
    'opus_ecm_transaction_tranche_syndicate', 'opus_ecm_transaction_tranche_stabilization')
ORDER  BY table_name, table_cat;

-- SB6. Anything that looks like ours under another name (Iceberg landings
--      sometimes rename or prefix tables).
SELECT table_cat, table_schem, table_name
FROM   system.jdbc.tables
WHERE  table_cat NOT IN ('system', 'wl_sb_lds')
  AND  regexp_like(lower(table_name), 'opus|ipreo|ecm|dcm|orderbook|ob_order|ob_deal|tranche|syndicate')
ORDER  BY 1, 2, 3;

-- AFTER SB3-SB6 (fill in the catalog / schema / table they show; one each):
-- SB7. Table format, partitioning, column types of one landed table:
--   SHOW CREATE TABLE <catalog>.<schema>.<table>;
-- SB8. What you may do in a catalog (SELECT only, or also CREATE / INSERT):
--   SELECT grantee, table_schema, table_name, privilege_type
--   FROM   <catalog>.information_schema.table_privileges
--   WHERE  grantee = current_user ORDER BY 2, 3, 4;
-- SB9. Freshness and versions of one landed table vs Oracle (row count, latest
--      update, versions per key):
--   SELECT count(*), max(dg_updated_ts), max(dg_version),
--          count(*) - count(DISTINCT ecm_transaction_tranche_id) AS extra_version_rows
--   FROM   <catalog>.<schema>.opus_ecm_transaction_tranche;
