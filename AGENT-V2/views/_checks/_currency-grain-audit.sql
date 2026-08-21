-- ===========================================================================
-- CURRENCY GRAIN ASYMMETRY (PROD issue #2, 2026-08-21). Read-only audit —
-- views are FROZEN; the fix (if measurement warrants) ships in the next
-- planned release. Cause, from the shipped SQL: vw_deal_summary's ECM
-- CURRENCIES has the GLOBAL id->name fallback (GC join, round 2);
-- vw_tranche_summary.CURRENCY and vw_order_detail.CURRENCY are the bare
-- per-tranche TDC join — no global fallback, no raw-id last resort. So a
-- deal can list currencies while its tranches read NULL. DCM reads one
-- source column at both grains and should not show the asymmetry.
-- ===========================================================================

-- G1 — size the symptom in PROD: ECM tranches with NULL currency whose
--      deal-level list HAS values ( = rows the release fix would heal).
SELECT COUNT(*) AS ecm_tranches_null_ccy,
       COUNT(CASE WHEN D.CURRENCIES IS NOT NULL
                  THEN 1 END) AS deal_list_has_values
FROM   DGSTREAM.VW_TRANCHE_SUMMARY T
JOIN   DGSTREAM.VW_DEAL_SUMMARY D
       ON D.PRODUCT = 'ECM' AND D.DEAL_ID = T.DEAL_ID
WHERE  T.PRODUCT = 'ECM' AND T.CURRENCY IS NULL;

-- G2 — DCM control: expect ~0 (same source column at both grains).
SELECT COUNT(*) AS dcm_tranches_null_ccy,
       COUNT(CASE WHEN D.CURRENCIES IS NOT NULL
                  THEN 1 END) AS deal_list_has_values
FROM   DGSTREAM.VW_TRANCHE_SUMMARY T
JOIN   DGSTREAM.VW_DEAL_SUMMARY D
       ON D.PRODUCT = 'DCM' AND D.DEAL_ID = T.DEAL_ID
WHERE  T.PRODUCT = 'DCM' AND T.CURRENCY IS NULL;

-- RELEASE-TRAIN FIX (recorded, not applied): mirror the deal view's GC
-- global fallback into the tranche and order views' CURRENCY columns —
-- NVL(TDC.CURRENCY_NAME, GC.CURRENCY_NAME), raw id excluded at scalar
-- grain (a bare "4" as a row's currency is worse than NULL; the agent
-- renders NULL as "not recorded").
