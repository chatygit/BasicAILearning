-- ===========================================================================
-- AWAY-ORDER SIZING (release 2 staged 2026-08-21). Read-only; run in PROD
-- BEFORE the release deploys — sizes what inclusion adds so the release
-- review knows how much every ECM total will move, and validates the
-- matched/dominant dedupe assumption.
-- ===========================================================================

-- O1 — population by ownership x match state (post-status-filter, the
--      view's own predicates minus IS_OWNED). The rows inclusion ADDS are
--      is_owned='false' AND (matched-dominant OR unmatched).
SELECT IS_OWNED, IS_MATCHED, IS_DOMINANT, COUNT(*) AS ROWS_
FROM   DGSTREAM.OB_ECM_ORDER
WHERE  ORDER_STATUS NOT IN ('CANCELLED', 'DELETED', 'PASS')
GROUP  BY IS_OWNED, IS_MATCHED, IS_DOMINANT
ORDER  BY IS_OWNED, IS_MATCHED, IS_DOMINANT;

-- O2 — dedupe sanity: matched pairs should contribute ONE dominant row.
--      >0 here = matched groups with multiple dominant rows (fan-out risk
--      the release review must see).
SELECT COUNT(*) AS MATCH_GROUPS_WITH_MULTI_DOMINANT
FROM (
    SELECT ORDER_ID
    FROM   DGSTREAM.OB_ECM_ORDER
    WHERE  IS_MATCHED = 'true' AND IS_DOMINANT = 'true'
    GROUP  BY ORDER_ID
    HAVING COUNT(*) > 1
);

-- O3 — does OB_ORDER (DCM) carry any ownership concept? (column census —
--      release 2 ships DCM ORDER_OWNERSHIP as NULL; confirm that is right)
SELECT column_name
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM' AND table_name = 'OB_ORDER'
AND    (column_name LIKE '%OWNED%' OR column_name LIKE '%OWNER%');
