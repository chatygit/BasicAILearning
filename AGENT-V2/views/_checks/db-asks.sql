-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- AG / AH answered (UAT 2026-10-19): DEMAND_QTY is never the sum; the 1,566
-- 'other' scaled orders are CURRENCY / PERCENT bids where DEMAND_QTY is the
-- share-equivalent — correct. The ladder now shows the bid's unit and decimals.

-- ===========================================================================
-- AL. VALIDATE THE TEAMMATE'S IPREO CHANGES (UAT, before deploying them).
-- Applied in the repo 2026-10-23: issuer-name regex (3 views), Ipreo demand =
-- ROUND(IOI_QTY) for EVERY unit (deal + order views), investor-name
-- normalisation (CN), billed-by names from DGLOBE.CMNSYNDREF_EXTERNAL_BROKER (EB).
-- ===========================================================================

-- AL1. The new cross-schema table: real column names, and whether DGSTREAM may
--      read it WITH GRANT OPTION (the views are granted on to roles; without
--      it the deploy fails with ORA-01720). An empty grant result only means
--      your account cannot see DGSTREAM's grants — then ask the DBA.
SELECT COLUMN_NAME, DATA_TYPE FROM ALL_TAB_COLUMNS
WHERE  OWNER = 'DGLOBE' AND TABLE_NAME = 'CMNSYNDREF_EXTERNAL_BROKER'
AND    COLUMN_NAME IN ('EXTERNAL_BROKER_CODE', 'EXTERNAL_BROKER_NAME', 'PRODUCT', 'IS_ACTIVE',
                       'EXTERNAL_BROKER_SOURCE', 'DG_UPDATED_TS');
SELECT GRANTEE, PRIVILEGE, GRANTABLE FROM ALL_TAB_PRIVS
WHERE  TABLE_SCHEMA = 'DGLOBE' AND TABLE_NAME = 'CMNSYNDREF_EXTERNAL_BROKER';

-- AL2. Demand: what IOI_QTY means for each bid unit on the Ipreo mirror. The new
--      rule sums it for EVERY unit; it is only right if IOI_QTY is a share
--      count for CURRENCY / PERCENT / FACE bids too.
SELECT O.IOI_UNIT, COUNT(*) AS ORDERS_,
       MIN(I.IOI_QTY) AS MIN_QTY, ROUND(MEDIAN(I.IOI_QTY)) AS MEDIAN_QTY, MAX(I.IOI_QTY) AS MAX_QTY,
       ROUND(MEDIAN(R.IOI_AMT)) AS MEDIAN_AMT_AS_ENTERED
FROM   DGSTREAM.IPREO_OB_ECM_ORDER O
JOIN   (SELECT ORDER_ID, MAX(IOI_QTY) AS IOI_QTY FROM DGSTREAM.IPREO_OB_ECM_ORDER_IOI GROUP BY ORDER_ID) I
       ON I.ORDER_ID = O.ORDER_ID
LEFT JOIN (SELECT ORD_ID, MAX(IOI_AMT) AS IOI_AMT FROM DGSTREAM.IPREO_ORDERIOI GROUP BY ORD_ID) R
       ON R.ORD_ID = TO_NUMBER(O.ORDER_ID DEFAULT NULL ON CONVERSION ERROR)
GROUP  BY O.IOI_UNIT
ORDER  BY ORDERS_ DESC;

-- AL3. Billed-by names: how many Ipreo billed-by codes the reference table
--      resolves, and the top 15 code -> name pairs (CITIUSA should read Citigroup...).
SELECT R.BILLED_BY_BRK_CD AS CODE_, MAX(B.EXTERNAL_BROKER_NAME) AS NAME_, COUNT(*) AS ORDERS_
FROM   DGSTREAM.IPREO_ORDER R
LEFT JOIN DGLOBE.CMNSYNDREF_EXTERNAL_BROKER B
       ON UPPER(TRIM(B.EXTERNAL_BROKER_CODE)) = UPPER(TRIM(R.BILLED_BY_BRK_CD))
WHERE  R.BILLED_BY_BRK_CD IS NOT NULL
GROUP  BY R.BILLED_BY_BRK_CD
ORDER  BY ORDERS_ DESC
FETCH FIRST 15 ROWS ONLY;

-- AL4. Issuer names: Ipreo deal names the new regex changes, 20 before / after
--      pairs — check nothing that is part of a company name gets stripped.
SELECT SYNDICATE_DEAL_NAME AS BEFORE_,
       REGEXP_REPLACE(SYNDICATE_DEAL_NAME, '\s*\(\s*([^)]*TRANCHE[^)]*|COMMON|[^)]*CONVERT[^)]*|BLOCK TRADE|NEW|PIPE|SERIES [A-Z0-9]+)\s*\)\s*$', '', 1, 0, 'i') AS AFTER_
FROM   (SELECT DISTINCT SYNDICATE_DEAL_NAME FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION)
WHERE  REGEXP_REPLACE(SYNDICATE_DEAL_NAME, '\s*\(\s*([^)]*TRANCHE[^)]*|COMMON|[^)]*CONVERT[^)]*|BLOCK TRADE|NEW|PIPE|SERIES [A-Z0-9]+)\s*\)\s*$', '', 1, 0, 'i')
    <> REGEXP_REPLACE(SYNDICATE_DEAL_NAME, '\s*\([^)]*TRANCHE[^)]*\)\s*$', '', 1, 0, 'i')
FETCH FIRST 20 ROWS ONLY;

-- AFTER the deploy (not before): deploy-check A0 + A (A01 43 / A02 89 / A03 73)
-- + D-ECM, and time K3 — the investor-name block (CN) aggregates the whole
-- Ipreo order table on every Ipreo query; K3 was sub-second before.

-- AK answered (UAT 2026-10-23): Source = OB_ECM_ORDER.SOURCE (ONEBOOK = '1B',
-- ISN, CMG, SALES, DA); Indication USD = cash amount / quantity x USD limit;
-- RELATIVE_INDICATION empty. Both now view columns.

-- Deploy vw_order_detail (ladder largest-first, wider number masks,
-- ORDER_SOURCE, INDICATION_USD), then deploy-check A0 + A (A03 = 73) + D-ECM.
