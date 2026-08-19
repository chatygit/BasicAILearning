-- ===========================================================================
-- DEV DEPLOY DIAGNOSIS (2026-08-19). Deploy-check hit ORA-00904 BILLED_BY:
-- the DEV order view lacks the round-2 column. Two possible causes:
--   (a) an old FILE was deployed / the order view was skipped;
--   (b) our CREATE OR REPLACE FAILED in DEV (a source table/column our SQL
--       reads doesn't exist there) and the old view silently survived.
-- D1 separates them; D2 names the compile-breaker if it's (b).
-- ===========================================================================

-- D1 — which views were actually replaced, and when. A fresh LAST_DDL on
--      deal/tranche but an OLD one on VW_ORDER_DETAIL = the order view's
--      create never succeeded (or was never run). STATUS should be VALID.
SELECT object_name, status,
       TO_CHAR(created,       'YYYY-MM-DD HH24:MI') AS created_,
       TO_CHAR(last_ddl_time, 'YYYY-MM-DD HH24:MI') AS last_ddl_
FROM   all_objects
WHERE  owner = 'DGSTREAM' AND object_type = 'VIEW'
AND    object_name IN ('VW_DEAL_SUMMARY','VW_TRANCHE_SUMMARY',
                       'VW_ORDER_DETAIL','VW_ENTITY_SEARCH')
ORDER  BY object_name;

-- D2 — does DEV's schema carry every SOURCE column the new views read?
--      EXPECT 18 ROWS. Any missing pair is the exact identifier that made
--      the CREATE fail — hand that line to the view team.
SELECT table_name, column_name
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM'
AND (   (table_name = 'OB_ECM_ORDER'
         AND column_name = 'BILLEDBY_BROKER_CODE')                -- ECM billed_by
     OR (table_name = 'OB_ORDER'
         AND column_name = 'BND')                                 -- DCM billed_by
     OR (table_name = 'OPUS_ECM_TRANSACTION'
         AND column_name IN ('PRODUCT_OFFERING_TYPE_VALUE',       -- offering_type
                             'PRODUCT_EQUITY_TYPE_VALUE',         -- equity_type
                             'SETTLEMENT_TS'))
     OR (table_name = 'OPUS_BASE_TRANSACTION_RELATED_PARTIES'     -- party master
         AND column_name IN ('TRANSACTION_ID','PARTY_ROLE',       -- (all views'
                             'PARTY_NAME','PARTY_GFCID',          --  issuer layer)
                             'PARTY_TICKER','PUBLISHED_TS'))
     OR (table_name = 'OB_DEAL_ISSUER'
         AND column_name IN ('DEAL_TRANCHE_ID','GFCID',
                             'NAME','TICKER'))
     OR (table_name = 'OB_DEAL_TRANCHE'
         AND column_name IN ('REGION','SETTLEMENT_DATE'))         -- batch 3
    )
ORDER BY table_name, column_name;
