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

-- ===========================================================================
-- V. SECONDARY LIST = EXTERNAL ORDER IDS (UAT). U1: the list is comma-
-- separated 8-digit ids ('16581936,16581488') — the shape of OB_ORDER.
-- EXTERNAL_ORDER_ID, not ORDER_ID — and ISN_ALLOC equals FINAL_ALLOC. U2:
-- zero matches by ORDER_ID, as that predicts. Three statements decide
-- whether a second match on EXTERNAL_ORDER_ID recovers the ~3.2k groups.
-- ===========================================================================

-- V1. U2 again, joined on EXTERNAL_ORDER_ID.
WITH G AS (
    SELECT MG.ORDER_GROUP_ID, MG.ROOT_ID, MG.PARENT_ID, MG.FINAL_ALLOC,
           MG.REF_SOURCE_SECONDARY_ORDER_LIST AS L
    FROM   DGSTREAM.OB_ORDER_MATCH_GROUP MG
    WHERE  MG.FINAL_ALLOC > 0 AND MG.PRIMARY_ORDER_ID IS NOT NULL AND MG.ITEM_SOURCE <> 'SBB'
    AND    NOT EXISTS (SELECT 1 FROM DGSTREAM.OB_ORDER O WHERE O.ORDER_ID = MG.PRIMARY_ORDER_ID)
    AND    MG.REF_SOURCE_SECONDARY_ORDER_LIST IS NOT NULL
), X AS (
    SELECT ORDER_GROUP_ID, ROOT_ID, PARENT_ID, FINAL_ALLOC,
           TRIM(REGEXP_SUBSTR(L, '[^,|; ]+', 1, LEVEL)) AS SEC_ID
    FROM   G
    CONNECT BY LEVEL <= REGEXP_COUNT(L, '[^,|; ]+')
           AND PRIOR ORDER_GROUP_ID = ORDER_GROUP_ID
           AND PRIOR SYS_GUID() IS NOT NULL
)
SELECT COUNT(DISTINCT X.ORDER_GROUP_ID) AS ORPHANED_GROUPS,
       COUNT(DISTINCT CASE WHEN O.ORDER_ID IS NOT NULL THEN X.ORDER_GROUP_ID END) AS GROUPS_NAMING_OUR_ORDER,
       COUNT(DISTINCT O.ORDER_ID) AS OUR_ORDERS_FOUND,
       COUNT(DISTINCT CASE WHEN O.ORDER_ID IS NOT NULL AND O.ROOT_ID = X.ROOT_ID THEN O.ORDER_ID END) AS SAME_DEAL,
       COUNT(DISTINCT CASE WHEN O.ORDER_ID IS NOT NULL AND O.FINAL_ALLOC IS NOT NULL THEN O.ORDER_ID END) AS ALREADY_ALLOCATED_ON_ORDER,
       COUNT(DISTINCT CASE WHEN O.ORDER_ID IS NOT NULL
                            AND (O.ITEM_SOURCE IS NULL OR UPPER(O.ITEM_SOURCE) <> 'RQ')
                            AND (O.STATUS IS NULL OR UPPER(O.STATUS) NOT IN ('DELETED', 'CANCELLED'))
                           THEN O.ORDER_ID END) AS IN_SCOPE
FROM   X
LEFT JOIN DGSTREAM.OB_ORDER O ON O.EXTERNAL_ORDER_ID = X.SEC_ID;

-- V2. Is EXTERNAL_ORDER_ID a usable key? Population and uniqueness within a
--     deal / tranche on the non-RQ book.
SELECT COUNT(*) AS ORDERS_,
       COUNT(EXTERNAL_ORDER_ID) AS WITH_EXTERNAL_ID,
       COUNT(DISTINCT ROOT_ID || '~' || PARENT_ID || '~' || EXTERNAL_ORDER_ID) AS DISTINCT_KEYS,
       COUNT(DISTINCT ORDER_ID) AS DISTINCT_ORDERS
FROM   DGSTREAM.OB_ORDER
WHERE  (ITEM_SOURCE IS NULL OR UPPER(ITEM_SOURCE) <> 'RQ');

-- V3. Across ALL allocated groups (not just the orphaned ones): how many
--     in-scope orders would the external-id match reach that the primary-id
--     match does not — the size of the second fallback.
WITH G AS (
    SELECT MG.ORDER_GROUP_ID, MG.ROOT_ID, MG.PARENT_ID, MG.PRIMARY_ORDER_ID, MG.FINAL_ALLOC,
           MG.REF_SOURCE_SECONDARY_ORDER_LIST AS L
    FROM   DGSTREAM.OB_ORDER_MATCH_GROUP MG
    WHERE  MG.FINAL_ALLOC > 0 AND MG.REF_SOURCE_SECONDARY_ORDER_LIST IS NOT NULL
), X AS (
    SELECT ORDER_GROUP_ID, ROOT_ID, PARENT_ID, PRIMARY_ORDER_ID,
           TRIM(REGEXP_SUBSTR(L, '[^,|; ]+', 1, LEVEL)) AS SEC_ID
    FROM   G
    CONNECT BY LEVEL <= REGEXP_COUNT(L, '[^,|; ]+')
           AND PRIOR ORDER_GROUP_ID = ORDER_GROUP_ID
           AND PRIOR SYS_GUID() IS NOT NULL
)
SELECT COUNT(DISTINCT O.ORDER_ID) AS ORDERS_REACHED_BY_EXTERNAL_ID,
       COUNT(DISTINCT CASE WHEN O.ORDER_ID <> X.PRIMARY_ORDER_ID THEN O.ORDER_ID END) AS NOT_THE_PRIMARY,
       COUNT(DISTINCT CASE WHEN O.ORDER_ID <> X.PRIMARY_ORDER_ID AND O.FINAL_ALLOC IS NULL THEN O.ORDER_ID END) AS NEW_ALLOCATIONS
FROM   X
JOIN   DGSTREAM.OB_ORDER O ON O.EXTERNAL_ORDER_ID = X.SEC_ID AND O.ROOT_ID = X.ROOT_ID
WHERE  (O.ITEM_SOURCE IS NULL OR UPPER(O.ITEM_SOURCE) <> 'RQ')
AND    (O.STATUS IS NULL OR UPPER(O.STATUS) NOT IN ('DELETED', 'CANCELLED'));
