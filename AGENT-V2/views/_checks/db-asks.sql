-- ===========================================================================
-- DB ASKS — only what still has to run. SELECTs only, never session settings.
-- Screenshot results into ~/Desktop/ADK. Closed rounds live in git history.
-- ===========================================================================

-- AG / AH answered (UAT 2026-10-19): DEMAND_QTY is never the sum; the 1,566
-- 'other' scaled orders are CURRENCY / PERCENT bids where DEMAND_QTY is the
-- share-equivalent — correct. The ladder now shows the bid's unit and decimals.

-- AL answered (UAT 2026-10-23): broker table columns exist and resolve every top
-- code (CITIUSA -> Citigroup Global Markets Inc.); the issuer regex strips only
-- deal-type suffixes; Ipreo IOI_QTY is the share / bond equivalent for every unit
-- (0 when never converted). No grant to DGSTREAM on the DGLOBE table and none
-- will be given — the view now carries a maintained code -> name list instead.
-- OPTIONAL AM: every Ipreo billed-by code with its reference name, to extend it.
SELECT R.BILLED_BY_BRK_CD AS CODE_, MAX(B.EXTERNAL_BROKER_NAME) AS NAME_, COUNT(*) AS ORDERS_
FROM   DGSTREAM.IPREO_ORDER R
LEFT JOIN DGLOBE.CMNSYNDREF_EXTERNAL_BROKER B
       ON UPPER(TRIM(B.EXTERNAL_BROKER_CODE)) = UPPER(TRIM(R.BILLED_BY_BRK_CD))
WHERE  R.BILLED_BY_BRK_CD IS NOT NULL
GROUP  BY R.BILLED_BY_BRK_CD
ORDER  BY ORDERS_ DESC
OFFSET 15 ROWS FETCH NEXT 50 ROWS ONLY;

-- AFTER the deploy (not before): deploy-check A0 + A (A01 43 / A02 89 / A03 73)
-- + D-ECM, and time K3 — the investor-name block (CN) aggregates the whole
-- Ipreo order table on every Ipreo query; K3 was sub-second before.

-- AK answered (UAT 2026-10-23): Source = OB_ECM_ORDER.SOURCE (ONEBOOK = '1B',
-- ISN, CMG, SALES, DA); Indication USD = cash amount / quantity x USD limit;
-- RELATIVE_INDICATION empty. Both now view columns.

-- Deploy vw_order_detail (ladder largest-first, wider number masks,
-- ORDER_SOURCE, INDICATION_USD), then deploy-check A0 + A (A03 = 73) + D-ECM.
