-- ===========================================================================
-- AWAY-ORDER SIZING — ANSWERED 2026-08-21. Verdicts:
--  * O1: current (home-only) population = 48,102 rows (47,762 unmatched +
--    340 matched-dominant). Release 2 ADDS 21,836 away rows (21,778
--    unmatched + 58 matched-dominant) => ECM order population grows ~45%.
--    EVERY ECM total/count moves by up to that much — the release review
--    number.
--  * BONUS FINDING: 58 matched orders whose DOMINANT row is AWAY are
--    entirely INVISIBLE today (home row non-dominant + away row filtered
--    out = the order vanished). Release 2 RESTORES them — inclusion is a
--    correctness fix, not just a scope widening.
--  * Guard footnote: 38 rows carry NULL IS_MATCHED and fall through the
--    matched/unmatched guard under BOTH releases (pre-existing, tiny).
--  * O2 = 0 multi-dominant match groups — the dedupe assumption HOLDS; no
--    fan-out from inclusion.
--  * O3: OB_ORDER has no IS_OWNED but DOES have OWNER + ALL_OWNERS —
--    semantics unknown (plural suggests member lists, not a home/away
--    flag). DCM ORDER_OWNERSHIP stays NULL in release 2; census those two
--    columns before ever mapping them.
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
