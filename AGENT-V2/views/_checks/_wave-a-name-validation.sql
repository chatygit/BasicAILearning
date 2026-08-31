-- ===========================================================================
-- WAVE-A NAME VALIDATION (2026-08-28) — run BEFORE handing release 3 over.
-- Each statement compiles only if EVERY new source column name is exactly
-- right (WHERE 1=0 = zero cost, instant ORA-00904 on any typo — the PCM
-- lesson, applied preemptively). All three must return "no rows selected".
-- Note: SELLING_CONSESSION_FEE is the SOURCE's own spelling (sic) — the
-- view aliases it to SELLING_CONCESSION_FEE.
-- ===========================================================================

SELECT COUPON, YIELD, PRICE, PRICE_GUIDANCE, ORDER_BOOK_SIZE_USD,
       TOTAL_FEE, UNDERWRITING_FEE, MANAGEMENT_FEES, SELLING_CONSESSION_FEE,
       PRAECIPIUM_FEES, RETAIL_UW_FEE, ANNOUNCEMENT_DATE, ISSUE_DATE,
       TRADE_DATE, TARGET_MARKET, FRN_COUPON_INDEX
FROM   DGSTREAM.OB_DEAL_TRANCHE WHERE 1 = 0;

SELECT DEAL_FEE_MM, DEAL_FEE_CURRENCY, DEAL_SIZE_MM, DEAL_SIZE_CURRENCY
FROM   DGSTREAM.OPUS_BASE_TRANSACTION WHERE 1 = 0;

SELECT STATUS, QIB_STATUS, SUB_TYPE, IS_FIRM_ORDER, IS_POT, DRAFT_ALLOC,
       SOFT_ALLOC, ISN_ALLOC, RETENTION, RATIONALE, RATIONALE_TYPE,
       FX_CURRENCY, OBO_NAME, OBO_LEGAL_ENTITY_ID, ESG_TAG,
       ORDER_SIZE_CHANGE, IS_AFFILIATED, ONE_OFF_INVESTOR, SOEID
FROM   DGSTREAM.OB_ORDER WHERE 1 = 0;

SELECT INVESTOR_LEID FROM DGSTREAM.OB_ECM_ORDER WHERE 1 = 0;
