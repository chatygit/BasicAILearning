-- ===========================================================================
-- CURRENCY UNMAPPED-ID CHECK — run in BOTH QA and PROD before deciding on a
-- view change. 2026-08-14: a deal card showed "Currencies: 1 | 4" — the deal
-- view's ECM currency fix falls back to the raw internal id when
-- TRANCHE_DEMAND_CURRENCY has no CURRENCY_NAME row. Presentation doctrine now
-- renders numeric tokens as "not recorded", so users never see ids; this
-- check decides whether the DATA needs fixing too. If PROD returns 0 deals,
-- QA seed data is the whole population and NO view change is warranted.
-- ===========================================================================

-- Q1 — blast radius: how many ECM deals carry at least one unmapped token.
SELECT COUNT(DISTINCT DEAL_ID) AS DEALS_WITH_UNMAPPED,
       COUNT(*)                AS ROWS_WITH_UNMAPPED
FROM   DGSTREAM.VW_DEAL_SUMMARY
WHERE  PRODUCT = 'ECM'
AND    REGEXP_LIKE(CURRENCIES, '(^|\| )[0-9]+( \||$)');

-- Q2 — the distinct unmapped id tokens themselves (what would need mapping).
SELECT DISTINCT REGEXP_SUBSTR(CURRENCIES, '[0-9]+', 1, LEVEL) AS UNMAPPED_ID
FROM   DGSTREAM.VW_DEAL_SUMMARY
WHERE  PRODUCT = 'ECM'
AND    REGEXP_LIKE(CURRENCIES, '(^|\| )[0-9]+( \||$)')
CONNECT BY REGEXP_SUBSTR(CURRENCIES, '[0-9]+', 1, LEVEL) IS NOT NULL
       AND PRIOR DEAL_ID = DEAL_ID
       AND PRIOR SYS_GUID() IS NOT NULL
ORDER  BY 1;

-- Q3 — sample rows for eyeballing (deal + the full currency list).
SELECT DEAL_ID, DEAL_NAME, CURRENCIES
FROM   DGSTREAM.VW_DEAL_SUMMARY
WHERE  PRODUCT = 'ECM'
AND    REGEXP_LIKE(CURRENCIES, '(^|\| )[0-9]+( \||$)')
FETCH FIRST 20 ROWS ONLY;

-- Q4 (THE DECIDER between data-gap and view-improvement) — do the unmapped
-- ids have names ANYWHERE in the demand-currency table? The view's lookup is
-- keyed per (transaction, tranche, currency) triple; a name existing under
-- ANY other row means a GLOBAL id->name second fallback in the view would
-- resolve these (NVL(TDC.name, NVL(global.name, id))) — a view-batch item
-- that would matter in PROD too. No rows at all = the ids exist nowhere =
-- QA seed junk; presentation doctrine already covers it, close the topic.
-- QA 2026-08-14 unmapped set: 1, 2, 3, 4, 7, 67, 76, 139.
SELECT CURRENCY_ID,
       MAX(CURRENCY_NAME) AS KNOWN_NAME,
       COUNT(*)           AS ROWS_
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY
WHERE  CURRENCY_ID IN ('1','2','3','4','7','67','76','139')
GROUP  BY CURRENCY_ID
ORDER  BY 1;
