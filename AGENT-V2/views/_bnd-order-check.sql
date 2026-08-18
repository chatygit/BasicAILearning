-- ===========================================================================
-- ORDER-LEVEL B&D CHECK — is "billed by" truly per-order in the source?
-- 2026-08-18. Business doctrine (V1 glossary) says B&D bills/settles an
-- ORDER; our views carry the designation at TRANCHE level only (BND_BANK
-- pipe list), and Q25 measured 850 ECM tranches with MORE THAN ONE flagged
-- B&D member — where "which bank billed this order" is unanswerable today.
-- OB_ORDER carries a per-order BND column the views never surfaced. These
-- queries decide whether the order-view round-2 denorm should pull it as the
-- true order-level "billed by".
-- ===========================================================================

-- Q1 — what does BND hold? (bank names? codes? flags? junk?)
SELECT BND, COUNT(*) AS ORDERS_
FROM   DGSTREAM.OB_ORDER
GROUP  BY BND
ORDER  BY ORDERS_ DESC
FETCH FIRST 30 ROWS ONLY;

-- Q2 — population: how many orders carry it at all?
SELECT COUNT(*)                                      AS ALL_ORDERS,
       COUNT(BND)                                    AS WITH_BND,
       ROUND(100 * COUNT(BND) / COUNT(*), 1)         AS PCT_WITH_BND
FROM   DGSTREAM.OB_ORDER;

-- Q3 (THE DECIDER) — does BND VARY across orders of one tranche? Varying =
-- genuine order-level attribution (gold: the 850-tranche ambiguity dies).
-- Constant per tranche = it mirrors the tranche designation (still useful,
-- but no new information).
SELECT COUNT(*) AS TRANCHES_WITH_BND_ORDERS,
       SUM(CASE WHEN DISTINCT_BNDS > 1 THEN 1 ELSE 0 END) AS TRANCHES_WHERE_BND_VARIES
FROM (
    SELECT O.TRANCHE_ID, COUNT(DISTINCT S.BND) AS DISTINCT_BNDS
    FROM   DGSTREAM.OB_ORDER S
    JOIN   DGSTREAM.VW_ORDER_DETAIL O ON O.ORDER_ID = S.ORDER_ID
    WHERE  S.BND IS NOT NULL
    GROUP  BY O.TRANCHE_ID
);

-- Q4 — eyeball: a few multi-B&D tranches with their orders' BND values,
-- side by side with the tranche-level designation list.
SELECT O.TRANCHE_ID, T.BND_BANK AS TRANCHE_DESIGNATION,
       S.BND AS ORDER_BND, COUNT(*) AS ORDERS_
FROM   DGSTREAM.OB_ORDER S
JOIN   DGSTREAM.VW_ORDER_DETAIL O   ON O.ORDER_ID = S.ORDER_ID
JOIN   DGSTREAM.VW_TRANCHE_SUMMARY T ON T.TRANCHE_ID = O.TRANCHE_ID
                                     AND T.PRODUCT = O.PRODUCT
WHERE  S.BND IS NOT NULL
AND    T.BND_BANK LIKE '%|%'
GROUP  BY O.TRANCHE_ID, T.BND_BANK, S.BND
ORDER  BY O.TRANCHE_ID
FETCH FIRST 40 ROWS ONLY;

-- Q5 — the product split: is BND a DCM-side fact? (Q4 returned 0 rows: no
-- multi-B&D ECM tranche has BND-carrying orders, suggesting ECM orders
-- largely lack BND and the 3.7M populated values are DCM.)
SELECT O.PRODUCT,
       COUNT(*)                              AS ORDERS_,
       COUNT(S.BND)                          AS WITH_BND,
       ROUND(100 * COUNT(S.BND) / COUNT(*), 1) AS PCT_WITH_BND
FROM   DGSTREAM.OB_ORDER S
JOIN   DGSTREAM.VW_ORDER_DETAIL O ON O.ORDER_ID = S.ORDER_ID
GROUP  BY O.PRODUCT;
