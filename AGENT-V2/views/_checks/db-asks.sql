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
-- S. WHY DO SO FEW IN-SCOPE ORDERS FIND THEIR MATCH GROUP? (R2, 2026-10-06:
-- 850,910 in-scope DCM orders, 28,087 with a group row on PRIMARY_ORDER_ID,
-- 5,740 of those with a group allocation — while R1 counts ~56k group rows
-- carrying FINAL_ALLOC, 42,914 of them 'new | SBB'.) Three statements; the
-- answer decides whether the join key or the dedupe needs changing.
-- ===========================================================================

-- S1. For every group carrying an allocation: does its PRIMARY_ORDER_ID exist
--     in OB_ORDER at all, and with what ITEM_SOURCE / STATUS? A big 'no match'
--     bucket = a different id space; a big RQ / deleted bucket = excluded on
--     purpose.
SELECT G.ITEM_SOURCE AS GROUP_SRC,
       NVL(O.ITEM_SOURCE, '(no OB_ORDER row)') AS ORDER_SRC,
       O.STATUS AS ORDER_STATUS,
       COUNT(*) AS GROUPS
FROM (
    SELECT PRIMARY_ORDER_ID, MAX(ITEM_SOURCE) AS ITEM_SOURCE
    FROM   DGSTREAM.OB_ORDER_MATCH_GROUP
    WHERE  PRIMARY_ORDER_ID IS NOT NULL AND FINAL_ALLOC > 0
    GROUP  BY PRIMARY_ORDER_ID
) G
LEFT JOIN (
    SELECT ORDER_ID, MAX(ITEM_SOURCE) AS ITEM_SOURCE, MAX(STATUS) AS STATUS
    FROM   DGSTREAM.OB_ORDER
    GROUP  BY ORDER_ID
) O ON O.ORDER_ID = G.PRIMARY_ORDER_ID
GROUP  BY G.ITEM_SOURCE, NVL(O.ITEM_SOURCE, '(no OB_ORDER row)'), O.STATUS
ORDER  BY GROUPS DESC;

-- S2. Does "latest version per primary order" drop allocations? Primary orders
--     that have an allocation on SOME version but not on their latest one.
WITH V AS (
    SELECT PRIMARY_ORDER_ID, FINAL_ALLOC,
           ROW_NUMBER() OVER (PARTITION BY PRIMARY_ORDER_ID ORDER BY DG_VERSION DESC, ROWID) AS RN_
    FROM   DGSTREAM.OB_ORDER_MATCH_GROUP
    WHERE  PRIMARY_ORDER_ID IS NOT NULL
)
SELECT COUNT(*) AS PRIMARIES_WITH_ANY_ALLOC,
       COUNT(CASE WHEN LATEST_ALLOC IS NULL THEN 1 END) AS LOST_BY_LATEST_VERSION
FROM (
    SELECT PRIMARY_ORDER_ID,
           MAX(FINAL_ALLOC) AS ANY_ALLOC,
           MAX(CASE WHEN RN_ = 1 THEN FINAL_ALLOC END) AS LATEST_ALLOC
    FROM   V
    GROUP  BY PRIMARY_ORDER_ID
)
WHERE ANY_ALLOC IS NOT NULL;

-- S3. Id shapes side by side (10 + 10 rows) — if the primary ids look like
--     another column of OB_ORDER (EXTERNAL_ORDER_ID, MISC_DRB_INVESTOR_ORDER_ID),
--     the join key is wrong, not the data.
SELECT 'group.PRIMARY_ORDER_ID' AS SRC, PRIMARY_ORDER_ID AS ID_
FROM   (SELECT PRIMARY_ORDER_ID FROM DGSTREAM.OB_ORDER_MATCH_GROUP
        WHERE FINAL_ALLOC > 0 AND ITEM_SOURCE = 'SBB' AND PRIMARY_ORDER_ID IS NOT NULL
        FETCH FIRST 10 ROWS ONLY)
UNION ALL
SELECT 'order.ORDER_ID | EXTERNAL | DRB', ORDER_ID || ' | ' || EXTERNAL_ORDER_ID || ' | ' || MISC_DRB_INVESTOR_ORDER_ID
FROM   (SELECT ORDER_ID, EXTERNAL_ORDER_ID, MISC_DRB_INVESTOR_ORDER_ID FROM DGSTREAM.OB_ORDER
        WHERE (ITEM_SOURCE IS NULL OR UPPER(ITEM_SOURCE) <> 'RQ') AND FINAL_ALLOC IS NULL
        FETCH FIRST 10 ROWS ONLY);
