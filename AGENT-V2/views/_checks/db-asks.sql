-- ===========================================================================
-- DB ASKS — only what still has to run. Run as a SCRIPT (F5) on UAT, screenshot
-- (or paste Script Output as text where the section says so) into
-- ~/Desktop/ADK. A section is deleted the moment its results are recorded.
-- Standing scripts (name validation, scale census, Trino visibility, PROD
-- census pack) are kept in PROMOTE-CHECKLIST.md / memory, not here.
-- ===========================================================================


-- ===========================================================================
-- N. 2026-09-21 — IPREO ECM BUILD CENSUS. Everything the three Ipreo branches
-- (deal / tranche / order views, third UNION ALL, PRODUCT 'ECM') stand on, in
-- ONE script. Run as a SCRIPT (F5) on UAT and paste the Script Output as
-- TEXT — column names and codes do not survive screenshots. A statement that
-- ERRORS is a finding (a table or column the draft assumed does not exist):
-- keep going, paste the error. Sections: A schema · B keys · C grain ·
-- D vocabularies · E fill · F exclusions · G overlap · H stability.
-- ===========================================================================

-- ---------- A. SCHEMA (the S1 name-validation source) ----------------------
-- N-A1. Every Ipreo table with row counts.
SELECT table_name, num_rows, last_analyzed
FROM   all_tables WHERE owner = 'DGSTREAM' AND UPPER(table_name) LIKE '%IPREO%'
ORDER  BY table_name;

-- N-A2. Every column of every Ipreo table + the two OPUS tables the draft reuses.
SELECT table_name, column_id, column_name, data_type, data_length, data_precision, data_scale, nullable
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM'
AND   (UPPER(table_name) LIKE '%IPREO%'
       OR table_name IN ('OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY', 'OPUS_ECM_TRANSACTION_STATUS'))
ORDER  BY table_name, column_id;

-- N-A3. Indexes on the Ipreo tables (the filter shapes we will hit: deal id,
--       tranche id, order id, investor code).
SELECT i.table_name, i.index_name, i.uniqueness,
       LISTAGG(c.column_name, ',') WITHIN GROUP (ORDER BY c.column_position) AS cols
FROM   all_indexes i JOIN all_ind_columns c
       ON c.index_owner = i.owner AND c.index_name = i.index_name
WHERE  i.owner = 'DGSTREAM' AND UPPER(i.table_name) LIKE '%IPREO%'
GROUP  BY i.table_name, i.index_name, i.uniqueness
ORDER  BY i.table_name, i.index_name;

-- ---------- B. KEYS (which id ties issue -> tranche -> order -> OPUS txn) ---
-- N-B1. Does an Ipreo ISS_ID equal an OPUS DEAL_TRANSACTION_ID? Counts of each
--       population and of the intersection under that equality.
SELECT (SELECT COUNT(*) FROM DGSTREAM.IPREO_ISSUE) AS ISSUES_,
       (SELECT COUNT(DISTINCT DEAL_TRANSACTION_ID) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION
         WHERE DEAL_TRANSACTION_ID IS NOT NULL) AS IPREO_OPUS_TXNS_,
       (SELECT COUNT(*) FROM DGSTREAM.IPREO_ISSUE I
         WHERE EXISTS (SELECT 1 FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T
                       WHERE T.DEAL_TRANSACTION_ID = TO_CHAR(I.ISS_ID))) AS ISSUES_MATCHING_TXN_
FROM   DUAL;

-- N-B2. Candidate link columns, by name, on the four key tables.
SELECT table_name, column_name, data_type
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM'
AND    table_name IN ('IPREO_ISSUE', 'IPREO_OPUS_ECM_TRANSACTION', 'IPREO_TRANCHE', 'IPREO_ORDER',
                      'IPREO_OPUS_ECM_TRANSACTION_TRANCHE')
AND   (column_name LIKE '%TRANSACTION%' OR column_name LIKE '%DEAL%' OR column_name LIKE '%ISS%'
       OR column_name LIKE '%TRN%' OR column_name LIKE '%OPUS%' OR column_name LIKE '%EXT%'
       OR column_name LIKE '%REF%' OR column_name LIKE '%_ID')
ORDER  BY table_name, column_name;

-- N-B3. Ten sample ids side by side, so the format itself can be compared
--       (numeric vs text, 8-digit vs GUID).
SELECT 'IPREO_ISSUE.ISS_ID' AS SRC, TO_CHAR(ISS_ID) AS ID_ FROM DGSTREAM.IPREO_ISSUE WHERE ROWNUM <= 10
UNION ALL
SELECT 'IPREO_OPUS_ECM_TRANSACTION.DEAL_TRANSACTION_ID', DEAL_TRANSACTION_ID
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION WHERE DEAL_TRANSACTION_ID IS NOT NULL AND ROWNUM <= 10
UNION ALL
SELECT 'IPREO_OPUS_ECM_TRANSACTION.ECM_TRANSACTION_ID', TO_CHAR(ECM_TRANSACTION_ID)
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION WHERE ROWNUM <= 10
UNION ALL
SELECT 'IPREO_TRANCHE.TRN_ID', TO_CHAR(TRN_ID) FROM DGSTREAM.IPREO_TRANCHE WHERE ROWNUM <= 10
UNION ALL
SELECT 'IPREO_OPUS_ECM_TRANSACTION_TRANCHE.ECM_TRANSACTION_TRANCHE_ID', TO_CHAR(ECM_TRANSACTION_TRANCHE_ID)
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE WHERE ROWNUM <= 10
UNION ALL
SELECT 'OPUS_ECM_TRANSACTION.DEAL_TRANSACTION_ID (current ECM)', DEAL_TRANSACTION_ID
FROM   DGSTREAM.OPUS_ECM_TRANSACTION WHERE DEAL_TRANSACTION_ID IS NOT NULL AND ROWNUM <= 10;

-- N-B4. Tranche -> issue: does every IPREO_TRANCHE carry an ISS_ID that exists
--       in IPREO_ISSUE, and does IPREO_OPUS_ECM_TRANSACTION_TRANCHE link to
--       IPREO_TRANCHE at all (which column)?
SELECT (SELECT COUNT(*) FROM DGSTREAM.IPREO_TRANCHE) AS TRANCHES_,
       (SELECT COUNT(*) FROM DGSTREAM.IPREO_TRANCHE T
         WHERE EXISTS (SELECT 1 FROM DGSTREAM.IPREO_ISSUE I WHERE I.ISS_ID = T.ISS_ID)) AS TRANCHES_WITH_ISSUE_,
       (SELECT COUNT(*) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE) AS OPUS_TRANCHES_
FROM   DUAL;

-- N-B5. Order -> tranche / issue integrity.
SELECT COUNT(*) AS ORDERS_,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM DGSTREAM.IPREO_TRANCHE T WHERE T.TRN_ID = O.TRN_ID) THEN 1 ELSE 0 END) AS WITH_TRANCHE_,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM DGSTREAM.IPREO_ISSUE I WHERE I.ISS_ID = O.ISS_ID) THEN 1 ELSE 0 END) AS WITH_ISSUE_
FROM   DGSTREAM.IPREO_ORDER O;

-- ---------- C. GRAIN (what one row means, per table) -----------------------
-- N-C1. Rows vs distinct keys — a ratio above 1 means versions/duplicates and
--       the branch needs a dedupe (ROW_NUMBER by ROWID, like the OPUS branch).
SELECT 'IPREO_ISSUE' AS TBL, COUNT(*) AS ROWS_, COUNT(DISTINCT ISS_ID) AS DISTINCT_KEY_ FROM DGSTREAM.IPREO_ISSUE
UNION ALL SELECT 'IPREO_TRANCHE', COUNT(*), COUNT(DISTINCT TRN_ID) FROM DGSTREAM.IPREO_TRANCHE
UNION ALL SELECT 'IPREO_ORDER', COUNT(*), COUNT(DISTINCT ORD_ID) FROM DGSTREAM.IPREO_ORDER
UNION ALL SELECT 'IPREO_ORDER (ORD_ID,TRN_ID)', COUNT(*), COUNT(DISTINCT ORD_ID || '~' || TRN_ID) FROM DGSTREAM.IPREO_ORDER
UNION ALL SELECT 'IPREO_ORDERPRODUCT (ORD_ID,TRN_ID)', COUNT(*), COUNT(DISTINCT ORD_ID || '~' || TRN_ID) FROM DGSTREAM.IPREO_ORDERPRODUCT
UNION ALL SELECT 'IPREO_ORDERIOI', COUNT(*), COUNT(DISTINCT ORD_ID) FROM DGSTREAM.IPREO_ORDERIOI
UNION ALL SELECT 'IPREO_OPUS_ECM_TRANSACTION', COUNT(*), COUNT(DISTINCT ECM_TRANSACTION_ID) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION
UNION ALL SELECT 'IPREO_OPUS_ECM_TRANSACTION (DEAL_TRANSACTION_ID)', COUNT(*), COUNT(DISTINCT DEAL_TRANSACTION_ID) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION
UNION ALL SELECT 'IPREO_OPUS_ECM_TRANSACTION_TRANCHE', COUNT(*), COUNT(DISTINCT ECM_TRANSACTION_TRANCHE_ID) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_TRANCHE;

-- N-C2. IOI curve: points per order in IPREO_ORDERIOI (1 = scalar, >1 = curve).
SELECT POINTS, COUNT(*) AS ORDERS_
FROM  (SELECT ORD_ID, COUNT(*) AS POINTS FROM DGSTREAM.IPREO_ORDERIOI GROUP BY ORD_ID)
GROUP  BY POINTS ORDER BY POINTS;

-- ---------- D. VOCABULARIES (the codes the branch maps by CASE) ------------
-- N-D1. Order product: IOI amount type codes (draft maps C/F/P/% — verify).
SELECT 'IOI_AMT_TYPE' AS COL, IOI_AMT_TYPE AS VAL, COUNT(*) AS N FROM DGSTREAM.IPREO_ORDERPRODUCT GROUP BY IOI_AMT_TYPE
UNION ALL SELECT 'IPREO_ORDER.DELETED_IND', DELETED_IND, COUNT(*) FROM DGSTREAM.IPREO_ORDER GROUP BY DELETED_IND
UNION ALL SELECT 'IPREO_ISSUE.DEAL_STATE_CD', DEAL_STATE_CD, COUNT(*) FROM DGSTREAM.IPREO_ISSUE GROUP BY DEAL_STATE_CD
ORDER  BY 1, 3 DESC;

-- N-D2. Any OTHER status-like column on IPREO_ORDER / IPREO_ISSUE / IPREO_TRANCHE
--       (the draft's ORDER_STATUS is derived from DELETED_IND alone, so the
--       CANCELLED / PASS exclusion is inert unless a real status exists).
SELECT table_name, column_name, data_type
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM' AND table_name IN ('IPREO_ORDER', 'IPREO_ISSUE', 'IPREO_TRANCHE', 'IPREO_ORDERPRODUCT')
AND   (column_name LIKE '%STAT%' OR column_name LIKE '%STATE%' OR column_name LIKE '%IND' OR column_name LIKE '%FLAG%'
       OR column_name LIKE '%CANCEL%' OR column_name LIKE '%DELET%' OR column_name LIKE '%ACTIVE%')
ORDER  BY table_name, column_name;

-- N-D3. Execution status vocabulary on the Ipreo OPUS status table (the
--       Confidential/Withdrawn/Terminated exclusion must find the same words).
SELECT STATUS_TYPE, STATUS_VALUE, COUNT(DISTINCT ECM_TRANSACTION_ID) AS TXNS_
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_STATUS
GROUP  BY STATUS_TYPE, STATUS_VALUE ORDER BY STATUS_TYPE, TXNS_ DESC;

-- N-D4. Equity type / offering type vocabularies on the Ipreo spine (must
--       match the OPUS vocabulary the catalogs document, or map to it).
SELECT 'EQUITY_TYPE' AS COL, PRODUCT_EQUITY_TYPE_VALUE AS VAL, COUNT(*) AS N
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION GROUP BY PRODUCT_EQUITY_TYPE_VALUE
UNION ALL
SELECT 'OFFERING_TYPE', PRODUCT_OFFERING_TYPE_VALUE, COUNT(*)
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION GROUP BY PRODUCT_OFFERING_TYPE_VALUE
UNION ALL
SELECT 'CURRENCY_CODE', CURRENCY_CODE, COUNT(*)
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION GROUP BY CURRENCY_CODE
ORDER  BY 1, 3 DESC;

-- ---------- E. FILL (which projected columns will actually carry data) -----
-- N-E1. Spine fill.
SELECT COUNT(*) AS TXNS_, COUNT(DEAL_TRANSACTION_ID) AS HAS_DEAL_TXN_, COUNT(SYNDICATE_DEAL_NAME) AS HAS_NAME_,
       COUNT(DEAL_SIZE) AS HAS_SIZE_, COUNT(ISSUER_TICKER) AS HAS_TICKER_, COUNT(ISSUER_INDUSTRY_SECTOR) AS HAS_SECTOR_,
       COUNT(PRODUCT_EQUITY_TYPE_VALUE) AS HAS_EQTYPE_, COUNT(PRODUCT_OFFERING_TYPE_VALUE) AS HAS_OFFTYPE_,
       COUNT(CURRENCY_CODE) AS HAS_CCY_
FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION;

-- N-E2. Order fill (the columns the order branch projects).
SELECT COUNT(*) AS ORDERS_, COUNT(EXT_INV_CD) AS HAS_GPNUM_, COUNT(INST_ALLOC_SIZE) AS HAS_ALLOC_,
       COUNT(ISS_ID) AS HAS_ISS_, COUNT(TRN_ID) AS HAS_TRN_, COUNT(DELETED_IND) AS HAS_DELETED_IND_
FROM   DGSTREAM.IPREO_ORDER;

-- N-E3. Investor identity on IPREO_ORDER — name / id / region / category
--       columns (by name), so the order branch can fill the investor block.
SELECT column_name, data_type
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM' AND table_name = 'IPREO_ORDER'
AND   (column_name LIKE '%INV%' OR column_name LIKE '%NAME%' OR column_name LIKE '%REGION%'
       OR column_name LIKE '%COUNTRY%' OR column_name LIKE '%TYPE%' OR column_name LIKE '%CATEG%'
       OR column_name LIKE '%SALES%' OR column_name LIKE '%ALLOC%' OR column_name LIKE '%DEMAND%'
       OR column_name LIKE '%QTY%' OR column_name LIKE '%AMT%' OR column_name LIKE '%TS' OR column_name LIKE '%DATE%')
ORDER  BY column_name;

-- N-E4. Tranche attributes on IPREO_TRANCHE (name / size / pricing / currency /
--       identifiers), by name.
SELECT column_name, data_type
FROM   all_tab_columns
WHERE  owner = 'DGSTREAM' AND table_name = 'IPREO_TRANCHE'
ORDER  BY column_id;

-- N-E5. IOI table fill and scale.
SELECT COUNT(*) AS IOI_ROWS_, COUNT(IOI_QTY) AS HAS_QTY_, COUNT(IOI_AMT) AS HAS_AMT_,
       COUNT(CASE WHEN IOI_QTY <> ROUND(IOI_QTY, 4) THEN 1 END) AS QTY_GT4DP_,
       MAX(IOI_QTY) AS MAX_QTY_, MAX(IOI_AMT) AS MAX_AMT_
FROM   DGSTREAM.IPREO_ORDERIOI;

-- ---------- F. EXCLUSIONS (so Ipreo counts mean what OPUS counts mean) ------
-- N-F1. Deals the execution-status rule would drop, and deals with NO status
--       row at all (an INNER JOIN to status drops those — the OPUS branch does).
SELECT (SELECT COUNT(DISTINCT T.ECM_TRANSACTION_ID) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T) AS TXNS_,
       (SELECT COUNT(DISTINCT T.ECM_TRANSACTION_ID) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION T
         WHERE NOT EXISTS (SELECT 1 FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_STATUS S
                           WHERE S.ECM_TRANSACTION_ID = T.ECM_TRANSACTION_ID AND S.STATUS_TYPE = 'Execution_Status')) AS TXNS_WITHOUT_STATUS_,
       (SELECT COUNT(DISTINCT S.ECM_TRANSACTION_ID) FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION_STATUS S
         WHERE S.STATUS_TYPE = 'Execution_Status'
         AND   S.STATUS_VALUE IN ('Confidential', 'Withdrawn', 'Terminated')) AS TXNS_EXCLUDED_
FROM   DUAL;

-- N-F2. Orders the DELETED_IND rule drops vs keeps.
SELECT DELETED_IND, COUNT(*) AS ORDERS_, COUNT(DISTINCT ISS_ID) AS ISSUES_
FROM   DGSTREAM.IPREO_ORDER GROUP BY DELETED_IND;

-- ---------- G. OVERLAP (the same deal in both ECM sources) ------------------
-- N-G1. Ipreo transactions that also exist in the current OPUS ECM spine.
SELECT COUNT(*) AS IPREO_TXNS_ALSO_IN_OPUS_
FROM  (SELECT DISTINCT DEAL_TRANSACTION_ID FROM DGSTREAM.IPREO_OPUS_ECM_TRANSACTION
       WHERE DEAL_TRANSACTION_ID IS NOT NULL) I
WHERE  EXISTS (SELECT 1 FROM DGSTREAM.OPUS_ECM_TRANSACTION T WHERE T.DEAL_TRANSACTION_ID = I.DEAL_TRANSACTION_ID);

-- N-G2. Ipreo ORDERS whose order id also exists in OB_ECM_ORDER (same book
--       loaded twice?) and Ipreo order ids that match OB_ECM_ORDER's
--       IPREO_EXTERNAL_ORDER_ID (the existing feed already carries them?).
SELECT (SELECT COUNT(*) FROM DGSTREAM.IPREO_ORDER O
         WHERE EXISTS (SELECT 1 FROM DGSTREAM.OB_ECM_ORDER E WHERE E.ORDER_ID = TO_CHAR(O.ORD_ID))) AS SAME_ORDER_ID_,
       (SELECT COUNT(*) FROM DGSTREAM.IPREO_ORDER O
         WHERE EXISTS (SELECT 1 FROM DGSTREAM.OB_ECM_ORDER E WHERE E.IPREO_EXTERNAL_ORDER_ID = TO_CHAR(O.ORD_ID))) AS MATCHES_EXTERNAL_ID_
FROM   DUAL;

-- N-G3. Ten overlapping deals side by side (name, size, order counts in each
--       source) — decides "OPUS wins" vs "Ipreo wins" vs "show both".
SELECT *
FROM  (SELECT I.DEAL_TRANSACTION_ID,
              MAX(I.SYNDICATE_DEAL_NAME) AS IPREO_NAME, MAX(I.DEAL_SIZE) AS IPREO_SIZE,
              (SELECT MAX(T.SYNDICATE_DEAL_NAME) FROM DGSTREAM.OPUS_ECM_TRANSACTION T
                WHERE T.DEAL_TRANSACTION_ID = I.DEAL_TRANSACTION_ID) AS OPUS_NAME,
              (SELECT MAX(T.DEAL_SIZE) FROM DGSTREAM.OPUS_ECM_TRANSACTION T
                WHERE T.DEAL_TRANSACTION_ID = I.DEAL_TRANSACTION_ID) AS OPUS_SIZE,
              (SELECT COUNT(*) FROM DGSTREAM.OB_ECM_ORDER E WHERE E.DEAL_ID = I.DEAL_TRANSACTION_ID) AS OPUS_ORDERS,
              (SELECT COUNT(*) FROM DGSTREAM.IPREO_ORDER O WHERE TO_CHAR(O.ISS_ID) = I.DEAL_TRANSACTION_ID) AS IPREO_ORDERS
       FROM   DGSTREAM.IPREO_OPUS_ECM_TRANSACTION I
       WHERE  I.DEAL_TRANSACTION_ID IS NOT NULL
       AND    EXISTS (SELECT 1 FROM DGSTREAM.OPUS_ECM_TRANSACTION T WHERE T.DEAL_TRANSACTION_ID = I.DEAL_TRANSACTION_ID)
       GROUP  BY I.DEAL_TRANSACTION_ID)
WHERE  ROWNUM <= 10;

-- ---------- H. STABILITY (the dedupe keys the branches will partition on) ---
-- N-H1. Within one ORD_ID, do ISS_ID / TRN_ID ever vary (if yes, a widened
--       PARTITION BY would split the order — the 2026-09-02 lesson)?
SELECT COUNT(*) AS ORDERS_WITH_VARYING_PARENTS
FROM  (SELECT ORD_ID FROM DGSTREAM.IPREO_ORDER
       GROUP  BY ORD_ID HAVING COUNT(DISTINCT ISS_ID) > 1 OR COUNT(DISTINCT TRN_ID) > 1);

-- N-H2. NULL keys (a NULL id forms one invisible group in a GROUP BY census).
SELECT SUM(CASE WHEN ORD_ID IS NULL THEN 1 ELSE 0 END) AS NULL_ORD_,
       SUM(CASE WHEN TRN_ID IS NULL THEN 1 ELSE 0 END) AS NULL_TRN_,
       SUM(CASE WHEN ISS_ID IS NULL THEN 1 ELSE 0 END) AS NULL_ISS_
FROM   DGSTREAM.IPREO_ORDER;

-- N-H3. Versioning on the Ipreo OPUS spine: rows per ECM_TRANSACTION_ID and
--       whether a version/published column exists to order the dedupe.
SELECT column_name FROM all_tab_columns
WHERE  owner = 'DGSTREAM' AND table_name = 'IPREO_OPUS_ECM_TRANSACTION'
AND   (column_name LIKE '%VERSION%' OR column_name LIKE '%PUBLISH%' OR column_name LIKE '%UPDATED%' OR column_name LIKE '%_TS')
ORDER  BY column_name;


-- ===========================================================================
-- L. 2026-09-21 — DCM ORDER STATUS CODES. Census K found the DCM order status
-- is a workflow code (XB 1.9M, B 1.6M, NEW, UPDATED, NULL 120k, D 96k, R, FR,
-- PN, A, F, XR) beside the plain DELETED / CANCELLED. The exclusion rule cannot
-- ship until D (deleted?), XB/XR (cancelled?) are decoded. UAT. Screenshot.
-- ===========================================================================

-- L1. What the codes look like in practice: per code, the share of orders that
--     carry a size row, an allocation, and whether the row is flagged active.
SELECT UPPER(O.STATUS) AS STATUS_, COUNT(*) AS ORDERS_,
       SUM(CASE WHEN O.FINAL_ALLOC > 0 THEN 1 ELSE 0 END) AS WITH_ALLOC_,
       SUM(CASE WHEN Z.ORDER_ID IS NOT NULL THEN 1 ELSE 0 END) AS WITH_SIZE_,
       MIN(O.PUBLISHED_TS) AS FIRST_SEEN_, MAX(O.PUBLISHED_TS) AS LAST_SEEN_
FROM   DGSTREAM.OB_ORDER O
LEFT JOIN (SELECT DISTINCT ORDER_ID FROM DGSTREAM.OB_ORDER_SIZE) Z ON Z.ORDER_ID = O.ORDER_ID
GROUP  BY UPPER(O.STATUS) ORDER BY ORDERS_ DESC;

-- L2. Do codes co-occur with the plain words on the same deal (a status
--     lifecycle, or two feeds)? Source system per code.
SELECT UPPER(STATUS) AS STATUS_, SOURCE_SYSTEM, ITEM_SOURCE, COUNT(*) AS ORDERS_
FROM   DGSTREAM.OB_ORDER
GROUP  BY UPPER(STATUS), SOURCE_SYSTEM, ITEM_SOURCE
ORDER  BY ORDERS_ DESC FETCH FIRST 30 ROWS ONLY;

-- L3. Ask the feed owner (no SQL): the meaning of XB, B, D, R, FR, PN, A, F, XR
--     and whether NULL status = live. Until answered the rule excludes ONLY the
--     spelled-out DELETED / CANCELLED on DCM orders.
