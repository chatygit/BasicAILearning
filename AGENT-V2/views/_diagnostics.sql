-- ===========================================================================
-- VALIDATION SET — proves the REWRITTEN view logic before anyone deploys it
--
-- The views cannot be created yet, so every query below runs the new view
-- body as a plain SELECT. Running one therefore proves two things at once:
--   (a) it COMPILES  — syntax, type resolution, UNION ALL compatibility
--   (b) it is CORRECT — the grain / value assertion in the outer SELECT
--
-- All earlier diagnostics (Q1-Q37) are ANSWERED and recorded in
-- _diagnostics-results.md. Do not re-run them. This file replaces them.
--
-- Cost: [cheap] seconds · [heavy] expect minutes, Q9 took ~11s and Q28 ~79s
--
--   V1-V4   does the rewrite compile, and does it hold grain
--   V5-V6   the gap I could not close from the previous round
--   V7-V9   type outcomes I asserted but never measured
--   V10-V11 blast radius of the MAX() collapse I introduced
--   V12     allocation fix, full population
--   V13     list-column lengths under the new keying
--   V14-V17 ECM issuer name — still open from Q28
--
-- PASS/FAIL is stated under each query. Please send the numbers plus any
-- ORA- error verbatim; a compile error is as useful as a wrong count.
-- ===========================================================================


-- ===========================================================================
-- V1 [heavy] *** THE ONE THAT MATTERS ***
-- The rewritten ECM branch of VW_DEAL_SUMMARY, wrapped in a grain assertion.
-- Old behaviour (Q9b): 22,347 rows for 18,399 deals.
-- PASS = rows_ equals deals_ equals 18,399-ish. Any excess means the
--        GROUP BY did not collapse multi-transaction deals as intended.
-- ===========================================================================
WITH ecm_deal AS (
SELECT
    T.DEAL_TRANSACTION_ID AS DEAL_ID,
    MAX(T.SYNDICATE_DEAL_NAME) AS DEAL_NAME,
    MAX(T.DEAL_SIZE) AS DEAL_SIZE,
    MAX(S.STATUS_VALUE) AS DEAL_STATUS,
    MAX(OBT.DEAL_REGION) AS DEAL_REGION,
    MAX(TR.TRANCHE_COUNT) AS TRANCHE_COUNT,
    MAX(TR.FIRST_PRICED) AS FIRST_PRICED,
    MAX(TR.LAST_PRICED) AS LAST_PRICED,
    MAX(TC.CURRENCIES) AS CURRENCIES,
    MAX(OD.ORDER_COUNT) AS ORDER_COUNT
FROM (
    SELECT X.*
    FROM (
        SELECT ET.*,
               ROW_NUMBER() OVER (PARTITION BY ET.ECM_TRANSACTION_ID
                                  ORDER BY ET.ROWID) AS RN_
        FROM DGSTREAM.OPUS_ECM_TRANSACTION ET
        WHERE ET.DEAL_TRANSACTION_ID IS NOT NULL
    ) X
    WHERE X.RN_ = 1
) T
INNER JOIN (
    SELECT ECM_TRANSACTION_ID,
           MAX(STATUS_VALUE) AS STATUS_VALUE
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_STATUS
    WHERE STATUS_TYPE = 'Execution_Status'
      AND STATUS_VALUE NOT IN ('Confidential', 'Withdrawn', 'Terminated')
    GROUP BY ECM_TRANSACTION_ID
) S
    ON T.ECM_TRANSACTION_ID = S.ECM_TRANSACTION_ID
LEFT JOIN (
    SELECT TRANSACTION_ID, MAX(DEAL_REGION) AS DEAL_REGION
    FROM DGSTREAM.OPUS_BASE_TRANSACTION
    GROUP BY TRANSACTION_ID
) OBT
    ON T.DEAL_TRANSACTION_ID = OBT.TRANSACTION_ID
LEFT JOIN (
    SELECT ET.DEAL_TRANSACTION_ID,
           COUNT(DISTINCT TT.ECM_TRANSACTION_ID || '~' ||
                          TT.ECM_TRANSACTION_TRANCHE_ID) AS TRANCHE_COUNT,
           MIN(TT.PRICING_TS) AS FIRST_PRICED,
           MAX(TT.PRICING_TS) AS LAST_PRICED
    FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TT
    JOIN (SELECT DISTINCT ECM_TRANSACTION_ID, DEAL_TRANSACTION_ID
          FROM DGSTREAM.OPUS_ECM_TRANSACTION) ET
      ON ET.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
    GROUP BY ET.DEAL_TRANSACTION_ID
) TR
    ON TR.DEAL_TRANSACTION_ID = T.DEAL_TRANSACTION_ID
LEFT JOIN (
    SELECT C.DEAL_TRANSACTION_ID,
           LISTAGG(C.TRANCHE_CURRENCY_ID, ' | ')
             WITHIN GROUP (ORDER BY C.TRANCHE_CURRENCY_ID) AS CURRENCIES
    FROM (
        SELECT DISTINCT ET.DEAL_TRANSACTION_ID, TT.TRANCHE_CURRENCY_ID
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TT
        JOIN (SELECT DISTINCT ECM_TRANSACTION_ID, DEAL_TRANSACTION_ID
              FROM DGSTREAM.OPUS_ECM_TRANSACTION) ET
          ON ET.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
    ) C
    GROUP BY C.DEAL_TRANSACTION_ID
) TC
    ON TC.DEAL_TRANSACTION_ID = T.DEAL_TRANSACTION_ID
LEFT JOIN (
    SELECT O.DEAL_ID,
           COUNT(DISTINCT O.ORDER_ID) AS ORDER_COUNT
    FROM DGSTREAM.OB_ECM_ORDER O
    WHERE O.IS_OWNED = 'true'
      AND O.ORDER_STATUS NOT IN ('CANCELLED', 'DELETED', 'PASS')
      AND ((O.IS_MATCHED = 'true' AND O.IS_DOMINANT = 'true') OR O.IS_MATCHED = 'false')
    GROUP BY O.DEAL_ID
) OD
    ON T.DEAL_TRANSACTION_ID = OD.DEAL_ID
GROUP BY T.DEAL_TRANSACTION_ID
)
SELECT COUNT(*)                   AS rows_,
       COUNT(DISTINCT DEAL_ID)    AS deals_,
       SUM(TRANCHE_COUNT)         AS total_tranches,
       MAX(LENGTH(CURRENCIES))    AS max_currencies_len
FROM   ecm_deal;


-- ===========================================================================
-- V2 [cheap] The rewritten DCM currency list, isolated.
-- Old behaviour rendered 'USD | USD | USD' on 6,940 deals (Q21).
-- PASS = zero rows returned. Any row is a currency still repeating.
-- ===========================================================================
SELECT DEAL_ID, CURRENCIES
FROM (
    SELECT C.DEAL_ID,
           LISTAGG(C.CURRENCY, ' | ')
             WITHIN GROUP (ORDER BY C.CURRENCY) AS CURRENCIES
    FROM (
        SELECT DISTINCT DEAL_ID, CURRENCY
        FROM DGSTREAM.OB_DEAL_TRANCHE
        WHERE CURRENCY IS NOT NULL
    ) C
    GROUP BY C.DEAL_ID
)
WHERE REGEXP_LIKE(CURRENCIES, '(^|\| )([A-Za-z]+)( \|.*\| | \| )\2( \||$)')
FETCH FIRST 10 ROWS ONLY;


-- ===========================================================================
-- V3 [heavy] The rewritten VW_ORDER_DETAIL, ECM branch, grain assertion.
-- Old whole-view behaviour (Q9): 11,881,246 rows / 5,874,386 distinct orders.
-- PASS = rows_ equals orders_.
-- ===========================================================================
SELECT COUNT(*) AS rows_, COUNT(DISTINCT ORDER_ID) AS orders_
FROM (
    SELECT O.ORDER_ID
    FROM (
        SELECT E.*
        FROM (
            SELECT EO.*,
                   ROW_NUMBER() OVER (PARTITION BY EO.ORDER_ID ORDER BY EO.ROWID) AS RN_
            FROM DGSTREAM.OB_ECM_ORDER EO
        ) E
        WHERE E.RN_ = 1
    ) O
    INNER JOIN (
        SELECT X.*
        FROM (
            SELECT ET.ECM_TRANSACTION_ID, ET.DEAL_TRANSACTION_ID,
                   ROW_NUMBER() OVER (PARTITION BY ET.ECM_TRANSACTION_ID
                                      ORDER BY ET.ROWID) AS RN_
            FROM DGSTREAM.OPUS_ECM_TRANSACTION ET
        ) X
        WHERE X.RN_ = 1
    ) T
        ON O.DEAL_ID = T.DEAL_TRANSACTION_ID
        AND O.IS_OWNED = 'true'
        AND O.ORDER_STATUS NOT IN ('CANCELLED', 'DELETED', 'PASS')
        AND ((O.IS_MATCHED = 'true' AND O.IS_DOMINANT = 'true') OR O.IS_MATCHED = 'false')
    INNER JOIN (
        SELECT ECM_TRANSACTION_ID, MAX(STATUS_VALUE) AS STATUS_VALUE
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_STATUS
        WHERE STATUS_TYPE = 'Execution_Status'
          AND STATUS_VALUE NOT IN ('Confidential', 'Withdrawn', 'Terminated')
        GROUP BY ECM_TRANSACTION_ID
    ) S
        ON T.ECM_TRANSACTION_ID = S.ECM_TRANSACTION_ID
    LEFT JOIN (
        SELECT ORDER_ID, MAX(LIMIT_VALUE) AS LIMIT_VALUE
        FROM DGSTREAM.OB_ECM_ORDER_IOI
        GROUP BY ORDER_ID
    ) OI
        ON O.ORDER_ID = OI.ORDER_ID
    LEFT JOIN DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TT
        ON T.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
        AND TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) = O.TRANCHE_ID
    LEFT JOIN (
        SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID,
               MAX(CURRENCY_NAME) AS CURRENCY_NAME
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY
        GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID
    ) TDC
        ON TT.ECM_TRANSACTION_ID = TDC.ECM_TRANSACTION_ID
        AND TT.ECM_TRANSACTION_TRANCHE_ID = TDC.ECM_TRANSACTION_TRANCHE_ID
        AND TT.TRANCHE_CURRENCY_ID = TDC.CURRENCY_ID
);


-- ===========================================================================
-- V4 [heavy] The rewritten VW_ORDER_DETAIL, DCM branch, grain + allocation.
-- PASS = rows_ equals orders_, AND sum_alloc is a large non-zero number.
--        Today the deployed view reports 0 allocation for the busiest
--        tranches, so a non-trivial sum here is the fix working.
-- ===========================================================================
SELECT COUNT(*)                AS rows_,
       COUNT(DISTINCT ORDER_ID) AS orders_,
       SUM(ORDER_ALLOCATION)   AS sum_alloc,
       COUNT(CASE WHEN ORDER_ALLOCATION > 0 THEN 1 END) AS orders_with_alloc
FROM (
    SELECT O.ORDER_ID,
           NVL(O.FINAL_ALLOC, 0) AS ORDER_ALLOCATION
    FROM (
        SELECT D.*
        FROM (
            SELECT DO.ORDER_ID, DO.ROOT_ID, DO.PARENT_ID, DO.FINAL_ALLOC,
                   ROW_NUMBER() OVER (PARTITION BY DO.ORDER_ID ORDER BY DO.ROWID) AS RN_
            FROM DGSTREAM.OB_ORDER DO
        ) D
        WHERE D.RN_ = 1
    ) O
    INNER JOIN (
        SELECT Y.*
        FROM (
            SELECT DT.DEAL_ID, DT.TRANCHE_ID,
                   ROW_NUMBER() OVER (PARTITION BY DT.DEAL_ID, DT.TRANCHE_ID
                                      ORDER BY DT.ROWID) AS RN_
            FROM DGSTREAM.OB_DEAL_TRANCHE DT
        ) Y
        WHERE Y.RN_ = 1
    ) ODT
        ON ODT.DEAL_ID = O.ROOT_ID AND ODT.TRANCHE_ID = O.PARENT_ID
    LEFT JOIN (
        SELECT ORDER_ID, MAX(AMT) AS AMT
        FROM DGSTREAM.OB_ORDER_SIZE
        GROUP BY ORDER_ID
    ) OZ
        ON O.ORDER_ID = OZ.ORDER_ID
);


-- ===========================================================================
-- V5 [cheap] *** THE GAP I COULD NOT CLOSE ***
-- The tranche view driving tables. I pre-aggregated six joins around them
-- but never checked the spine itself. If either is non-unique the tranche
-- grain still fails after my fix, and I would need to dedupe the FROM too.
-- The Q12 OB_DEAL_TRANCHE line was the one the screenshot OCR could not read.
-- PASS = both zero.
-- ===========================================================================
SELECT 'OPUS_ECM_TRANSACTION_TRANCHE per (txn,tranche)' AS spine_, COUNT(*) AS offenders
FROM   (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
        FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
        HAVING COUNT(*) > 1)
UNION ALL
SELECT 'OB_DEAL_TRANCHE per (deal,tranche)', COUNT(*)
FROM   (SELECT DEAL_ID, TRANCHE_ID
        FROM   DGSTREAM.OB_DEAL_TRANCHE
        GROUP  BY DEAL_ID, TRANCHE_ID
        HAVING COUNT(*) > 1);


-- ===========================================================================
-- V6 [cheap] Does the ECM tranche id repeat ACROSS transactions?
-- My deal-view TRANCHE_COUNT counts DISTINCT txn||'~'||tranche to be safe.
-- If tranche ids are globally unique this is belt-and-braces; if they repeat
-- per transaction it is load-bearing. Either way I want to know.
-- ===========================================================================
SELECT COUNT(*)                                        AS tranche_rows,
       COUNT(DISTINCT ECM_TRANSACTION_TRANCHE_ID)      AS distinct_tranche_ids,
       COUNT(DISTINCT ECM_TRANSACTION_ID || '~' ||
                      ECM_TRANSACTION_TRANCHE_ID)      AS distinct_txn_tranche
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE;


-- ===========================================================================
-- V7 [cheap] Transactions with a NULL DEAL_TRANSACTION_ID.
-- I added a guard that drops these. This says what the guard costs.
-- ===========================================================================
SELECT COUNT(*) AS txn_rows,
       COUNT(CASE WHEN DEAL_TRANSACTION_ID IS NULL THEN 1 END) AS null_deal_id
FROM   DGSTREAM.OPUS_ECM_TRANSACTION;


-- ===========================================================================
-- V8 [cheap] Is DCM TRANCHE_SIZE already numeric?
-- I reverted the DCM branch to NVL(ODT.TRANCHE_SIZE, 0) rather than risk
-- TO_CHAR scientific notation zeroing real sizes. If the base column is
-- NUMBER, removing the ECM cast alone yields a NUMBER view column.
-- PASS = this runs without ORA-01722 and the numbers look like money.
-- ===========================================================================
SELECT MIN(NVL(TRANCHE_SIZE, 0))              AS min_size,
       MAX(NVL(TRANCHE_SIZE, 0))              AS max_size,
       SUM(NVL(TRANCHE_SIZE, 0))              AS sum_size,
       COUNT(CASE WHEN TRANCHE_SIZE > 1000000000 THEN 1 END) AS over_1bn
FROM   DGSTREAM.OB_DEAL_TRANCHE;


-- ===========================================================================
-- V9 [cheap] Does the new ECM TRANCHE_SIZE expression agree with the raw
-- value, and does it survive large numbers? This is the exact expression now
-- in the view. PASS = mismatches is 0 and max_size looks like a real size.
-- ===========================================================================
SELECT COUNT(*) AS rows_,
       MIN(CASE WHEN REGEXP_LIKE(TO_CHAR(TRANCHE_OFFER_SIZE), '^\s*-?[0-9]+(\.[0-9]+)?\s*$')
                THEN TO_NUMBER(TRIM(TO_CHAR(TRANCHE_OFFER_SIZE))) ELSE 0 END) AS min_size,
       MAX(CASE WHEN REGEXP_LIKE(TO_CHAR(TRANCHE_OFFER_SIZE), '^\s*-?[0-9]+(\.[0-9]+)?\s*$')
                THEN TO_NUMBER(TRIM(TO_CHAR(TRANCHE_OFFER_SIZE))) ELSE 0 END) AS max_size,
       COUNT(CASE WHEN TRANCHE_OFFER_SIZE IS NOT NULL
                   AND NOT REGEXP_LIKE(TO_CHAR(TRANCHE_OFFER_SIZE), '^\s*-?[0-9]+(\.[0-9]+)?\s*$')
                  THEN 1 END) AS would_become_zero
FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE;


-- ===========================================================================
-- V10 [cheap] BLAST RADIUS of the MAX() collapse I introduced.
-- Multi-transaction ECM deals now produce one row, with MAX() picking the
-- winner per attribute. This counts deals where the transactions actually
-- DISAGREE — those are the rows where MAX() silently chooses.
-- If this is near zero the collapse is free. If it is large, tell me and I
-- will pick a deliberate winner (latest transaction) instead of MAX.
-- ===========================================================================
SELECT COUNT(*)                                                   AS multi_txn_deals,
       SUM(CASE WHEN name_variants  > 1 THEN 1 ELSE 0 END)        AS disagree_on_name,
       SUM(CASE WHEN size_variants  > 1 THEN 1 ELSE 0 END)        AS disagree_on_size,
       SUM(CASE WHEN issuer_variants > 1 THEN 1 ELSE 0 END)       AS disagree_on_issuer
FROM   (SELECT DEAL_TRANSACTION_ID,
               COUNT(DISTINCT ECM_TRANSACTION_ID)      AS txns,
               COUNT(DISTINCT SYNDICATE_DEAL_NAME)     AS name_variants,
               COUNT(DISTINCT DEAL_SIZE)               AS size_variants,
               COUNT(DISTINCT ISSUER_NAME_FROM_SOURCE) AS issuer_variants
        FROM   DGSTREAM.OPUS_ECM_TRANSACTION
        WHERE  DEAL_TRANSACTION_ID IS NOT NULL
        GROUP  BY DEAL_TRANSACTION_ID
        HAVING COUNT(DISTINCT ECM_TRANSACTION_ID) > 1);


-- ===========================================================================
-- V11 [cheap] Same question for the pre-aggregations where I used MAX() on a
-- previously-raw join: do the duplicate rows actually differ, or are they
-- exact copies? Exact copies mean MAX() is lossless.
-- ===========================================================================
SELECT 'OPUS_BASE_TRANSACTION.DEAL_REGION' AS agg_, COUNT(*) AS keys_where_values_differ
FROM   (SELECT TRANSACTION_ID FROM DGSTREAM.OPUS_BASE_TRANSACTION
        GROUP BY TRANSACTION_ID HAVING COUNT(DISTINCT DEAL_REGION) > 1)
UNION ALL
SELECT 'TRANCHE_PRODUCT_DETAIL.SECURITY_TYPE_NAME', COUNT(*)
FROM   (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
        FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
        HAVING COUNT(DISTINCT SECURITY_TYPE_NAME) > 1)
UNION ALL
SELECT 'TRANCHE_DEMAND_CURRENCY.CURRENCY_NAME', COUNT(*)
FROM   (SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID
        FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID
        HAVING COUNT(DISTINCT CURRENCY_NAME) > 1)
UNION ALL
SELECT 'OB_ECM_ORDER_IOI.LIMIT_VALUE', COUNT(*)
FROM   (SELECT ORDER_ID FROM DGSTREAM.OB_ECM_ORDER_IOI
        GROUP BY ORDER_ID HAVING COUNT(DISTINCT LIMIT_VALUE) > 1)
UNION ALL
SELECT 'OB_ORDER_SIZE.AMT', COUNT(*)
FROM   (SELECT ORDER_ID FROM DGSTREAM.OB_ORDER_SIZE
        GROUP BY ORDER_ID HAVING COUNT(DISTINCT AMT) > 1)
UNION ALL
SELECT 'OB_DEAL_ISSUER.NAME', COUNT(*)
FROM   (SELECT DEAL_TRANCHE_ID FROM DGSTREAM.OB_DEAL_ISSUER
        GROUP BY DEAL_TRANCHE_ID HAVING COUNT(DISTINCT NAME) > 1)
UNION ALL
SELECT 'EXEC_STATUS.STATUS_VALUE', COUNT(*)
FROM   (SELECT ECM_TRANSACTION_ID FROM DGSTREAM.OPUS_ECM_TRANSACTION_STATUS
        WHERE  STATUS_TYPE = 'Execution_Status'
        GROUP  BY ECM_TRANSACTION_ID HAVING COUNT(DISTINCT STATUS_VALUE) > 1);
-- Zero on a line = duplicates are exact copies, MAX() loses nothing.
-- Non-zero = MAX() is picking, and I should say so in the ontology.


-- ===========================================================================
-- V12 [heavy] Allocation fix across the WHOLE DCM population, not 5 tranches.
-- PASS = sum_order_alloc is the same order of magnitude as sum_tranche_size.
--        The deployed view would score near zero on sum_matchgroup_alloc.
-- ===========================================================================
SELECT SUM(t.sz)                AS sum_tranche_size,
       SUM(o.alloc)             AS sum_order_alloc,
       SUM(m.alloc)             AS sum_matchgroup_alloc,
       COUNT(*)                 AS tranches
FROM   (SELECT DEAL_ID, TRANCHE_ID, MAX(NVL(TRANCHE_SIZE,0)) sz
        FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY DEAL_ID, TRANCHE_ID) t
LEFT   JOIN (SELECT ROOT_ID, PARENT_ID, SUM(FINAL_ALLOC) alloc
             FROM DGSTREAM.OB_ORDER GROUP BY ROOT_ID, PARENT_ID) o
       ON o.ROOT_ID = t.DEAL_ID AND o.PARENT_ID = t.TRANCHE_ID
LEFT   JOIN (SELECT ROOT_ID, PARENT_ID, SUM(FINAL_ALLOC) alloc
             FROM DGSTREAM.OB_ORDER_MATCH_GROUP GROUP BY ROOT_ID, PARENT_ID) m
       ON m.ROOT_ID = t.DEAL_ID AND m.PARENT_ID = t.TRANCHE_ID;


-- ===========================================================================
-- V13 [cheap] List lengths under the NEW keying. I changed CURRENCIES from
-- per-transaction to per-DEAL and BND_BANK from a scalar to a list, so both
-- can only get longer. Columns are VARCHAR2(32767); LISTAGG overflow raises
-- ORA-01489 and kills the whole query.
-- PASS = all well under 32767.
-- ===========================================================================
SELECT 'deal currencies (new per-deal keying)' AS list_, MAX(len) AS max_chars
FROM   (SELECT SUM(LENGTH(TRANCHE_CURRENCY_ID) + 3) len
        FROM   (SELECT DISTINCT ET.DEAL_TRANSACTION_ID, TT.TRANCHE_CURRENCY_ID
                FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TT
                JOIN   (SELECT DISTINCT ECM_TRANSACTION_ID, DEAL_TRANSACTION_ID
                        FROM DGSTREAM.OPUS_ECM_TRANSACTION) ET
                  ON   ET.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID)
        GROUP  BY DEAL_TRANSACTION_ID)
UNION ALL
SELECT 'bnd_bank (new list form)', MAX(len)
FROM   (SELECT SUM(LENGTH(SYNDICATE_MEMBER_NAME) + 3) len
        FROM   DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
        WHERE  BND_BROKER = 'true'
        GROUP  BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID)
UNION ALL
SELECT 'dcm identifier values', MAX(len)
FROM   (SELECT SUM(LENGTH(VALUE) + 3) len
        FROM DGSTREAM.OB_TRANCHE GROUP BY DEAL_TRANCHE_ID);


-- ===========================================================================
-- V14-V17 — ECM ISSUER NAME, still open from Q28
--
-- Q28 returned FIVE groups, not six: ISSUER/ECM is absent from
-- VW_ENTITY_SEARCH entirely, so ECM issuer name resolution returns nothing.
-- V1/domain/dictionary-official.md records ISSUER_NAME as present on BOTH
-- products in V1, so either the source column changed or it stopped being
-- populated. The old view is still deployed, so we can diff directly.
-- ===========================================================================

-- V14 [cheap] Which ECM issuer fields are populated at source?
SELECT COUNT(*)                       AS ecm_txn_rows,
       COUNT(ISSUER_NAME_FROM_SOURCE) AS with_issuer_name,
       COUNT(ISSUER_GFCID)            AS with_gfcid,
       COUNT(ISSUER_TICKER)           AS with_ticker,
       COUNT(ISSUER_INDUSTRY_SECTOR)  AS with_sector,
       COUNT(SYNDICATE_DEAL_NAME)     AS with_deal_name
FROM   DGSTREAM.OPUS_ECM_TRANSACTION;


-- V15 [cheap] *** DECISIVE *** the old V1 view vs the new one, same question.
-- If V1 has ECM issuer names and V2 does not, the V1 source is the right one.
SELECT 'V1 VW_DEAL_ORDER_SUMMARY' AS view_, PRODUCT,
       COUNT(*) AS rows_, COUNT(ISSUER_NAME) AS with_issuer, COUNT(GFCID) AS with_gfcid
FROM   DGSTREAM.VW_DEAL_ORDER_SUMMARY GROUP BY PRODUCT
UNION ALL
SELECT 'V2 VW_DEAL_SUMMARY', PRODUCT,
       COUNT(*), COUNT(ISSUER_NAME), COUNT(GFCID)
FROM   DGSTREAM.VW_DEAL_SUMMARY GROUP BY PRODUCT;


-- V16 [cheap] Your hypothesis: does the ECM deal name carry the issuer?
-- Measured on the OLD view where both columns are known to be populated.
-- Below ~80% contained means deal name is correlated, not a substitute.
SELECT COUNT(*)                                                        AS ecm_rows_both,
       COUNT(CASE WHEN UPPER(DEAL_NAME) LIKE '%'||UPPER(ISSUER_NAME)||'%'
                  THEN 1 END)                                          AS name_contains_issuer,
       COUNT(CASE WHEN UPPER(DEAL_NAME) = UPPER(ISSUER_NAME) THEN 1 END) AS exactly_equal
FROM   DGSTREAM.VW_DEAL_ORDER_SUMMARY
WHERE  PRODUCT = 'ECM'
AND    ISSUER_NAME IS NOT NULL AND DEAL_NAME IS NOT NULL;


-- V17 [cheap] Eyeball 30 ECM deals: deal name beside every issuer field.
SELECT DEAL_TRANSACTION_ID, SYNDICATE_DEAL_NAME,
       ISSUER_NAME_FROM_SOURCE, ISSUER_GFCID, ISSUER_TICKER, ISSUER_INDUSTRY_SECTOR
FROM   DGSTREAM.OPUS_ECM_TRANSACTION
WHERE  SYNDICATE_DEAL_NAME IS NOT NULL
FETCH  FIRST 30 ROWS ONLY;


-- ===========================================================================
-- ROUND 2 — added after V1-V17.  V8 and V12 both died on ORA-01722, which
-- disproved my assumption that DCM TRANCHE_SIZE is numeric. It is character
-- data containing values Oracle cannot convert. I need to see them before I
-- can write the conversion, because the ECM-side fix alone will NOT make the
-- column numeric while DCM stays text.
-- ===========================================================================

-- V18 [cheap] *** BLOCKS THE TRANCHE_SIZE FIX ***
-- What is actually in DCM TRANCHE_SIZE that will not convert?
SELECT COUNT(*)                                                        AS non_null_rows,
       COUNT(CASE WHEN NOT REGEXP_LIKE(TRANCHE_SIZE,
                       '^\s*-?[0-9]+(\.[0-9]+)?\s*$') THEN 1 END)      AS non_numeric_rows
FROM   DGSTREAM.OB_DEAL_TRANCHE
WHERE  TRANCHE_SIZE IS NOT NULL;


-- V19 [cheap] Show me the offending values — the shape decides the fix
-- (thousands separators and currency prefixes are salvageable with a strip;
-- free text is not, and those rows become NULL rather than a fake 0).
SELECT TRANCHE_SIZE AS raw_value, COUNT(*) AS occurrences
FROM   DGSTREAM.OB_DEAL_TRANCHE
WHERE  TRANCHE_SIZE IS NOT NULL
AND    NOT REGEXP_LIKE(TRANCHE_SIZE, '^\s*-?[0-9]+(\.[0-9]+)?\s*$')
GROUP  BY TRANCHE_SIZE
ORDER  BY COUNT(*) DESC
FETCH  FIRST 30 ROWS ONLY;


-- V20 [cheap] Same question for DEAL_ISSUE_SIZE, which feeds DCM DEAL_SIZE on
-- vw_deal_summary. Q1 says that view column IS a NUMBER today, so this should
-- come back clean — but V8 already caught me assuming, so verify.
SELECT COUNT(*)                                                        AS non_null_rows,
       COUNT(CASE WHEN NOT REGEXP_LIKE(TO_CHAR(DEAL_ISSUE_SIZE),
                       '^\s*-?[0-9]+(\.[0-9]+)?\s*$') THEN 1 END)      AS non_numeric_rows
FROM   DGSTREAM.OB_DEAL_TRANCHE
WHERE  DEAL_ISSUE_SIZE IS NOT NULL;


-- V21 [heavy] Re-run of V12 with the conversion guarded, so it survives the
-- bad values. PASS = sum_order_alloc within an order of magnitude of
-- sum_tranche_size, and sum_matchgroup_alloc far smaller (the broken source).
SELECT SUM(t.sz)     AS sum_tranche_size,
       SUM(o.alloc)  AS sum_order_alloc,
       SUM(m.alloc)  AS sum_matchgroup_alloc,
       COUNT(*)      AS tranches
FROM   (SELECT DEAL_ID, TRANCHE_ID,
               MAX(CASE WHEN REGEXP_LIKE(TRANCHE_SIZE, '^\s*-?[0-9]+(\.[0-9]+)?\s*$')
                        THEN TO_NUMBER(TRIM(TRANCHE_SIZE)) END) sz
        FROM DGSTREAM.OB_DEAL_TRANCHE GROUP BY DEAL_ID, TRANCHE_ID) t
LEFT   JOIN (SELECT ROOT_ID, PARENT_ID, SUM(FINAL_ALLOC) alloc
             FROM DGSTREAM.OB_ORDER GROUP BY ROOT_ID, PARENT_ID) o
       ON o.ROOT_ID = t.DEAL_ID AND o.PARENT_ID = t.TRANCHE_ID
LEFT   JOIN (SELECT ROOT_ID, PARENT_ID, SUM(FINAL_ALLOC) alloc
             FROM DGSTREAM.OB_ORDER_MATCH_GROUP GROUP BY ROOT_ID, PARENT_ID) m
       ON m.ROOT_ID = t.DEAL_ID AND m.PARENT_ID = t.TRANCHE_ID;


-- V22 [heavy] Re-run of V3 with the tranche spine now deduped — this is the
-- fix for the 365 residual duplicates V3 found. V5 proved
-- OPUS_ECM_TRANSACTION_TRANCHE has 1,835 duplicate (txn,tranche) pairs and it
-- was the last join in the ECM order branch still going in raw.
-- PASS = rows_ equals orders_ equals 48,302.
SELECT COUNT(*) AS rows_, COUNT(DISTINCT ORDER_ID) AS orders_
FROM (
    SELECT O.ORDER_ID
    FROM (
        SELECT E.* FROM (
            SELECT EO.*, ROW_NUMBER() OVER (PARTITION BY EO.ORDER_ID ORDER BY EO.ROWID) AS RN_
            FROM DGSTREAM.OB_ECM_ORDER EO
        ) E WHERE E.RN_ = 1
    ) O
    INNER JOIN (
        SELECT X.* FROM (
            SELECT ET.ECM_TRANSACTION_ID, ET.DEAL_TRANSACTION_ID,
                   ROW_NUMBER() OVER (PARTITION BY ET.ECM_TRANSACTION_ID ORDER BY ET.ROWID) AS RN_
            FROM DGSTREAM.OPUS_ECM_TRANSACTION ET
        ) X WHERE X.RN_ = 1
    ) T
        ON O.DEAL_ID = T.DEAL_TRANSACTION_ID
        AND O.IS_OWNED = 'true'
        AND O.ORDER_STATUS NOT IN ('CANCELLED', 'DELETED', 'PASS')
        AND ((O.IS_MATCHED = 'true' AND O.IS_DOMINANT = 'true') OR O.IS_MATCHED = 'false')
    INNER JOIN (
        SELECT ECM_TRANSACTION_ID, MAX(STATUS_VALUE) AS STATUS_VALUE
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_STATUS
        WHERE STATUS_TYPE = 'Execution_Status'
          AND STATUS_VALUE NOT IN ('Confidential', 'Withdrawn', 'Terminated')
        GROUP BY ECM_TRANSACTION_ID
    ) S
        ON T.ECM_TRANSACTION_ID = S.ECM_TRANSACTION_ID
    LEFT JOIN (
        SELECT ORDER_ID, MAX(LIMIT_VALUE) AS LIMIT_VALUE
        FROM DGSTREAM.OB_ECM_ORDER_IOI GROUP BY ORDER_ID
    ) OI
        ON O.ORDER_ID = OI.ORDER_ID
    LEFT JOIN (
        SELECT W.* FROM (
            SELECT TTR.ECM_TRANSACTION_ID, TTR.ECM_TRANSACTION_TRANCHE_ID,
                   TTR.TRANCHE_NAME, TTR.PRICING_TS, TTR.TRANCHE_CURRENCY_ID,
                   ROW_NUMBER() OVER (PARTITION BY TTR.ECM_TRANSACTION_ID,
                                                   TTR.ECM_TRANSACTION_TRANCHE_ID
                                      ORDER BY TTR.ROWID) AS RN_
            FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TTR
        ) W WHERE W.RN_ = 1
    ) TT
        ON T.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
        AND TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) = O.TRANCHE_ID
    LEFT JOIN (
        SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID,
               MAX(CURRENCY_NAME) AS CURRENCY_NAME
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY
        GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID
    ) TDC
        ON TT.ECM_TRANSACTION_ID = TDC.ECM_TRANSACTION_ID
        AND TT.ECM_TRANSACTION_TRANCHE_ID = TDC.ECM_TRANSACTION_TRANCHE_ID
        AND TT.TRANCHE_CURRENCY_ID = TDC.CURRENCY_ID
);


-- ===========================================================================
-- V23 [heavy] *** THE UNTESTED VIEW ***
-- vw_tranche_summary is the file I changed most and never validated
-- end-to-end. V3 taught me that reasoning "every join is guarded" is not
-- enough — I reasoned exactly that about the order branch and was wrong.
-- Every join from the rewritten ECM branch is present here; only the grain
-- key is selected.
-- PASS = rows_ equals tranches_.  (V6 puts the true figure near 70,567.)
-- ===========================================================================
SELECT COUNT(*) AS rows_,
       COUNT(DISTINCT DEAL_ID || '~' || TRANCHE_ID) AS tranches_
FROM (
    SELECT T.DEAL_TRANSACTION_ID AS DEAL_ID,
           TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) AS TRANCHE_ID
    FROM (
        SELECT W.* FROM (
            SELECT TTR.ECM_TRANSACTION_ID, TTR.ECM_TRANSACTION_TRANCHE_ID,
                   TTR.TRANCHE_CURRENCY_ID,
                   ROW_NUMBER() OVER (PARTITION BY TTR.ECM_TRANSACTION_ID,
                                                   TTR.ECM_TRANSACTION_TRANCHE_ID
                                      ORDER BY TTR.ROWID) AS RN_
            FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TTR
        ) W WHERE W.RN_ = 1
    ) TT
    INNER JOIN (
        SELECT X.* FROM (
            SELECT ET.ECM_TRANSACTION_ID, ET.DEAL_TRANSACTION_ID,
                   ROW_NUMBER() OVER (PARTITION BY ET.ECM_TRANSACTION_ID
                                      ORDER BY ET.ROWID) AS RN_
            FROM DGSTREAM.OPUS_ECM_TRANSACTION ET
        ) X WHERE X.RN_ = 1
    ) T
        ON TT.ECM_TRANSACTION_ID = T.ECM_TRANSACTION_ID
    INNER JOIN (
        SELECT ECM_TRANSACTION_ID, MAX(STATUS_VALUE) AS STATUS_VALUE
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_STATUS
        WHERE STATUS_TYPE = 'Execution_Status'
          AND STATUS_VALUE NOT IN ('Confidential', 'Withdrawn', 'Terminated')
        GROUP BY ECM_TRANSACTION_ID
    ) S
        ON T.ECM_TRANSACTION_ID = S.ECM_TRANSACTION_ID
    LEFT JOIN (
        SELECT TRANSACTION_ID, MAX(DEAL_REGION) AS DEAL_REGION
        FROM DGSTREAM.OPUS_BASE_TRANSACTION GROUP BY TRANSACTION_ID
    ) OBT
        ON T.DEAL_TRANSACTION_ID = OBT.TRANSACTION_ID
    LEFT JOIN (
        SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID,
               MAX(SECURITY_TYPE_NAME) AS SECURITY_TYPE_NAME
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL
        GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
    ) TPD
        ON TT.ECM_TRANSACTION_ID = TPD.ECM_TRANSACTION_ID
        AND TT.ECM_TRANSACTION_TRANCHE_ID = TPD.ECM_TRANSACTION_TRANCHE_ID
    LEFT JOIN (
        SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID,
               MAX(CURRENCY_NAME) AS CURRENCY_NAME
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY
        GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID, CURRENCY_ID
    ) TDC
        ON TT.ECM_TRANSACTION_ID = TDC.ECM_TRANSACTION_ID
        AND TT.ECM_TRANSACTION_TRANCHE_ID = TDC.ECM_TRANSACTION_TRANCHE_ID
        AND TT.TRANCHE_CURRENCY_ID = TDC.CURRENCY_ID
    LEFT JOIN (
        SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID,
               MAX(SYNDICATE_MEMBER_NAME) AS BND_BANK
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
        GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
    ) SYN
        ON TT.ECM_TRANSACTION_ID = SYN.ECM_TRANSACTION_ID
        AND TT.ECM_TRANSACTION_TRANCHE_ID = SYN.ECM_TRANSACTION_TRANCHE_ID
    LEFT JOIN (
        SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID,
               MAX(IDENTIFIER_TYPE) AS IDENTIFIER_TYPE
        FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL_IDENTIFIER
        GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID
    ) IDN
        ON TT.ECM_TRANSACTION_ID = IDN.ECM_TRANSACTION_ID
        AND TT.ECM_TRANSACTION_TRANCHE_ID = IDN.ECM_TRANSACTION_TRANCHE_ID
);


-- ===========================================================================
-- V24 [heavy] Same for the DCM tranche branch. OB_DEAL_TRANCHE is its FROM
-- and the V5 line for it did not OCR, so its uniqueness is still unknown.
-- PASS = rows_ equals tranches_.
-- ===========================================================================
SELECT COUNT(*) AS rows_,
       COUNT(DISTINCT DEAL_ID || '~' || TRANCHE_ID) AS tranches_
FROM (
    SELECT ODT.DEAL_ID, ODT.TRANCHE_ID
    FROM DGSTREAM.OB_DEAL_TRANCHE ODT
    LEFT JOIN (
        SELECT Z.* FROM (
            SELECT DI.DEAL_TRANCHE_ID, DI.NAME,
                   ROW_NUMBER() OVER (PARTITION BY DI.DEAL_TRANCHE_ID
                                      ORDER BY DI.ROWID) AS RN_
            FROM DGSTREAM.OB_DEAL_ISSUER DI
        ) Z WHERE Z.RN_ = 1
    ) ODI
        ON ODI.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
    LEFT JOIN (
        SELECT DEAL_TRANCHE_ID, MAX(DELIVERY_TYPE) AS DELIVERY_TYPE
        FROM DGSTREAM.OB_TRANCHE GROUP BY DEAL_TRANCHE_ID
    ) IDN
        ON IDN.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
    LEFT JOIN (
        SELECT DEAL_TRANCHE_ID, MAX(AGENCY) AS A
        FROM DGSTREAM.OB_TRANCHE_RATING GROUP BY DEAL_TRANCHE_ID
    ) RAT
        ON RAT.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
    LEFT JOIN (
        SELECT DEAL_TRANCHE_ID, MAX(DEALER) AS D
        FROM DGSTREAM.OB_TRANCHE_SYNDICATE_MEMBER GROUP BY DEAL_TRANCHE_ID
    ) DST
        ON DST.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
);
