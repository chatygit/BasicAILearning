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
