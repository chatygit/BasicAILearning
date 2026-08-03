#!/usr/bin/env python3
"""Pre-promote regression suite for the ECM/DCM text2sql agent configs.

    python3 regression_check.py            # run everything
    python3 regression_check.py -v         # also list what passed

Exit 0 = safe to promote.  Exit 1 = a change would regress behavior we already fixed.

WHY THIS EXISTS
    Every layer we ship is text, but most of it is mechanically checkable. The
    regressions that actually bit us were all catchable here:
      - a rule written to fix bug X silently created its mirror (to-now windows
        admitted future-dated rows; "numbered lists" ate tables)
      - a prose rewrite deleted a concrete mapping the model depended on
        ("common stock -> EQUITY_TYPE" vanished during an axis-doctrine edit)
      - a doctrine lived in ONE layer, so skill-absent turns lost it (EXCHANGE)
      - a validator regex was evaded by a new SQL shape (NOT (x LIKE ...))
      - a generic rule rejected a specific defect with a misleading message,
        costing 3 retries (missing DGSTREAM prefix, quoted identifiers)

FOUR CHECK LAYERS
    1. STRUCTURE    files parse, every regex compiles, counts sane
    2. SQL CORPUS   every SQL shape we ever got wrong is still REJECTED - and by
                    the RIGHT rule (diagnosis, not just rejection); every
                    corrected shape still PASSES all rules
    3. INVARIANTS   load-bearing phrases still present; retired doctrines absent
    4. CROSS-LAYER  facts that must agree across skill / instruction / schema / domain

HOW TO EXTEND (do this with every fix, it is the whole point)
    Fixed a bad SQL shape?      add it to BAD_SQL with the rule keyword.
    Wrote a concrete mapping?   add the exact phrase to INVARIANTS.
    Overturned a doctrine?      add the old wording to RETIRED.
    Rule must hold everywhere?  add it to CROSS_LAYER.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
SKILL = DIR / "skill-v7.md"
INSTR = DIR / "agents-v6.yml"
DOMAIN = DIR / "domain-v4.yml"
SCHEMA = DIR / "vw_deal_order_summary-v3.json"
RULES = DIR / "sql-validation-v2.yml"
UNSUPPORTED = DIR / "unspported-v2.json"

VERBOSE = "-v" in sys.argv or "--verbose" in sys.argv

# ---------------------------------------------------------------------------
# 2. SQL CORPUS - shapes that broke production, and the shapes that fixed them
#    (name, sql, rule-name keyword expected to reject it)
# ---------------------------------------------------------------------------

V = "DGSTREAM.VW_DEAL_ORDER_SUMMARY"

BAD_SQL = [
    ("exchange-equality", f"SELECT DISTINCT DEAL_ID, DEAL_NAME FROM {V} WHERE PRODUCT = 'ECM' AND EXCHANGE = 'NYSE'", "EXCHANGE"),
    ("bnd-trailing-true", f"SELECT DISTINCT DEAL_ID FROM {V} WHERE PRODUCT = 'ECM' AND SYNDICATE_MEMBER_NAME LIKE '%CITIGROUP GLOBAL MARKETS% (TRUE)'", "true"),
    ("product-wrong-value", f"SELECT DISTINCT DEAL_ID FROM {V} WHERE PRODUCT = 'ADR'", "PRODUCT only"),
    ("quoted-dotted-view", "SELECT DISTINCT DEAL_ID FROM \"DGSTREAM.VW_DEAL_ORDER_SUMMARY\" WHERE PRODUCT = 'ECM'", "double-quote"),
    ("bare-string-date", f"SELECT DISTINCT DEAL_ID FROM {V} WHERE PRODUCT = 'ECM' AND PRICING_TS >= '2026-01-01' AND PRICING_TS < '2027-01-01'", "DATE keyword"),
    ("count-without-distinct", f"SELECT CURRENCY, COUNT(ORDER_ID) AS N FROM {V} WHERE PRODUCT = 'ECM' GROUP BY CURRENCY", "DISTINCT"),
    ("ecm-tranche-status", f"SELECT DISTINCT DEAL_ID FROM {V} WHERE PRODUCT = 'ECM' AND UPPER(TRANCHE_STATUS) = 'PRICED'", "DCM-only"),
    ("dcm-equity-type", f"SELECT DISTINCT DEAL_ID FROM {V} WHERE PRODUCT = 'DCM' AND UPPER(EQUITY_TYPE) = 'COMMON STOCK'", "ECM-only"),
    ("unquoted-deal-id", f"SELECT DISTINCT ORDER_ID FROM {V} WHERE PRODUCT IN ('ECM','DCM') AND DEAL_ID = 25248935", "quote the literal"),
    ("unquoted-gpnum", f"SELECT DISTINCT ORDER_ID FROM {V} WHERE PRODUCT = 'ECM' AND GPNUM = 01842", "quote the literal"),
    ("identifier-equality", f"SELECT DISTINCT DEAL_ID FROM {V} WHERE PRODUCT = 'DCM' AND IDENTIFIER_VALUE = '91282CEQ0'", "Identifier columns"),
    ("identifier-no-upper", f"SELECT DISTINCT DEAL_ID FROM {V} WHERE PRODUCT = 'DCM' AND IDENTIFIER_TYPE LIKE '%CUSIP%'", "UPPER"),
    ("unbounded-trailing-window", f"SELECT DISTINCT DEAL_ID FROM {V} WHERE PRODUCT = 'DCM' AND PRICING_TS >= ADD_MONTHS(SYSDATE, -12) AND UPPER(ISSUER_NAME) = 'TESLA INC'", "tomorrow-midnight"),
    ("deal-name-without-id", f"SELECT DISTINCT DEAL_NAME, ISSUER_NAME, DEAL_SIZE FROM {V} WHERE PRODUCT = 'DCM' ORDER BY DEAL_NAME", "DEAL_ID"),
    ("missing-schema-prefix", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM'", "schema prefix"),
    ("product-type-equality", f"SELECT DISTINCT DEAL_ID, DEAL_NAME FROM {V} WHERE PRODUCT = 'ECM' AND PRODUCT_TYPE = 'Common Stock'", "PRODUCT_TYPE"),
    ("whole-syndicate-negation", f"SELECT DISTINCT DEAL_ID, DEAL_NAME FROM {V} WHERE PRODUCT = 'ECM' AND UPPER(SYNDICATE_MEMBER_NAME) NOT LIKE '%CITIGROUP GLOBAL MARKETS%'", "NOT"),
    ("whole-syndicate-negation-wrapped", f"SELECT DISTINCT DEAL_ID, DEAL_NAME FROM {V} WHERE PRODUCT = 'ECM' AND (NOT (UPPER(SYNDICATE_MEMBER_NAME) LIKE '%CITIGROUP GLOBAL MARKETS%'))", "NOT"),
    ("no-product-filter", f"SELECT DISTINCT DEAL_ID, DEAL_NAME FROM {V} WHERE UPPER(SECTOR) = 'ENERGY'", "Product scope"),
    # --- mined from the failure log + per-rule sweep (workflow, 2026-08-03) ---
    ("count-id-no-distinct", "SELECT CURRENCY, COUNT(ORDER_ID) AS ORDER_COUNT, SUM(ALLOCATION) AS TOTAL_SHARES FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND UPPER(INVESTOR_REGION) NOT LIKE '%UNITED STATES%' GROUP BY CURRENCY ORDER BY ORDER_COUNT DESC", "DISTINCT"),
    ("quoted-dotted-view-name", "SELECT DISTINCT DEAL_ID, DEAL_NAME, PRICING_TS FROM \"DGSTREAM.VW_DEAL_ORDER_SUMMARY\" WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' FETCH FIRST 10 ROWS ONLY", "quote"),
    ("bare-string-timestamp", "SELECT DISTINCT DEAL_ID, DEAL_NAME, TRANCHE_NAME, PRICING_TS FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND PRICING_TS >= '2026-01-01' AND PRICING_TS < '2027-01-01' FETCH FIRST 20 ROWS ONLY", "Timestamp"),
    ("unquoted-numeric-deal-id", "SELECT ORDER_ID, INVESTOR_NAME, ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND DEAL_ID = 25248935 AND UPPER(TRANCHE_NAME) LIKE '%UNITED STATES%'", "TEXT"),
    ("negation-as-literal", "SELECT ORDER_ID, INVESTOR_NAME, INVESTOR_REGION, ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND INVESTOR_REGION = 'Non USA' FETCH FIRST 50 ROWS ONLY", "Negation"),
    ("fabricated-bond-columns", "SELECT DEAL_ID, DEAL_NAME, CUSIP, COUPON, MATURITY_DATE FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND CUSIP = '91282CEQ0'", "Fabricated"),
    ("exchange-ticker-equality", "SELECT DISTINCT DEAL_ID, DEAL_NAME, TICKER, EXCHANGE FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND EXCHANGE = 'NYSE' FETCH FIRST 25 ROWS ONLY", "EXCHANGE"),
    ("not-like-pipe-syndicate", "SELECT ORDER_ID, INVESTOR_NAME, ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND SYNDICATE_MEMBER_NAME NOT LIKE '%CITI%' FETCH FIRST 50 ROWS ONLY", "pipe-list"),
    ("not-outside-parens-evasion", "SELECT ORDER_ID, INVESTOR_NAME, ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND NOT (UPPER(SYNDICATE_MEMBER_NAME) LIKE '%CITI%') FETCH FIRST 50 ROWS ONLY", "pipe-list"),
    ("uncapped-broad-listing", "SELECT DISTINCT DEAL_ID, DEAL_NAME, TRANCHE_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' ORDER BY PRICING_TS DESC", "cap"),
    ("tranche-size-lexical-sort", "SELECT DISTINCT DEAL_ID, DEAL_NAME, TRANCHE_NAME, TRANCHE_SIZE FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND CURRENCY = 'USD' ORDER BY TRANCHE_SIZE DESC FETCH FIRST 10 ROWS ONLY", "TO_NUMBER"),
    ("tranche-status-on-ecm", "SELECT DISTINCT DEAL_ID, DEAL_NAME, TRANCHE_NAME, TRANCHE_STATUS FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND UPPER(TRANCHE_STATUS) = 'PRICED' FETCH FIRST 25 ROWS ONLY", "ECM-scoped"),
    ("legacy-solo-member-count", "SELECT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' GROUP BY DEAL_ID, DEAL_NAME HAVING COUNT(DISTINCT SYNDICATE_MEMBER_NAME) = 1 AND MAX(SYNDICATE_MEMBER_NAME) = 'Citi'", "solo"),
    ("cross-product-unit-mixing", "SELECT ISSUER_NAME, SUM(ALLOCATION) AS TOTAL FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT IN ('ECM','DCM') AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' GROUP BY ISSUER_NAME", "Quantity"),
    ("dml-appended-delete", "SELECT DISTINCT DEAL_ID FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM'; DELETE FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM'", "data modification"),
    ("select-star", "SELECT * FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND DEAL_ID = '25248935'", "wildcard"),
    ("union-all-two-products", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' UNION ALL SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM'", "injection"),
    ("to-char-year-filter", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND TO_CHAR(PRICING_TS,'YYYY') = '2025'", "TO_CHAR"),
    ("extract-year-filter", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND EXTRACT(YEAR FROM PRICING_TS) = 2025", "EXTRACT"),
    ("trunc-pricing-ts-filter", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND TRUNC(PRICING_TS) = DATE '2026-03-05'", "TRUNC"),
    ("issuer-deal-count-count-star", "SELECT ISSUER_NAME, COUNT(*) AS DEAL_COUNT FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2025-01-01' AND PRICING_TS < DATE '2026-01-01' GROUP BY ISSUER_NAME ORDER BY DEAL_COUNT DESC FETCH FIRST 10 ROWS ONLY", "deal-level aggregate"),
    ("ipo-listing-flattened", "SELECT DEAL_ID, DEAL_NAME, ISSUER_NAME, PRICING_TS FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND OFFERING_TYPE = 'IPO' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' FETCH FIRST 20 ROWS ONLY", "IPO listing"),
    ("ecm-deal-listing-flattened", "SELECT DEAL_ID, DEAL_NAME, PRICING_TS FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2026-07-01' FETCH FIRST 25 ROWS ONLY", "ECM/DCM deal listing"),
    ("investor-name-with-gfcid", "SELECT DISTINCT ORDER_ID, INVESTOR_NAME, ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND UPPER(INVESTOR_NAME) LIKE '%FIDELITY%' AND GFCID = '1234567'", "investor-name filter"),
    ("investor-sum-with-gfcid", "SELECT SUM(ALLOCATION) AS TOTAL_ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND GFCID = '9876543' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'", "investor-side aggregate"),
    ("bnd-broker-without-member-context", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND INSTR(BND_BROKER,'true') > 0 AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'", "B&D"),
    ("bnd-broker-equals-true", "SELECT DISTINCT DEAL_ID, DEAL_NAME, SYNDICATE_MEMBER_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND BND_BROKER = 'true' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'", "whole-field"),
    ("broker-ask-only-issuer-id", "SELECT DISTINCT DEAL_ID, DEAL_NAME, PRICING_TS, 'CITI' AS BROKER FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND GFCID = '1234567' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'", "rely only"),
    ("syndicate-member-equals-citi", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND SYNDICATE_MEMBER_NAME = 'Citi' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'", "brittle exact"),
    ("legacy-solo-distinct-member-count", "SELECT DEAL_ID, MAX(DEAL_NAME) AS DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' GROUP BY DEAL_ID HAVING COUNT(DISTINCT SYNDICATE_MEMBER_NAME) = 1 AND MAX(SYNDICATE_MEMBER_NAME) = 'Citi'", "legacy solo"),
    ("dcm-solo-broker-code-tokens", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND REGEXP_COUNT(NVL(BROKER_CODE,''),'\\|') = 0 AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'", "DCM solo"),
    ("dual-product-solo-broker-code", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT IN ('ECM','DCM') AND REGEXP_COUNT(NVL(BROKER_CODE,''),'\\|') = 0 AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'", "non-ECM scope"),
    ("narrow-pipe-anchor", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND REGEXP_LIKE(NVL(BROKER_CODE,''),'(^|\\|)CITI') AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'", "narrow"),
    ("connect-by-token-expansion", "SELECT DISTINCT DEAL_ID, TRIM(REGEXP_SUBSTR(BROKER_CODE,'[^|]+',1,LEVEL)) AS BROKER_TOKEN FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' CONNECT BY LEVEL <= REGEXP_COUNT(BROKER_CODE,'\\|') + 1", "CONNECT BY"),
    ("order-by-tranche-size-text", "SELECT DISTINCT DEAL_ID, DEAL_NAME, TRANCHE_SIZE FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND CURRENCY = 'USD' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' ORDER BY TRANCHE_SIZE DESC FETCH FIRST 10 ROWS ONLY", "TO_NUMBER"),
    ("dcm-sum-amt-mixed-currency", "SELECT INVESTOR_REGION, SUM(AMT) AS TOTAL_ORDERED FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND DEAL_ID = '25248935' GROUP BY INVESTOR_REGION", "currency scoping"),
    ("ecm-sum-amt", "SELECT SUM(AMT) AS TOTAL_INVESTED FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND GPNUM IN ('0001842') AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'", "AMT"),
    ("cross-product-allocation-sum", "SELECT DEAL_ID, SUM(ALLOCATION) AS TOTAL_ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT IN ('ECM','DCM') AND CURRENCY = 'USD' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' GROUP BY DEAL_ID FETCH FIRST 20 ROWS ONLY", "Quantity"),
    ("fill-rate-no-nullif", "SELECT DEAL_ID, SUM(ALLOCATION) / SUM(DEMAND_QTY) AS FILL_RATE FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND DEAL_ID = '25248935' GROUP BY DEAL_ID", "divide-by-zero"),
    ("self-join-two-deals", "SELECT DISTINCT A.DEAL_ID, A.DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY A JOIN DGSTREAM.VW_DEAL_ORDER_SUMMARY B ON A.GPNUM = B.GPNUM WHERE A.PRODUCT = 'ECM' AND A.DEAL_ID = '25248935' AND B.DEAL_ID = '25246247'", "self-join"),
    ("order-type-limit", "SELECT DISTINCT ORDER_ID, INVESTOR_NAME, ORDER_TYPE FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND DEAL_ID = '25248935' AND UPPER(ORDER_TYPE) LIKE '%LIMIT%'", "IOI_TYPE"),
    ("equity-type-or-product-type", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND (UPPER(EQUITY_TYPE) = 'COMMON STOCK' OR UPPER(PRODUCT_TYPE) LIKE '%COMMON%')", "never OR"),
    ("fabricated-cusip-column", "SELECT DISTINCT DEAL_ID, DEAL_NAME, CUSIP FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND CUSIP = '91282CEQ0'", "Fabricated"),
    ("negation-phrase-as-value", "SELECT DISTINCT DEAL_ID, DEAL_NAME, INVESTOR_REGION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND UPPER(INVESTOR_REGION) = 'NON-US' AND DEAL_ID = '25248935'", "Negation"),
]

GOOD_SQL = [
    ("deal-listing", f"SELECT DISTINCT DEAL_ID, DEAL_NAME, ISSUER_NAME, DEAL_STATUS FROM {V} WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2024-01-01' AND PRICING_TS < DATE '2025-01-01' ORDER BY DEAL_ID FETCH FIRST 20 ROWS ONLY"),
    ("bnd-index-recipe", f"SELECT DISTINCT DEAL_ID, DEAL_NAME, TRANCHE_ID, TRANCHE_NAME, PRICING_TS FROM {V} WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2024-01-01' AND PRICING_TS < DATE '2025-01-01' AND INSTR(BND_BROKER,'true') > 0 AND UPPER(TRIM(REGEXP_SUBSTR(SYNDICATE_MEMBER_NAME,'[^|]+',1,REGEXP_COUNT(SUBSTR(BND_BROKER,1,INSTR(BND_BROKER,'true')),'\\|')+1))) LIKE '%CITIGROUP GLOBAL MARKETS%' ORDER BY PRICING_TS DESC, DEAL_ID, TRANCHE_ID FETCH FIRST 20 ROWS ONLY"),
    ("bounded-trailing-window", f"SELECT DISTINCT DEAL_ID, DEAL_NAME FROM {V} WHERE PRODUCT = 'DCM' AND PRICING_TS >= ADD_MONTHS(SYSDATE, -12) AND PRICING_TS < TRUNC(SYSDATE) + 1 ORDER BY PRICING_TS DESC, DEAL_ID FETCH FIRST 20 ROWS ONLY"),
    ("identifier-lookup", f"SELECT DISTINCT DEAL_ID, DEAL_NAME, TRANCHE_NAME, IDENTIFIER_TYPE, IDENTIFIER_VALUE FROM {V} WHERE PRODUCT = 'DCM' AND UPPER(IDENTIFIER_TYPE) LIKE '%CUSIP%' AND UPPER(IDENTIFIER_VALUE) LIKE '%91282CEQ0%' ORDER BY DEAL_ID FETCH FIRST 20 ROWS ONLY"),
    ("investor-having-count", f"SELECT GPNUM, INVESTOR_NAME, COUNT(DISTINCT DEAL_ID) AS DEAL_COUNT FROM {V} WHERE PRODUCT = 'ECM' GROUP BY GPNUM, INVESTOR_NAME HAVING COUNT(DISTINCT DEAL_ID) > 5 ORDER BY DEAL_COUNT DESC FETCH FIRST 20 ROWS ONLY"),
    ("equity-type-class-word", "SELECT DEAL_ID, DEAL_NAME, MAX(ISSUER_NAME) AS ISSUER_NAME, COUNT(DISTINCT TRANCHE_ID) AS TRANCHE_COUNT, MIN(PRICING_TS) AS FIRST_PRICED FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND UPPER(SECTOR) = 'ENERGY' AND UPPER(EQUITY_TYPE) = 'COMMON STOCK' AND UPPER(OFFERING_TYPE) = 'FO' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2026-04-01' GROUP BY DEAL_ID, DEAL_NAME ORDER BY FIRST_PRICED DESC, DEAL_ID FETCH FIRST 10 ROWS ONLY"),
    ("quoted-schema-and-view", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM \"DGSTREAM\".\"VW_DEAL_ORDER_SUMMARY\" WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2024-01-01' ORDER BY DEAL_ID FETCH FIRST 20 ROWS ONLY"),
    # doctrine evolved 2026-07-31: abbreviations MAY be stored, so the OR-both form is now correct
    ("exchange-or-both-tokens", f"SELECT DISTINCT DEAL_ID, DEAL_NAME FROM {V} WHERE PRODUCT = 'ECM' AND (UPPER(EXCHANGE) LIKE '%NYSE%' OR UPPER(EXCHANGE) LIKE '%NEW YORK%') ORDER BY DEAL_ID FETCH FIRST 20 ROWS ONLY"),
    ("orders-for-deal", f"SELECT DISTINCT ORDER_ID, INVESTOR_NAME, GPNUM, TRANCHE_NAME, ALLOCATION, DEMAND_QTY FROM {V} WHERE PRODUCT = 'ECM' AND DEAL_ID = '25246247' ORDER BY ORDER_ID FETCH FIRST 20 ROWS ONLY"),
    # --- mined from the failure log + per-rule sweep (workflow, 2026-08-03) ---
    ("breakdown-dedupe-inside", "SELECT CURRENCY, COUNT(*) AS ORDER_COUNT, SUM(ALLOCATION) AS TOTAL_SHARES FROM (SELECT DISTINCT ORDER_ID, DEAL_ID, CURRENCY, ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND UPPER(INVESTOR_REGION) NOT LIKE '%UNITED STATES%') GROUP BY CURRENCY ORDER BY ORDER_COUNT DESC"),
    ("non-citi-bnd-index", "SELECT ORDER_ID, INVESTOR_NAME, ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND INSTR(BND_BROKER, 'true') > 0 AND UPPER(TRIM(REGEXP_SUBSTR(SYNDICATE_MEMBER_NAME, '[^|]+', 1, REGEXP_COUNT(SUBSTR(BND_BROKER, 1, INSTR(BND_BROKER, 'true')), '\\|') + 1))) NOT LIKE '%CITI%' FETCH FIRST 50 ROWS ONLY"),
    ("paging-page-two", "SELECT DISTINCT DEAL_ID, DEAL_NAME, TRANCHE_NAME, PRICING_TS FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' ORDER BY PRICING_TS DESC OFFSET 20 ROWS FETCH NEXT 20 ROWS ONLY"),
    ("investor-family-by-name", "SELECT DISTINCT DEAL_ID, DEAL_NAME, GPNUM, INVESTOR_NAME, ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND UPPER(INVESTOR_NAME) LIKE '%MILLENNIUM MANAGEMENT%' FETCH FIRST 50 ROWS ONLY"),
    ("meeting-other-than-1x1", "SELECT ORDER_ID, INVESTOR_NAME, MEETING_TYPE, ALLOCATION FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND DEAL_ID = '25246247' AND MEETING_TYPE NOT IN ('1x1', 'No Meeting')"),
    ("deal-count-deduped-subquery", "SELECT ISSUER_NAME, COUNT(*) AS DEAL_COUNT FROM (SELECT DISTINCT DEAL_ID, ISSUER_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND PRICING_TS >= DATE '2025-01-01' AND PRICING_TS < DATE '2026-01-01') GROUP BY ISSUER_NAME ORDER BY DEAL_COUNT DESC FETCH FIRST 10 ROWS ONLY"),
    ("ipo-listing-deduped", "SELECT DEAL_ID, DEAL_NAME, MAX(ISSUER_NAME) AS ISSUER_NAME, COUNT(DISTINCT TRANCHE_ID) AS TRANCHE_COUNT, MIN(PRICING_TS) AS FIRST_PRICED FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND UPPER(OFFERING_TYPE) = 'IPO' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' GROUP BY DEAL_ID, DEAL_NAME ORDER BY FIRST_PRICED DESC, DEAL_ID FETCH FIRST 20 ROWS ONLY"),
    ("investor-aggregate-by-gpnum", "SELECT SUM(ALLOCATION) AS TOTAL_ALLOCATION, COUNT(DISTINCT ORDER_ID) AS ORDER_COUNT FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND GPNUM IN ('0001842','0009911') AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01'"),
    ("wide-pipe-anchor-broker-match", "SELECT DISTINCT DEAL_ID, DEAL_NAME, BROKER_CODE FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND REGEXP_LIKE(NVL(BROKER_CODE,''),'(^| \\| )CITI( \\| |$)') AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' ORDER BY PRICING_TS DESC, DEAL_ID FETCH FIRST 20 ROWS ONLY"),
    ("ecm-solo-broker-token", "SELECT DISTINCT DEAL_ID, DEAL_NAME FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND REGEXP_COUNT(NVL(BROKER_CODE,''),'\\|') = 0 AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' ORDER BY PRICING_TS DESC, DEAL_ID FETCH FIRST 20 ROWS ONLY"),
    ("dcm-sum-grouped-by-currency", "SELECT CURRENCY, SUM(AMT) AS TOTAL_ORDERED FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND DEAL_ID = '25248935' GROUP BY CURRENCY ORDER BY TOTAL_ORDERED DESC"),
    ("tranche-size-to-number-ranked", "SELECT DISTINCT DEAL_ID, DEAL_NAME, TRANCHE_ID, TRANCHE_NAME, TO_NUMBER(TRANCHE_SIZE DEFAULT NULL ON CONVERSION ERROR) AS TRANCHE_SIZE_NUM FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'DCM' AND CURRENCY = 'USD' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' ORDER BY TRANCHE_SIZE_NUM DESC NULLS LAST, DEAL_ID FETCH FIRST 10 ROWS ONLY"),
    ("fill-rate-with-nullif", "SELECT DEAL_ID, SUM(ALLOCATION) / NULLIF(SUM(DEMAND_QTY), 0) AS FILL_RATE FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT = 'ECM' AND DEAL_ID = '25248935' GROUP BY DEAL_ID"),
    ("cross-product-grouped-by-product", "SELECT PRODUCT, DEAL_ID, SUM(ALLOCATION) AS TOTAL FROM DGSTREAM.VW_DEAL_ORDER_SUMMARY WHERE PRODUCT IN ('ECM','DCM') AND CURRENCY = 'USD' AND PRICING_TS >= DATE '2026-01-01' AND PRICING_TS < DATE '2027-01-01' GROUP BY PRODUCT, DEAL_ID FETCH FIRST 20 ROWS ONLY"),
]

# ---------------------------------------------------------------------------
# 3. INVARIANTS - concrete, load-bearing text a tidy-up must never delete
#    (file, exact substring, what it guards)
# ---------------------------------------------------------------------------

INVARIANTS = [
    (SKILL, "CLASS-WORD MAP", "common stock -> EQUITY_TYPE routing (regressed 2026-08-03)"),
    (SKILL, "DGSTREAM.VW_DEAL_ORDER_SUMMARY", "schema-qualified table doctrine"),
    (SKILL, "TRUNC(SYSDATE) + 1", "trailing windows exclude future-dated rows"),
    (SKILL, "ALWAYS quote id literals", "ids are TEXT -> ORA-01722"),
    (SKILL, "DISPLAYED-RESULT REFERENCE", "no re-search of a row we displayed"),
    (SKILL, "Insights & Trends", "analyst-style answer section"),
    (SKILL, "quantitative brief", "answers lead with numbers, not enumeration"),
    (SKILL, "Executive Summary", "house reply anatomy"),
    (SKILL, "hand-summed", "no stats from the 20-row sample"),
    (SKILL, "COLUMN-ADD", "follow-ups keep rows/order and append columns"),
    (SKILL, "(true)", "B&D flag lives inside the member token"),
    (SKILL, "never split a pipe-delimited value across table columns", "identifier smear bug"),
    (SKILL, "Never render the executor's sample", "sample is not the full result"),
    (SKILL, "must NEVER DELETE the ask's defining condition", "retry must not drop the filter"),
    (SKILL, "IDS HAVE EXACTLY TWO SOURCES", "no fabricated ids on tool failure"),
    (INSTR, "FEWEST HOPS", "no entity_search for metric asks"),
    (INSTR, "ENTITLEMENT SCOPE IS A SQL CONSTRAINT", "no unentitled PRODUCT branches"),
    (INSTR, "NUMBERED", "choices are numbered lists"),
    (INSTR, "row_count describes THE PAGE", "paging termination law"),
    (INSTR, "never as per-cell tags", "units live in column headers"),
    (INSTR, "${current_datetime}", "date anchor field"),
    (DOMAIN, "DOMAIN_QUERY_LIBRARY", "pre-verified query library"),
    (DOMAIN, "TRUNC(SYSDATE) + 1", "trailing-window bound in the per-query layer"),
    (DOMAIN, "DEAL_SHARING_TYPE", "solo route"),
    (SCHEMA, "DEAL_SHARING_TYPE", "column present in schema"),
    (SCHEMA, "SETTLEMENT_CURRENCY", "column present in schema"),
    (SCHEMA, "TRANCHE_STATUS", "column present in schema"),
    # --- mined from the failure log + per-rule sweep (workflow, 2026-08-03) ---
    (SKILL, "Order counts = COUNT(DISTINCT ORDER_ID) everywhere", "User confirmation 2026-07-28 overturned the 'ORDER_ID is DCM-only' team doc; ECM order cou"),
    (INSTR, "status=ambiguous on a METRIC/LIST ask", "Verified live at agents-v6.yml:75; stops the agent dead-ending a metric ask with a disambi"),
    (SCHEMA, "coverage/fill ratios are ECM-only", "VERIFIED present 1x (DEMAND_QTY, line 192). DCM DEMAND_QTY = ALLOCATION = AMT (all OZ.AMT)"),
    (DOMAIN, "DOMAIN_PRODUCT_ENTITLEMENT_CLAUSE", "Verified live at domain-v4.yml:69; template variable the preflight hook injects entitled p"),
    (SKILL, "PRICING_TS and CURRENCY VARY PER TRANCHE", "VERIFIED present 1x (skill-v7.md:51). Trace 94b25ec2: Dare-Beer deal appeared twice in a d"),
    (SKILL, "REGEXP_COUNT(SUBSTR(BND_BROKER, 1, INSTR", "The position-index recipe that identifies the actual B&D bank on ECM; without it 'billed b"),
    (SKILL, "UPPER(DEAL_SHARING_TYPE)='SOLO' ALONE", "User ruling 2026-07-30: view is Citi's own book, so adding a syndicate-member filter to 's"),
    (SKILL, "TO_NUMBER(TRANCHE_SIZE DEFAULT NULL", "TRANCHE_SIZE is TEXT; the ON CONVERSION ERROR form is the only safe cast for ranking/summi"),
    (INSTR, "you MUST call text2sql_data_context", "Without it the agent presents the 5-20 row sample_data as the full result set \u2014 the silent"),
    (INSTR, "transient platform registry issue", "Verified live at agents-v6.yml:202; without it the agent treats 'Tool not found' as a wron"),
    (SKILL, "fixed-to-floating\u2192'Fixed to FRN'", "COUPON_TYPE is matched with = on exact stored values; the user phrase never matches withou"),
    (DOMAIN, "DEFAULT NULL ON CONVERSION ERROR", "TRANCHE_SIZE is TEXT; without the guarded TO_NUMBER, ranking/summing sorts lexically or bl"),
    (SKILL, "UPPER(DEAL_SHARING_TYPE)='SOLO'", "Primary solo route for both products; the old syndicate-member workaround produced wrong/z"),
    (INSTR, "UNITS LIVE IN THE COLUMN HEADER", "Verified live at agents-v6.yml:175; QA ruling on shares-vs-currency labelling, without it "),
    (SCHEMA, "NEVER exact '=' on this column", "VERIFIED present 1x (PRODUCT_TYPE, line 210). QA#5: messy label variants ('Common Shares',"),
    (INSTR, "gpnum IS a supported parameter", "Verified live at agents-v6.yml:98; counters the stale 'gpnum not accepted' belief that mak"),
    (SKILL, "\"free to trade\"\u2192'FREETOTRADE'", "Spaced user phrase vs the camelCase stored literal freeToTrade; the mapping is the only br"),
    (INSTR, "HARD CAP: 2 executor attempts", "Removing the cap reintroduces retry-storm traces where the agent loops on validation error"),
    (DOMAIN, "entity_search is NON-terminal", "Guards traces where the agent stopped at resolution output and returned an entity list as "),
    (SCHEMA, "never OR'd with PRODUCT_TYPE", "VERIFIED present 1x (EQUITY_TYPE, line 222). 'American Depositary deals' trace produced a "),
    (SKILL, "'%M & A%' OR '%ACQUISITION%'", "M&A/buyout asks need the OR across two overlapping USE_OF_PROCEEDS values or 'Future Acqui"),
    (SKILL, "exactly these 5 subsidiaries", "Numeric definition of 'Citi'; dropping it re-admits CITIBANK / 'Citi (Test Syndicate CMG)'"),
    (INSTR, "Always pass domain=\"ecm_dcm\"", "Without the domain arg every text2sql_* call resolves the wrong/no domain config and silen"),
    (SKILL, "UPPER(DEAL_STATUS) = 'OPEN'", "DEAL_STATUS holds both 'Open' and 'OPEN'; plain = 'Open' silently under-counts (skill-v7.m"),
    (SKILL, "UPPER(col) = UPPER('value')", "General case-insensitive comparison rule for all coded columns with inconsistent DB casing"),
    (SKILL, "ECM \u2192 ALLOCATION, DCM \u2192 AMT", "AMT is DCM-only money; SUM(AMT) on ECM 'how much did X invest' returns near-empty totals ("),
    (SKILL, "CITIUSA, CITIAUS, CITIASIA", "The enumerated Citi BROKER_CODE set that backs every Citi B&D / non-B&D query."),
    (INSTR, "HARD GATE: never write SQL", "Guards query_context-before-SQL flow; dropping it lets the agent hallucinate table/column "),
    (INSTR, "render as a markdown TABLE", "Verified live at agents-v6.yml:171; data rows otherwise regress to numbered lists with sub"),
    (SKILL, "'%REPAY%' OR '%REFINANC%'", "Dictionary audit 2026-07-30: the old '%DEBT REPAY%' pattern cannot match DCM's stored 'Rep"),
    (SKILL, "'Conv. Bond', 'Conv. Pfd'", "Abbreviated PRODUCT_TYPE literals with periods; the named-column route for 'product type c"),
    (SKILL, "NULLIF(SUM(DEMAND_QTY),0)", "Fill-rate/coverage divisions error on zero demand without the NULLIF guard."),
    (DOMAIN, "NEVER filter the investor", "Filtering the investor in WHERE makes share-of-book always 100% \u2014 a silently wrong number "),
    (DOMAIN, "Explicit-identifier guard", "Without it a zero-row explicit DEAL_ID/GPNUM silently gets fuzzy-substituted with a differ"),
    (SKILL, "jpmorgan\u2192JPMSEC/JPMORSEC", "Concrete BROKER_CODE mapping for a non-Citi bank; without it the model guesses codes (fabr"),
    (SKILL, "'Exchangable Notes' (sic", "Data stores the misspelling; a tidy-up that 'corrects' it to Exchangeable makes the filter"),
    (DOMAIN, "DOMAIN_MANDATORY_FILTERS", "Verified live at domain-v4.yml:181; anchors the PRODUCT/dedupe/time/region/broker rule blo"),
    (SCHEMA, "(secondary, unverified)", "VERIFIED present 8x (SETTLEMENT_DATE, INVESTOR_CATEGORY, MEETING_TYPE et al). Dictionary d"),
    (SKILL, "ADD_MONTHS(SYSDATE,-12)", "Exact scan-guard window for unfiltered 'last N' asks; losing it reintroduces full-view sca"),
    (SKILL, "DEMAND_QTY \u2212 ALLOCATION", "'Got scaled back' is an allocation-cut computation, not IOI_TYPE LIKE '%SCALED%' (skill-v7"),
    (SKILL, "CANONICAL DEAL-GRAIN RECIPE", "deal listings are one row per deal (multi-tranche fix)"),
    (SKILL, "TRANCHE_COUNT", "multi-tranche deals show a Tranches column"),
    (DOMAIN, "ONE ROW PER DEAL", "deal-grain rule in the always-present layer"),
]

# ---------------------------------------------------------------------------
#    RETIRED - doctrines we overturned; their old wording must never reappear
# ---------------------------------------------------------------------------

RETIRED = [
    (SKILL, "ORDER_ID | order id — DCM only", "ORDER_ID is on both products (confirmed 2026-07-28)"),
    (SKILL, "No settlement/demand currency exists", "SETTLEMENT_CURRENCY now exists"),
    (SKILL, "Solo = ECM only", "solo is answerable on both products"),
    (SKILL, "Windows that end \"now\" have NO upper bound", "admitted future-dated rows"),
    (DOMAIN, "ORDER_ID is DCM-only", "ORDER_ID is on both products"),
    (SCHEMA, "DCM ONLY - not usable on ECM rows", "ORDER_ID description was corrected"),
    # --- mined from the failure log + per-rule sweep (workflow, 2026-08-03) ---
    (SCHEMA, "ECM ONLY (official dict)", "VERIFIED absent (0 hits; 'official dict' survives only in DEAL_STATUS vocab note, and bare"),
    (SKILL, "text2sql_export_to_excel", "VERIFIED absent (0 hits in skill-v7.md and also clean in agents-v6.yml, sql-validation-v2."),
    (SKILL, "query BOTH with OR", "VERIFIED absent (0 hits, and no 'BOTH with OR'/'query BOTH' variant survives). This exact "),
    (SKILL, "OR '%DEBT REPAY%'", "VERIFIED absent (0 hits). Superseded UOP map form - cannot match DCM's 'Repay Outstanding "),
    (SKILL, "SOURCE='ECM'", "PRODUCT-to-SOURCE rename was CANCELLED (2026-07-27); live file uses PRODUCT='ECM' unspaced"),
]

# ---------------------------------------------------------------------------
# 4. CROSS-LAYER - a rule that lives in only one layer dies on skill-absent turns
#    (label, {file: substring that must appear})
# ---------------------------------------------------------------------------

CROSS_LAYER = [
    ("exchange-full-venue-names", {SKILL: "NEW YORK", SCHEMA: "New York", RULES: "EXCHANGE"}),
    ("tranche-name-with-identifiers", {SKILL: "TRANCHE_NAME", SCHEMA: "TRANCHE-grain", INSTR: "tranche"}),
    ("entitlement-is-a-sql-constraint", {SKILL: "entitled", INSTR: "ENTITLEMENT SCOPE", DOMAIN: "ENTITLED"}),
    ("units-per-product", {SKILL: "shares", INSTR: "shares", SCHEMA: "shares"}),
    ("equity-type-is-ecm-only", {SKILL: "ECM ONLY", SCHEMA: "ECM ONLY", RULES: "ECM-only"}),
    ("id-quoting", {SKILL: "quote id literals", SCHEMA: "QUOTED", RULES: "quote the literal"}),
]


# ---------------------------------------------------------------------------
# machinery
# ---------------------------------------------------------------------------

def has(path: Path, phrase: str) -> bool:
    """Case-insensitive presence check - rewrites recase text; behavior is what matters."""
    return phrase.lower() in path.read_text().lower()


def load_rules() -> list[dict]:
    """Validator rules as [{name, value, match_should_fail}]. PyYAML if available, else ruby."""
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(RULES.read_text())
    except Exception:
        out = subprocess.run(
            ["ruby", "-ryaml", "-rjson", "-e", f"puts JSON.dump(YAML.load_file('{RULES}'))"],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(out.stdout)
    rules = data.get("rules") or next((v for v in data.values() if isinstance(v, list)), None)
    if not rules:
        raise SystemExit("could not locate the rule list in sql-validation-v2.yml")
    return rules


def rejecting_rules(sql: str, rules: list[dict]) -> list[str]:
    """Names of rules that REJECT this SQL (mirrors the server's validate_or_raise)."""
    out = []
    for r in rules:
        matched = bool(re.search(r["value"], sql, re.I | re.S))
        if matched == r.get("match_should_fail", True):
            out.append(r["name"])
    return out


def library_queries() -> list[tuple[str, str]]:
    """Extract the DOMAIN_QUERY_LIBRARY statements from domain-v4.yml."""
    text = DOMAIN.read_text()
    if "DOMAIN_QUERY_LIBRARY" not in text:
        return []
    block = text.split("DOMAIN_QUERY_LIBRARY", 1)[1]
    block = block.split("DOMAIN_SPECIFIC_AGGREGATION_RULES", 1)[0]
    out, label = [], "library"
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("--"):
            label = s.lstrip("- ").strip()
        elif s.upper().startswith("SELECT "):
            out.append((label, s))
    return out


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes = 0

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        if ok:
            self.passes += 1
            if VERBOSE:
                print(f"  ok   {label}")
        else:
            self.failures.append(f"{label}{(' — ' + detail) if detail else ''}")
            print(f"  FAIL {label}{(' — ' + detail) if detail else ''}")


def main() -> int:
    rep = Report()

    print("\n1. STRUCTURE")
    rules = load_rules()
    rep.check(bool(rules), "validator YAML parses", f"{len(rules)} rules")
    names = [r["name"] for r in rules]
    rep.check(len(names) == len(set(names)), "rule names unique")
    for r in rules:
        try:
            rx = re.compile(r["value"], re.I | re.S)
        except re.error as e:
            rep.check(False, f"regex compiles: {r['name'][:40]}", str(e))
            continue
        # a rule that matches the empty string is catastrophically over-broad
        if r.get("match_should_fail", True) and rx.search(""):
            rep.check(False, f"regex not empty-matching: {r['name'][:40]}")
    rep.check(True, "all rule regexes compile")
    try:
        schema = json.loads(SCHEMA.read_text())
        cols = [c["columnName"] for t in schema["tables"] for c in t["columns"]]
        rep.check(len(cols) >= 57, "schema column count", f"{len(cols)} columns")
        rep.check(len(cols) == len(set(cols)), "schema column names unique")
    except Exception as e:  # noqa: BLE001
        rep.check(False, "schema JSON parses", str(e))
    try:
        json.loads(UNSUPPORTED.read_text())
        rep.check(True, "unsupported-intents JSON parses")
    except Exception as e:  # noqa: BLE001
        rep.check(False, "unsupported-intents JSON parses", str(e))

    print("\n2. SQL CORPUS — shapes that broke production must stay rejected")
    for name, sql, keyword in BAD_SQL:
        hits = rejecting_rules(sql, rules)
        if not hits:
            rep.check(False, f"bad/{name}", "NOT rejected by any rule")
        elif not any(keyword.lower() in h.lower() for h in hits):
            rep.check(False, f"bad/{name}", f"rejected, but not by a '{keyword}' rule -> misleading diagnosis; got {hits[:2]}")
        else:
            rep.check(True, f"bad/{name}")

    print("\n   corrected shapes must stay clean")
    for name, sql in GOOD_SQL:
        hits = rejecting_rules(sql, rules)
        rep.check(not hits, f"good/{name}", f"falsely rejected by {hits}")

    lib = library_queries()
    print(f"\n   query library ({len(lib)} statements)")
    for label, sql in lib:
        concrete = (sql.replace("<YEAR+1>", "2025").replace("<YEAR>", "2024")
                       .replace("<STATUS>", "Priced").replace("<DEAL_ID>", "25248935"))
        hits = rejecting_rules(concrete, rules)
        rep.check(not hits, f"library/{label[:44]}", f"rejected by {hits}")

    print("\n3. INVARIANTS — load-bearing text still present")
    for path, phrase, why in INVARIANTS:
        rep.check(has(path, phrase), f"{path.name}: {phrase[:44]!r}", why)

    print("\n   retired doctrines still absent")
    for path, phrase, why in RETIRED:
        rep.check(not has(path, phrase), f"{path.name}: NOT {phrase[:38]!r}", why)

    print("\n4. CROSS-LAYER — doctrine present in every layer that needs it")
    for label, layers in CROSS_LAYER:
        missing = [p.name for p, sub in layers.items() if not has(p, sub)]
        rep.check(not missing, f"{label}", f"missing from {missing}")

    print("\n" + "=" * 72)
    if rep.failures:
        print(f"FAIL — {len(rep.failures)} regression(s), {rep.passes} checks passed\n")
        for f in rep.failures:
            print(f"  - {f}")
        print("\nDo NOT promote until these are green or consciously retired.")
        return 1
    print(f"PASS — {rep.passes} checks green. Safe to promote.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
