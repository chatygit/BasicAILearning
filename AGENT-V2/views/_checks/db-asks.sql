-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- AG / AH answered (UAT 2026-10-19): DEMAND_QTY is never the sum; the 1,566
-- 'other' scaled orders are CURRENCY / PERCENT bids where DEMAND_QTY is the
-- share-equivalent — correct. The ladder now shows the bid's unit and decimals.

-- ===========================================================================
-- SB. STARBURST INVENTORY (run in STARBURST, Trino SQL — not Oracle). Maps the
-- Iceberg landing area before we port the nine views. Read-only metadata.
-- ===========================================================================

-- SB1. Every schema and its table count in the candidate catalogs.
SELECT table_cat, table_schem, count(*) AS tables_
FROM   system.jdbc.tables
WHERE  table_cat IN ('dataglobe_s3', 'dcm', 'ecm', 'dealogic', 'dms', 'dsi')
  AND  table_schem <> 'information_schema'
GROUP  BY 1, 2
ORDER  BY 1, 2;

-- SB2. Which of the 38 DG tables our views read already exist anywhere in
--      Starburst outside the Oracle catalog, and where.
SELECT table_cat, table_schem, table_name
FROM   system.jdbc.tables
WHERE  table_cat <> 'bds_dg_oraas'
  AND  lower(table_name) IN (
    'ipreo_issue',
    'ipreo_ob_ecm_order',
    'ipreo_ob_ecm_order_ioi',
    'ipreo_opus_ecm_transaction',
    'ipreo_opus_ecm_transaction_status',
    'ipreo_opus_ecm_transaction_tranche',
    'ipreo_opus_ecm_transaction_tranche_product_detail',
    'ipreo_opus_ecm_transaction_tranche_syndicate',
    'ipreo_order',
    'ipreo_orderioi',
    'ipreo_product',
    'ipreo_productfee',
    'ipreo_tranche',
    'ob_deal_issuer',
    'ob_deal_tranche',
    'ob_ecm_order',
    'ob_ecm_order_ioi',
    'ob_ecm_trade_book_designation',
    'ob_ecm_trade_book_investor_trade',
    'ob_hedge_order',
    'ob_hedge_trade',
    'ob_order',
    'ob_order_match_group',
    'ob_order_size',
    'ob_order_trade',
    'ob_order_trade_syndicate',
    'ob_tranche',
    'ob_tranche_rating',
    'ob_tranche_syndicate_member',
    'opus_base_transaction',
    'opus_base_transaction_related_parties',
    'opus_ecm_transaction',
    'opus_ecm_transaction_status',
    'opus_ecm_transaction_tranche',
    'opus_ecm_transaction_tranche_demand_currency',
    'opus_ecm_transaction_tranche_product_detail',
    'opus_ecm_transaction_tranche_product_detail_identifier',
    'opus_ecm_transaction_tranche_syndicate')
ORDER  BY table_name, table_cat;

-- SB3. What dataglobe_s3 holds (all tables, with the connector's table type).
SELECT table_schema, table_name, table_type
FROM   dataglobe_s3.information_schema.tables
WHERE  table_schema <> 'information_schema'
ORDER  BY 1, 2;

-- SB4. One table's DDL: shows the format (Iceberg / Parquet), partitioning and
--      column types. Put the first table name from SB3 in.
-- SHOW CREATE TABLE dataglobe_s3.dg_s3_reference.<table_from_SB3>;

-- AN. IPREO PERCENT BIDS (UAT, one statement). PR bot 2026-10-27: is a non-zero
-- IOI_QTY on a PERCENT bid a converted SHARE count or the raw percentage (10 for
-- a 10% order)? Percent bids are excluded from Ipreo demand until this answers.
SELECT CASE WHEN I.IOI_QTY = 0 THEN '0 (never converted)'
            WHEN I.IOI_QTY <= 100 THEN '0 < qty <= 100 (looks like a percentage)'
            ELSE '> 100 (looks like shares)' END AS BUCKET,
       COUNT(*) AS ORDERS_, MIN(I.IOI_QTY) AS MIN_, MAX(I.IOI_QTY) AS MAX_
FROM   DGSTREAM.IPREO_OB_ECM_ORDER O
JOIN   (SELECT ORDER_ID, MAX(IOI_QTY) AS IOI_QTY FROM DGSTREAM.IPREO_OB_ECM_ORDER_IOI GROUP BY ORDER_ID) I
       ON I.ORDER_ID = O.ORDER_ID
WHERE  O.IOI_UNIT = 'PERCENT'
GROUP  BY CASE WHEN I.IOI_QTY = 0 THEN '0 (never converted)'
               WHEN I.IOI_QTY <= 100 THEN '0 < qty <= 100 (looks like a percentage)'
               ELSE '> 100 (looks like shares)' END;

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
