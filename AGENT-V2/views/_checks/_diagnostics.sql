-- ===========================================================================
-- FINAL VALIDATION — 3 queries. Everything else is answered.
-- If all three PASS, the four view files in this folder are ready to hand to
-- the data team. Send the numbers, or any ORA- error verbatim.
-- ===========================================================================


-- ===========================================================================
-- V25  DCM TRANCHE_SIZE conversion
-- PASS = e_notation_converted 43 · still_unconvertible 1 · max_size in the
--        tens of billions (not 0, not an error)
-- ===========================================================================
SELECT COUNT(*)                                                        AS non_null_rows,
       COUNT(CASE WHEN REGEXP_LIKE(TRANCHE_SIZE,
               '^\s*[+-]?[0-9]+(\.[0-9]+)?([Ee][+-]?[0-9]+)?\s*$')
                   AND NOT REGEXP_LIKE(TRANCHE_SIZE, '^\s*-?[0-9]+(\.[0-9]+)?\s*$')
                  THEN 1 END)                                          AS e_notation_converted,
       COUNT(CASE WHEN NOT REGEXP_LIKE(TRANCHE_SIZE,
               '^\s*[+-]?[0-9]+(\.[0-9]+)?([Ee][+-]?[0-9]+)?\s*$')
                  THEN 1 END)                                          AS still_unconvertible,
       MAX(CASE WHEN REGEXP_LIKE(TRANCHE_SIZE,
               '^\s*[+-]?[0-9]+(\.[0-9]+)?([Ee][+-]?[0-9]+)?\s*$')
                THEN TO_NUMBER(TRIM(TRANCHE_SIZE)) END)                AS max_size
FROM   DGSTREAM.OB_DEAL_TRANCHE
WHERE  TRANCHE_SIZE IS NOT NULL;


-- ===========================================================================
-- V26  ECM tranche grain (was 33,011 vs 33,010)
-- PASS = rows_ equals tranches_ equals 33,010
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
                   ROW_NUMBER() OVER (PARTITION BY ETX.DEAL_TRANSACTION_ID,
                                                   TTR.ECM_TRANSACTION_TRANCHE_ID
                                      ORDER BY TTR.ROWID) AS RN_
            FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TTR
            JOIN (SELECT DISTINCT ECM_TRANSACTION_ID, DEAL_TRANSACTION_ID
                  FROM DGSTREAM.OPUS_ECM_TRANSACTION) ETX
              ON ETX.ECM_TRANSACTION_ID = TTR.ECM_TRANSACTION_ID
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
-- V27  DCM tranche grain (was 36,371 vs 36,370)
-- PASS = rows_ equals tranches_ equals 36,370
-- ===========================================================================
SELECT COUNT(*) AS rows_,
       COUNT(DISTINCT DEAL_ID || '~' || TRANCHE_ID) AS tranches_
FROM (
    SELECT ODT.DEAL_ID, ODT.TRANCHE_ID
    FROM (
        SELECT V.* FROM (
            SELECT DTR.DEAL_ID, DTR.TRANCHE_ID,
                   ROW_NUMBER() OVER (PARTITION BY DTR.DEAL_ID, DTR.TRANCHE_ID
                                      ORDER BY DTR.ROWID) AS RN_
            FROM DGSTREAM.OB_DEAL_TRANCHE DTR
        ) V WHERE V.RN_ = 1
    ) ODT
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
