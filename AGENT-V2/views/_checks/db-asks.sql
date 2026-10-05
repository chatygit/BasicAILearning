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

-- ===========================================================================
-- P. BATCH C — BANKER FILTERS (UAT, BEFORE the deploy). P0 validates every
-- source column name the three new view files use (the "one errores" guard);
-- P1-P6 census the vocabularies the catalogs cannot describe yet. SELECTs only.
-- ===========================================================================

-- P0. NAME VALIDATION — expect 21 rows from the three OPUS / OB tables. Fewer
--     = a name is wrong, do NOT deploy. The IPREO_* rows (if any) tell us what
--     the mirrors carry — those branches are NULL stubs until then.
SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM'
AND   ((TABLE_NAME = 'OPUS_ECM_TRANSACTION'
        AND COLUMN_NAME IN ('PRODUCT_EQUITY_CLASS_VALUE', 'ISSUER_COUNTRY_NAME'))
    OR (TABLE_NAME = 'OPUS_ECM_TRANSACTION_TRANCHE'
        AND COLUMN_NAME IN ('BASE_PRIMARY_SHARES', 'BASE_SECONDARY_SHARES',
                            'LAST_TRADE_PRICE_BEFORE_OFFER', 'LAST_TRADE_PRICE_BEFORE_LAUNCH',
                            'INITIAL_DEAL_AMOUNT', 'FINAL_TRANCHE_OFFER_AMOUNT'))
    OR (TABLE_NAME = 'OB_DEAL_TRANCHE'
        AND COLUMN_NAME IN ('DEAL_PRODUCT_TYPE_LIST', 'SMC_ISSUER_COUNTRY',
                            'SMC_ISSUER_COUNTRY_OF_RISK', 'CALL_IND', 'CALL_DATE',
                            'NON_CALL_PERIOD', 'PUT_IND', 'MAKE_WHOLE_CALLABLE', 'IS_TAP',
                            'PERPETUAL_MATURITY', 'IS_CONVERTIBLE', 'GOVERNING_LAW',
                            'EXCHANGE_LISTING_VENUE'))
    OR (TABLE_NAME IN ('IPREO_OPUS_ECM_TRANSACTION', 'IPREO_OPUS_ECM_TRANSACTION_TRANCHE')
        AND COLUMN_NAME IN ('PRODUCT_EQUITY_CLASS_VALUE', 'ISSUER_COUNTRY_NAME',
                            'BASE_PRIMARY_SHARES', 'BASE_SECONDARY_SHARES',
                            'LAST_TRADE_PRICE_BEFORE_OFFER', 'INITIAL_DEAL_AMOUNT',
                            'FINAL_TRANCHE_OFFER_AMOUNT')))
ORDER  BY TABLE_NAME, COLUMN_NAME;

-- P1. DCM flag vocabularies (one statement, six small scans of OB_DEAL_TRANCHE).
SELECT 'CALL_IND' AS COL, CALL_IND AS VAL, COUNT(*) AS ROWS_ FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY CALL_IND
UNION ALL SELECT 'PUT_IND', PUT_IND, COUNT(*) FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY PUT_IND
UNION ALL SELECT 'MAKE_WHOLE_CALLABLE', MAKE_WHOLE_CALLABLE, COUNT(*) FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY MAKE_WHOLE_CALLABLE
UNION ALL SELECT 'IS_TAP', IS_TAP, COUNT(*) FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY IS_TAP
UNION ALL SELECT 'PERPETUAL_MATURITY', PERPETUAL_MATURITY, COUNT(*) FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY PERPETUAL_MATURITY
UNION ALL SELECT 'IS_CONVERTIBLE', IS_CONVERTIBLE, COUNT(*) FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY IS_CONVERTIBLE
ORDER  BY 1, 3 DESC;

-- P2. DCM text vocabularies — top 15 each (NULL counts as a row).
SELECT * FROM (SELECT 'GOVERNING_LAW' AS COL, GOVERNING_LAW AS VAL, COUNT(*) AS ROWS_
               FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY GOVERNING_LAW ORDER BY 3 DESC FETCH FIRST 15 ROWS ONLY)
UNION ALL
SELECT * FROM (SELECT 'EXCHANGE_LISTING_VENUE', EXCHANGE_LISTING_VENUE, COUNT(*)
               FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY EXCHANGE_LISTING_VENUE ORDER BY 3 DESC FETCH FIRST 15 ROWS ONLY)
UNION ALL
SELECT * FROM (SELECT 'NON_CALL_PERIOD', NON_CALL_PERIOD, COUNT(*)
               FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY NON_CALL_PERIOD ORDER BY 3 DESC FETCH FIRST 15 ROWS ONLY)
UNION ALL
SELECT * FROM (SELECT 'SMC_ISSUER_COUNTRY', SMC_ISSUER_COUNTRY, COUNT(*)
               FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY SMC_ISSUER_COUNTRY ORDER BY 3 DESC FETCH FIRST 15 ROWS ONLY);

-- P3. ECM tranche populations for the six new numeric columns (raw rows).
SELECT COUNT(*) AS ROWS_,
       COUNT(BASE_PRIMARY_SHARES) AS PRIMARY_,
       COUNT(BASE_SECONDARY_SHARES) AS SECONDARY_,
       COUNT(LAST_TRADE_PRICE_BEFORE_OFFER) AS LAST_CLOSE_OFFER,
       COUNT(LAST_TRADE_PRICE_BEFORE_LAUNCH) AS LAST_CLOSE_LAUNCH,
       COUNT(INITIAL_DEAL_AMOUNT) AS INITIAL_AMT,
       COUNT(FINAL_TRANCHE_OFFER_AMOUNT) AS OFFER_AMT
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE;

-- P4. OFFERING_FORMAT vocabulary (already projected on the deal view, never
--     censused) and the deal class once more, by source.
SELECT 'OFFERING_FORMAT' AS COL, OFFERING_FORMAT AS VAL, COUNT(*) AS ROWS_
FROM   DGSTREAM.OPUS_ECM_TRANSACTION GROUP BY OFFERING_FORMAT
UNION ALL
SELECT 'PRODUCT_EQUITY_CLASS_VALUE', PRODUCT_EQUITY_CLASS_VALUE, COUNT(*)
FROM   DGSTREAM.OPUS_ECM_TRANSACTION GROUP BY PRODUCT_EQUITY_CLASS_VALUE
ORDER  BY 1, 3 DESC;

-- P5 (OPTIONAL). Citi's DCM role lead: SFC_ROLE × CO_MANAGED_DEAL values.
SELECT SFC_ROLE, CO_MANAGED_DEAL, COUNT(*) AS ROWS_
FROM   DGSTREAM.OB_DEAL_TRANCHE
GROUP  BY SFC_ROLE, CO_MANAGED_DEAL
ORDER  BY 3 DESC FETCH FIRST 20 ROWS ONLY;
