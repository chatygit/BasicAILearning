-- ===========================================================================
-- DCM BOOKS / PROMPT-SUPPORT VALIDATION (D2, 2026-08-27). The planned test
-- prompts assume concepts the views do not carry: hedge book, trade book,
-- CV book, firm accounts, salespeople, trade ids, issuer LEI, DCM
-- syndicate members, DCM "allowed order types", tranche announcement
-- dates. Measure what the SOURCE has before promising anything. Run in
-- PROD; screenshot per query.
-- ===========================================================================

-- V1 — are there book/hedge/trade tables at all?
SELECT table_name
FROM   all_tables
WHERE  owner = 'DGSTREAM'
AND    (table_name LIKE '%HEDGE%' OR table_name LIKE '%BOOK%'
     OR table_name LIKE '%TRADE%' OR table_name LIKE '%SALES%'
     OR table_name LIKE '%ACCOUNT%')
ORDER  BY table_name;

-- V2 — the full OB_ORDER column list (never desc'd; OWNER/ALL_OWNERS came
--      from a LIKE probe). Book type, trade id, salesperson, firm account,
--      order type and hedge fields would live here if anywhere.
SELECT column_id, column_name, data_type
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM' AND table_name = 'OB_ORDER'
ORDER  BY column_id;

-- V3 — LEI anywhere in the schema?
SELECT table_name, column_name
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM' AND column_name LIKE '%LEI%'
ORDER  BY table_name;

-- V4 — DCM syndicate membership: does OB_TRANCHE_SYNDICATE_MEMBER carry
--      rows for DCM-keyed tranches, or is it ECM-only?
SELECT COUNT(*) AS SYND_ROWS,
       COUNT(CASE WHEN DT.DEAL_ID IS NOT NULL THEN 1 END) AS DCM_KEYED_ROWS
FROM   DGSTREAM.OB_TRANCHE_SYNDICATE_MEMBER S
LEFT JOIN (SELECT DISTINCT DEAL_ID, TRANCHE_ID FROM DGSTREAM.OB_DEAL_TRANCHE) DT
  ON S.DEAL_TRANCHE_ID = DT.DEAL_ID || '-' || DT.TRANCHE_ID;

-- V5 — tranche announcement date is ALREADY MEASURED (29,534/74,281) —
--      no query needed; it is a release-train exposure decision.
