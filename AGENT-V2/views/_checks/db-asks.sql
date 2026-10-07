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

-- UAT FULL CHECK 2026-10-07: everything PASS except D01 (ECM order grain —
-- rows > distinct ORDER_ID on the ECM branches). Diagnose before any view
-- change. Two statements, one scan each of the ECM order branches (~12 s).

-- W1. Shape of the duplicates: how many order ids repeat, and whether they
--     repeat ACROSS the two ECM sources (OPUS 8-char ids vs Ipreo 10-digit
--     deal ids), across deals, or across tranches of one deal.
SELECT COUNT(*) AS DUP_ORDER_IDS,
       SUM(ROWS_) - COUNT(*) AS EXTRA_ROWS,
       SUM(CASE WHEN SOURCES = 2 THEN 1 ELSE 0 END) AS IN_BOTH_SOURCES,
       SUM(CASE WHEN DEALS > 1 THEN 1 ELSE 0 END) AS ACROSS_DEALS,
       SUM(CASE WHEN DEALS = 1 AND TRANCHES > 1 THEN 1 ELSE 0 END) AS SAME_DEAL_SEVERAL_TRANCHES,
       SUM(CASE WHEN DEALS = 1 AND TRANCHES = 1 THEN 1 ELSE 0 END) AS SAME_DEAL_SAME_TRANCHE
FROM (
    SELECT ORDER_ID, COUNT(*) AS ROWS_,
           COUNT(DISTINCT DEAL_ID) AS DEALS,
           COUNT(DISTINCT DEAL_ID || '~' || TRANCHE_ID) AS TRANCHES,
           COUNT(DISTINCT CASE WHEN REGEXP_LIKE(DEAL_ID, '^[0-9]{10}$') THEN 'IPREO' ELSE 'OPUS' END) AS SOURCES
    FROM   DGSTREAM.VW_ORDER_DETAIL
    WHERE  PRODUCT = 'ECM'
    GROUP  BY ORDER_ID
    HAVING COUNT(*) > 1
);

-- W2. Ten of them, with every row they produce (deal, tranche, investor,
--     figures) — the pattern is usually obvious from the ids.
SELECT V.ORDER_ID, V.DEAL_ID, V.TRANCHE_ID, V.TRANCHE_NAME, V.INVESTOR_NAME,
       V.ORDER_DEMAND_QTY, V.ORDER_ALLOCATION, TO_CHAR(V.PRICING_TS, 'YYYY-MM-DD') AS PRICED
FROM   DGSTREAM.VW_ORDER_DETAIL V
JOIN   (SELECT ORDER_ID FROM DGSTREAM.VW_ORDER_DETAIL WHERE PRODUCT = 'ECM'
        GROUP BY ORDER_ID HAVING COUNT(*) > 1 FETCH FIRST 10 ROWS ONLY) D
       ON D.ORDER_ID = V.ORDER_ID
WHERE  V.PRODUCT = 'ECM'
ORDER  BY V.ORDER_ID, V.DEAL_ID, V.TRANCHE_ID;

-- ===========================================================================
-- X. IPREO PRODUCT_TYPE SOURCE (UAT). Defect item 6 (2026-10-07): product_type
-- is set from the deal's equity type but expected from securityType. That is
-- our tranche view's Ipreo branch (TPD.EQUITY_TYPE AS PRODUCT_TYPE; the OPUS
-- branch already uses SECURITY_TYPE_NAME). Deploy-check C11 now FAILS on it by
-- design. Two statements pick the replacement source.
-- ===========================================================================

-- X1. Does the Ipreo product-detail mirror carry a security-type column?
SELECT COLUMN_ID, COLUMN_NAME, DATA_TYPE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'IPREO_OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL'
ORDER  BY COLUMN_ID;

-- X2. The raw alternative: IPREO_PRODUCT.SEC_TYPE_CD through the tranche's
--     DEFAULT_PRD_ID — coverage and vocabulary on Ipreo tranches.
SELECT P.SEC_TYPE_CD, COUNT(*) AS TRANCHES
FROM   DGSTREAM.IPREO_TRANCHE T
LEFT JOIN (SELECT PRD_ID, MAX(SEC_TYPE_CD) AS SEC_TYPE_CD FROM DGSTREAM.IPREO_PRODUCT GROUP BY PRD_ID) P
       ON P.PRD_ID = T.DEFAULT_PRD_ID
GROUP  BY P.SEC_TYPE_CD
ORDER  BY TRANCHES DESC;

-- ===========================================================================
-- Y. IPREO ISSUER NAME SOURCE (UAT). Defect item 3 (2026-10-07): issuer_name
-- is a copy of deal_name. On the Ipreo deal branch that is by construction
-- (deal name with the tranche parenthetical stripped; the mirror gave us no
-- issuer). Two statements find a real source. Deploy-check B15 / B16 now
-- measure the copy rate per ECM source.
-- ===========================================================================

-- Y1. Which ISSUER_* columns the Ipreo transaction mirror carries (names only).
SELECT COLUMN_ID, COLUMN_NAME, DATA_TYPE
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM' AND TABLE_NAME = 'IPREO_OPUS_ECM_TRANSACTION'
AND    COLUMN_NAME LIKE 'ISSUER%'
ORDER  BY COLUMN_ID;

-- Y2. The ticker route: ISSUER_TICKER on the mirror (validated) looked up in
--     the party master — how many Ipreo deals would get a party name.
SELECT COUNT(*) AS IPREO_DEALS,
       COUNT(ET.ISSUER_TICKER) AS WITH_TICKER,
       COUNT(PM.PARTY_NAME) AS TICKER_IN_PARTY_MASTER,
       COUNT(DISTINCT PM.PARTY_NAME) AS DISTINCT_NAMES
FROM   (SELECT DEAL_TRANSACTION_ID, MAX(ISSUER_TICKER) AS ISSUER_TICKER
        FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION WHERE DEAL_TRANSACTION_ID IS NOT NULL
        GROUP BY DEAL_TRANSACTION_ID) ET
LEFT JOIN (SELECT PARTY_TICKER, MAX(PARTY_NAME) AS PARTY_NAME
           FROM DGSTREAM.OPUS_BASE_TRANSACTION_RELATED_PARTIES
           WHERE PARTY_ROLE = 'Primary Client' AND PARTY_TICKER IS NOT NULL
           GROUP BY PARTY_TICKER) PM
       ON PM.PARTY_TICKER = ET.ISSUER_TICKER;

-- ===========================================================================
-- Z. BROKER CODE → NAME FOR IPREO ORDERS (UAT). Defect (2026-10-07): BILLED_BY
-- is a broker NAME on OPUS orders (O.BILLEDBY_BROKER_CODE holds names on most
-- rows) but a broker CODE on Ipreo orders (RO.BILLED_BY_BRK_CD, e.g. CITIUSA).
-- Deploy-check D14 / D14b now measure it. Three statements find a dictionary.
-- ===========================================================================

-- Z1. The OPUS syndicate table pairs BROKER_CODE with SYNDICATE_MEMBER_NAME —
--     is the code → name mapping one-to-one? (top 60 pairs)
SELECT BROKER_CODE, SYNDICATE_MEMBER_NAME, COUNT(*) AS ROWS_
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
WHERE  BROKER_CODE IS NOT NULL
GROUP  BY BROKER_CODE, SYNDICATE_MEMBER_NAME
ORDER  BY BROKER_CODE, ROWS_ DESC
FETCH FIRST 60 ROWS ONLY;

-- Z2. The Ipreo billed-by codes (top 30 by orders) and whether each resolves
--     through that dictionary.
SELECT V.BILLED_BY, COUNT(*) AS ORDERS_, MAX(D.NAME_) AS OPUS_NAME
FROM   DGSTREAM.VW_ORDER_DETAIL V
LEFT JOIN (SELECT BROKER_CODE, MAX(SYNDICATE_MEMBER_NAME) AS NAME_
           FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
           WHERE BROKER_CODE IS NOT NULL GROUP BY BROKER_CODE) D
       ON D.BROKER_CODE = V.BILLED_BY
WHERE  V.PRODUCT = 'ECM' AND REGEXP_LIKE(V.DEAL_ID, '^[0-9]{10}$') AND V.BILLED_BY IS NOT NULL
GROUP  BY V.BILLED_BY
ORDER  BY ORDERS_ DESC
FETCH FIRST 30 ROWS ONLY;

-- Z3. Do the source tables carry a broker NAME beside the code? (names only)
SELECT TABLE_NAME, COLUMN_NAME
FROM   ALL_TAB_COLUMNS
WHERE  OWNER = 'DGSTREAM'
AND   ((TABLE_NAME = 'OB_ECM_ORDER' AND COLUMN_NAME LIKE 'BILLEDBY%')
    OR (TABLE_NAME IN ('IPREO_ORDER', 'IPREO_OB_ECM_ORDER') AND (COLUMN_NAME LIKE '%BRK%' OR COLUMN_NAME LIKE '%BROKER%')))
ORDER  BY TABLE_NAME, COLUMN_NAME;
