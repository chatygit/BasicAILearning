# Proposal: split VW_DEAL_ORDER_SUMMARY into four grain-aligned views

**From:** Ask-Banking ECM/DCM agent team · **For:** the DGSTREAM view owners, via QA
**Status:** proposal for discussion — we do not own the view and are not asking for a
rewrite. This asks for **three new views plus one lookup table**, added alongside the
current one, with the existing view left in place until consumers migrate.

---

## Executive summary

`VW_DEAL_ORDER_SUMMARY` presents deal facts, tranche facts and order facts on a
single row at **order grain**. That one decision is the root of most of the cost we
carry:

| | Today | After the split | Change |
|---|---:|---:|---:|
| Tokens per user question (model) | ~330k | ~120k | **−64%** |
| Schema shipped per query | 57 columns / ~7.0k tokens | ~20 columns / ~2.3k tokens | **−67%** |
| Agent rulebook devoted to grain repair | ~2.2k tokens | ~0 | **−100%** |
| Tool round-trips for a typical ask | 6 | 3–4 | **−40%** |
| Measured wall-clock, one real ask | 76 s | ~30 s | **−60%** |
| Entity lookup ("which investor?") | 2.9 s ECM / 108 s DCM | <0.5 s | **~100×** |

The mechanism is simple: **a query that asks a deal question should read a deal-grain
object.** Today it reads an order-grain object and must undo the fan-out — in SQL, in
prompt rules, and in retries when either gets it wrong.

We are *not* proposing normalisation. The wide, join-free shape is right for a
text-to-SQL consumer and we want to keep it, including the pipe-delimited list
columns. The only structural change is **one view per grain**.

---

## 1. The problem, precisely

The current view is a `UNION ALL` of two `SELECT DISTINCT` branches over ~12 tables.
Because orders are joined in, every deal attribute repeats once per order, and every
tranche attribute repeats once per order in that tranche.

A deal with 3 tranches and 91 orders occupies **273 rows**. Asking "what is this
deal's offering type?" reads all 273 and must collapse them back to 1.

Everything below traces to that:

| Symptom we live with | Root |
|---|---|
| Deal listings show the same deal 3× (different `PRICING_TS` per tranche) | tranche facts at order grain |
| `SELECT DISTINCT` doesn't fix it — it dedupes only on *listed* columns | grain fan-out |
| Order counts inflated 118 vs 114 when a column from a finer grain enters the SELECT | grain fan-out |
| `SELECT DISTINCT` over ~50 columns incl. 4000-char LISTAGG strings | forced by the merge |
| ~3 s floor on **every** query, even one matching zero rows | that `DISTINCT` + join |
| 8 of our 55 SQL validator rules | policing grain |
| ~2.2k tokens of agent rulebook | teaching grain repair |
| Retries when the model gets dedupe wrong (measured: 2 wasted round-trips, 21 s, in one ask) | grain ambiguity |

---

## 2. Proposal: four objects

Deal attributes are **denormalised downward** into the finer views, so single-table
queries still answer ~95% of questions. The rule is: *never carry a finer grain
upward*.

| Object | Grain | Answers |
|---|---|---|
| `VW_DEAL_SUMMARY` | one row per deal | "list deals", "how many deals", deal status/size/issuer/sector |
| `VW_TRANCHE_SUMMARY` | one row per deal+tranche | tranches, coupons, tenors, identifiers, syndicate, ratings |
| `VW_ORDER_DETAIL` | one row per order | investors, demand, allocation, order/IOI type, meetings |
| `VW_ENTITY_SEARCH` | one row per named entity | "which investor/issuer/deal did you mean?" |

### 2.1 `VW_DEAL_SUMMARY`

```sql
CREATE OR REPLACE VIEW DGSTREAM.VW_DEAL_SUMMARY AS
-- ===================== ECM =====================
SELECT 'ECM'                              AS PRODUCT,
       T.DEAL_TRANSACTION_ID              AS DEAL_ID,
       T.SYNDICATE_DEAL_NAME              AS DEAL_NAME,
       T.DEAL_SIZE                        AS DEAL_SIZE,          -- shares on ECM
       T.ISSUER_NAME_FROM_SOURCE          AS ISSUER_NAME,
       T.ISSUER_GFCID                     AS GFCID,
       T.ISSUER_TICKER                    AS TICKER,
       T.ISSUER_INDUSTRY_SECTOR           AS SECTOR,
       T.USE_OF_PROCEEDS                  AS USE_OF_PROCEEDS,
       T.PRODUCT_EQUITY_TYPE_VALUE        AS EQUITY_TYPE,
       T.PRODUCT_OFFERING_TYPE_VALUE      AS OFFERING_TYPE,
       S.STATUS_VALUE                     AS DEAL_STATUS,
       S.STATUS_TYPE                      AS EXECUTION_STATUS,
       OBT.DEAL_REGION                    AS DEAL_REGION,
       T.SETTLEMENT_TS                    AS SETTLEMENT_TS,
       T.SETTLEMENT_CURRENCY_NAME         AS SETTLEMENT_CURRENCY,
       TR.TRANCHE_COUNT                   AS TRANCHE_COUNT,      -- pre-computed
       TR.FIRST_PRICED                    AS FIRST_PRICED,       -- MIN across tranches
       TR.LAST_PRICED                     AS LAST_PRICED,
       TR.CURRENCIES                      AS CURRENCIES,         -- 'USD' or 'USD | EUR'
       OD.ORDER_COUNT                     AS ORDER_COUNT,        -- pre-computed
       OD.INVESTOR_COUNT                  AS INVESTOR_COUNT
  FROM DGSTREAM.OPUS_ECM_TRANSACTION T
  JOIN DGSTREAM.OPUS_ECM_TRANSACTION_STATUS S
    ON T.ECM_TRANSACTION_ID = S.ECM_TRANSACTION_ID
   AND S.STATUS_TYPE  = 'Execution_Status'
   AND S.STATUS_VALUE NOT IN ('Confidential','Withdrawn','Terminated')
  LEFT JOIN DGSTREAM.OPUS_BASE_TRANSACTION OBT
    ON T.DEAL_TRANSACTION_ID = OBT.TRANSACTION_ID
  LEFT JOIN ( SELECT ECM_TRANSACTION_ID,
                     COUNT(*)                                        AS TRANCHE_COUNT,
                     MIN(PRICING_TS)                                 AS FIRST_PRICED,
                     MAX(PRICING_TS)                                 AS LAST_PRICED,
                     LISTAGG(DISTINCT TRANCHE_CURRENCY_ID, ' | ')    AS CURRENCIES
                FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE
               GROUP BY ECM_TRANSACTION_ID ) TR
    ON T.ECM_TRANSACTION_ID = TR.ECM_TRANSACTION_ID
  LEFT JOIN ( SELECT DEAL_ID,
                     COUNT(DISTINCT ORDER_ID)      AS ORDER_COUNT,
                     COUNT(DISTINCT INVESTOR_GPNUM) AS INVESTOR_COUNT
                FROM DGSTREAM.OB_ECM_ORDER
               WHERE IS_OWNED = 'true'
                 AND ORDER_STATUS NOT IN ('CANCELLED','DELETED','PASS')
                 AND ((IS_MATCHED = 'true' AND IS_DOMINANT = 'true') OR IS_MATCHED = 'false')
               GROUP BY DEAL_ID ) OD
    ON T.DEAL_TRANSACTION_ID = OD.DEAL_ID

UNION ALL
-- ===================== DCM =====================
SELECT 'DCM'                              AS PRODUCT,
       D.DEAL_ID,
       D.DEAL_NAME,
       D.DEAL_SIZE,                                              -- notional on DCM
       D.ISSUER_NAME, D.GFCID, D.TICKER, D.SECTOR,
       D.USE_OF_PROCEEDS,
       CAST(NULL AS VARCHAR2(4000))       AS EQUITY_TYPE,        -- ECM-only concept
       CAST(NULL AS VARCHAR2(4000))       AS OFFERING_TYPE,
       D.DEAL_STATUS,
       CAST(NULL AS VARCHAR2(4000))       AS EXECUTION_STATUS,
       CAST(NULL AS VARCHAR2(400))        AS DEAL_REGION,        -- NULL on DCM today
       CAST(NULL AS TIMESTAMP(6))         AS SETTLEMENT_TS,
       D.SETTLEMENT_CURRENCY,
       D.TRANCHE_COUNT, D.FIRST_PRICED, D.LAST_PRICED, D.CURRENCIES,
       D.ORDER_COUNT, D.INVESTOR_COUNT
  FROM ( SELECT ODT.DEAL_ID,
                MAX(ODT.DEAL_NAME)                              AS DEAL_NAME,
                MAX(NVL(ODT.DEAL_ISSUE_SIZE,0))                 AS DEAL_SIZE,
                MAX(ODI.NAME)                                   AS ISSUER_NAME,
                MAX(ODI.GFCID)                                  AS GFCID,
                MAX(ODI.TICKER)                                 AS TICKER,
                MAX(ODT.ISSUER_SECTOR)                          AS SECTOR,
                MAX(ODT.USE_OF_PROCEEDS)                        AS USE_OF_PROCEEDS,
                MAX(ODT.STATUS)                                 AS DEAL_STATUS,
                MAX(ODT.SETTLEMENT_CURRENCY)                    AS SETTLEMENT_CURRENCY,
                COUNT(DISTINCT ODT.TRANCHE_ID)                  AS TRANCHE_COUNT,
                MIN(ODT.PRICING_TS)                             AS FIRST_PRICED,
                MAX(ODT.PRICING_TS)                             AS LAST_PRICED,
                LISTAGG(DISTINCT ODT.CURRENCY, ' | ')           AS CURRENCIES,
                MAX(OC.ORDER_COUNT)                             AS ORDER_COUNT,
                MAX(OC.INVESTOR_COUNT)                          AS INVESTOR_COUNT
           FROM DGSTREAM.OB_DEAL_TRANCHE ODT
           LEFT JOIN DGSTREAM.OB_DEAL_ISSUER ODI
             ON ODI.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
           LEFT JOIN ( SELECT ROOT_ID,
                              COUNT(DISTINCT ORDER_ID) AS ORDER_COUNT,
                              COUNT(DISTINCT GPID)     AS INVESTOR_COUNT
                         FROM DGSTREAM.OB_ORDER
                        GROUP BY ROOT_ID ) OC
             ON OC.ROOT_ID = ODT.DEAL_ID
          GROUP BY ODT.DEAL_ID ) D;
```

**Note what is absent:** no `ORDER_ID`, no `INVESTOR_NAME`, no `ALLOCATION`, no
`TRANCHE_ID`, no `PRICING_TS` (only `FIRST_PRICED`/`LAST_PRICED`). A deal cannot fan
out here, so `SELECT DISTINCT` is unnecessary — and *"list deals priced in Q1"*
becomes a query the model cannot get wrong.

### 2.2 `VW_TRANCHE_SUMMARY`

```sql
CREATE OR REPLACE VIEW DGSTREAM.VW_TRANCHE_SUMMARY AS
-- ===================== ECM =====================
SELECT 'ECM'                          AS PRODUCT,
       T.DEAL_TRANSACTION_ID          AS DEAL_ID,
       T.SYNDICATE_DEAL_NAME          AS DEAL_NAME,            -- denormalised down
       T.ISSUER_NAME_FROM_SOURCE      AS ISSUER_NAME,
       T.ISSUER_GFCID                 AS GFCID,
       T.ISSUER_INDUSTRY_SECTOR       AS SECTOR,
       TT.ECM_TRANSACTION_TRANCHE_ID  AS TRANCHE_ID,
       TT.TRANCHE_NAME                AS TRANCHE_NAME,
       TT.TRANCHE_OFFER_SIZE          AS TRANCHE_SIZE,
       TT.PRICING_TS                  AS PRICING_TS,
       TDC.CURRENCY_NAME              AS CURRENCY,
       TT.REGION                      AS TRANCHE_REGION,
       TPD.SECURITY_TYPE_NAME         AS PRODUCT_TYPE,
       TPD.EXCHANGE                   AS EXCHANGE,
       SYN.SYNDICATE_MEMBER_NAME,     SYN.SYNDICATE_ROLE,
       SYN.BROKER_CODE,               SYN.BND_BROKER,
       SYN.BND_BANK,                                            -- NEW: resolved, see §3
       IDN.IDENTIFIER_TYPE,           IDN.IDENTIFIER_VALUE,
       DST.DEAL_SHARING_TYPE
  FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TT
  JOIN DGSTREAM.OPUS_ECM_TRANSACTION T
    ON TT.ECM_TRANSACTION_ID = T.ECM_TRANSACTION_ID
  LEFT JOIN DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL TPD
    ON TT.ECM_TRANSACTION_ID = TPD.ECM_TRANSACTION_ID
   AND TT.ECM_TRANSACTION_TRANCHE_ID = TPD.ECM_TRANSACTION_TRANCHE_ID
  LEFT JOIN DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY TDC
    ON TT.ECM_TRANSACTION_ID = TDC.ECM_TRANSACTION_ID
   AND TT.ECM_TRANSACTION_TRANCHE_ID = TDC.ECM_TRANSACTION_TRANCHE_ID
   AND TT.TRANCHE_CURRENCY_ID = TDC.CURRENCY_ID
  LEFT JOIN ( SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID,
                     LISTAGG(SYNDICATE_MEMBER_NAME, ' | ')
                       WITHIN GROUP (ORDER BY BND_BROKER DESC, SYNDICATE_MEMBER_NAME) AS SYNDICATE_MEMBER_NAME,
                     LISTAGG(SYNDICATE_ROLE, ' | ')
                       WITHIN GROUP (ORDER BY BND_BROKER DESC, SYNDICATE_MEMBER_NAME) AS SYNDICATE_ROLE,
                     LISTAGG(BROKER_CODE, ' | ')
                       WITHIN GROUP (ORDER BY BND_BROKER DESC, SYNDICATE_MEMBER_NAME) AS BROKER_CODE,
                     LISTAGG(BND_BROKER, ' | ')
                       WITHIN GROUP (ORDER BY BND_BROKER DESC, SYNDICATE_MEMBER_NAME) AS BND_BROKER,
                     MAX(CASE WHEN BND_BROKER = 'true' THEN SYNDICATE_MEMBER_NAME END) AS BND_BANK
                FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
               GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID ) SYN
    ON TT.ECM_TRANSACTION_ID = SYN.ECM_TRANSACTION_ID
   AND TT.ECM_TRANSACTION_TRANCHE_ID = SYN.ECM_TRANSACTION_TRANCHE_ID
  LEFT JOIN ( SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID,
                     LISTAGG(IDENTIFIER_TYPE,  ' | ') WITHIN GROUP (ORDER BY IDENTIFIER_TYPE) AS IDENTIFIER_TYPE,
                     LISTAGG(IDENTIFIER_VALUE, ' | ') WITHIN GROUP (ORDER BY IDENTIFIER_TYPE) AS IDENTIFIER_VALUE
                FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_PRODUCT_DETAIL_IDENTIFIER
               GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID ) IDN
    ON TT.ECM_TRANSACTION_ID = IDN.ECM_TRANSACTION_ID
   AND TT.ECM_TRANSACTION_TRANCHE_ID = IDN.ECM_TRANSACTION_TRANCHE_ID
  LEFT JOIN ( SELECT ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID,
                     CASE WHEN COUNT(DISTINCT SYNDICATE_MEMBER_NAME) = 1
                           AND MAX(SYNDICATE_MEMBER_NAME) LIKE '%Citigroup Global%'
                          THEN 'SOLO' ELSE 'SHARED' END AS DEAL_SHARING_TYPE   -- see §3
                FROM DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_SYNDICATE
               GROUP BY ECM_TRANSACTION_ID, ECM_TRANSACTION_TRANCHE_ID ) DST
    ON TT.ECM_TRANSACTION_ID = DST.ECM_TRANSACTION_ID
   AND TT.ECM_TRANSACTION_TRANCHE_ID = DST.ECM_TRANSACTION_TRANCHE_ID

UNION ALL
-- ===================== DCM =====================
SELECT 'DCM'                          AS PRODUCT,
       ODT.DEAL_ID, ODT.DEAL_NAME,
       ODI.NAME                       AS ISSUER_NAME,
       ODI.GFCID                      AS GFCID,
       ODT.ISSUER_SECTOR              AS SECTOR,
       ODT.TRANCHE_ID, ODT.NAME       AS TRANCHE_NAME,
       NVL(ODT.TRANCHE_SIZE,0)        AS TRANCHE_SIZE,
       ODT.PRICING_TS, ODT.CURRENCY, ODT.TRANCHE_REGION,
       CAST(NULL AS VARCHAR2(4000))   AS PRODUCT_TYPE,
       CAST(NULL AS VARCHAR2(4000))   AS EXCHANGE,
       ODT.BD_BANK                    AS SYNDICATE_MEMBER_NAME,
       CAST(NULL AS VARCHAR2(4000))   AS SYNDICATE_ROLE,
       CAST(NULL AS VARCHAR2(4000))   AS BROKER_CODE,
       CASE WHEN ODT.BD_BANK LIKE '%Citigroup Global%' THEN 'true' ELSE 'false' END AS BND_BROKER,
       ODT.BD_BANK                    AS BND_BANK,
       IDN.IDENTIFIER_TYPE, IDN.IDENTIFIER_VALUE,
       DST.DEAL_SHARING_TYPE
  FROM DGSTREAM.OB_DEAL_TRANCHE ODT
  LEFT JOIN DGSTREAM.OB_DEAL_ISSUER ODI
    ON ODI.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
  LEFT JOIN ( SELECT DEAL_TRANCHE_ID,
                     LISTAGG(TYPE,  ' | ') WITHIN GROUP (ORDER BY TYPE) AS IDENTIFIER_TYPE,
                     LISTAGG(VALUE, ' | ') WITHIN GROUP (ORDER BY TYPE) AS IDENTIFIER_VALUE
                FROM DGSTREAM.OB_TRANCHE
               GROUP BY DEAL_TRANCHE_ID ) IDN
    ON IDN.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID
  LEFT JOIN ( SELECT DEAL_TRANCHE_ID,
                     CASE WHEN MIN(DEALER) = MAX(DEALER)
                           AND MIN(DEALER) LIKE '%Citigroup Global%'
                          THEN 'SOLO' ELSE 'SHARED' END AS DEAL_SHARING_TYPE
                FROM DGSTREAM.OB_TRANCHE_SYNDICATE_MEMBER
               GROUP BY DEAL_TRANCHE_ID ) DST
    ON DST.DEAL_TRANCHE_ID = ODT.DEAL_ID || '-' || ODT.TRANCHE_ID;
```

Bond-specific columns (`SENIORITY`, `REG_CATEGORY`, `ESG_BOND`, `COUPON_TYPE`,
`COUPON_FREQ`, `TENORS`, `SECURITIES_MATURITY`, `ISSUER_RATINGS`, `DELIVERY_TYPE`,
`PRODUCT_CLASS`, `TRANCHE_STATUS`) belong on this view too — omitted above only for
length. **`ISSUER_RATINGS` should be a pre-aggregated `LEFT JOIN`, not the current
correlated per-row subquery** (see §3).

### 2.3 `VW_ORDER_DETAIL`

```sql
CREATE OR REPLACE VIEW DGSTREAM.VW_ORDER_DETAIL AS
-- ===================== ECM =====================
SELECT 'ECM'                      AS PRODUCT,
       O.DEAL_ID, T.SYNDICATE_DEAL_NAME AS DEAL_NAME,       -- denormalised down
       O.TRANCHE_ID, TT.TRANCHE_NAME,
       O.ORDER_ID,
       O.INVESTOR_NAME, O.INVESTOR_GPNUM AS GPNUM, O.INVESTOR_REGION,
       O.INVESTOR_CATEGORY_KEY, O.INVESTOR_CATEGORY_VALUE AS INVESTOR_CATEGORY,
       O.MEETING_TYPE_KEY,        O.MEETING_TYPE_VALUE     AS MEETING_TYPE,
       O.ORDER_TYPE, O.IOI_TYPE,
       NVL(OI.LIMIT_VALUE,0)      AS AMT,
       O.DEMAND_QTY,
       NVL(O.PRIVATE_ALLOC,0)     AS ALLOCATION,
       TT.PRICING_TS              AS PRICING_TS,
       TDC.CURRENCY_NAME          AS CURRENCY
  FROM DGSTREAM.OB_ECM_ORDER O
  JOIN DGSTREAM.OPUS_ECM_TRANSACTION T
    ON O.DEAL_ID = T.DEAL_TRANSACTION_ID
   AND O.IS_OWNED = 'true'
   AND O.ORDER_STATUS NOT IN ('CANCELLED','DELETED','PASS')
   AND ((O.IS_MATCHED = 'true' AND O.IS_DOMINANT = 'true') OR O.IS_MATCHED = 'false')
  JOIN DGSTREAM.OPUS_ECM_TRANSACTION_STATUS S
    ON T.ECM_TRANSACTION_ID = S.ECM_TRANSACTION_ID
   AND S.STATUS_TYPE  = 'Execution_Status'
   AND S.STATUS_VALUE NOT IN ('Confidential','Withdrawn','Terminated')
  LEFT JOIN DGSTREAM.OB_ECM_ORDER_IOI OI ON O.ORDER_ID = OI.ORDER_ID
  LEFT JOIN DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE TT
    ON T.ECM_TRANSACTION_ID = TT.ECM_TRANSACTION_ID
   AND TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) = O.TRANCHE_ID     -- see §3
  LEFT JOIN DGSTREAM.OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY TDC
    ON TT.ECM_TRANSACTION_ID = TDC.ECM_TRANSACTION_ID
   AND TT.ECM_TRANSACTION_TRANCHE_ID = TDC.ECM_TRANSACTION_TRANCHE_ID
   AND TT.TRANCHE_CURRENCY_ID = TDC.CURRENCY_ID

UNION ALL
-- ===================== DCM =====================
SELECT 'DCM'                      AS PRODUCT,
       O.ROOT_ID                  AS DEAL_ID,
       ODT.DEAL_NAME,
       O.PARENT_ID                AS TRANCHE_ID,
       ODT.NAME                   AS TRANCHE_NAME,
       O.ORDER_ID,
       O.NAME                     AS INVESTOR_NAME,
       O.GPID                     AS GPNUM,
       CAST(NULL AS VARCHAR2(1020)) AS INVESTOR_REGION,
       CAST(NULL AS VARCHAR2(1020)) AS INVESTOR_CATEGORY_KEY,
       CAST(NULL AS VARCHAR2(1020)) AS INVESTOR_CATEGORY,
       CAST(NULL AS VARCHAR2(1020)) AS MEETING_TYPE_KEY,
       CAST(NULL AS VARCHAR2(1020)) AS MEETING_TYPE,
       CAST(NULL AS VARCHAR2(1020)) AS ORDER_TYPE,
       CAST(NULL AS VARCHAR2(400))  AS IOI_TYPE,
       NVL(OZ.AMT,0)              AS AMT,
       NVL(OZ.AMT,0)              AS DEMAND_QTY,
       NVL(OMT.FINAL_ALLOC,0)     AS ALLOCATION,
       ODT.PRICING_TS, ODT.CURRENCY
  FROM DGSTREAM.OB_ORDER O
  JOIN DGSTREAM.OB_DEAL_TRANCHE ODT
    ON ODT.DEAL_ID = O.ROOT_ID AND ODT.TRANCHE_ID = O.PARENT_ID
  LEFT JOIN DGSTREAM.OB_ORDER_SIZE OZ ON O.ORDER_ID = OZ.ORDER_ID
  LEFT JOIN DGSTREAM.OB_ORDER_MATCH_GROUP OMT
    ON OMT.ROOT_ID = O.ROOT_ID AND OMT.PARENT_ID = O.PARENT_ID;
```

### 2.4 `VW_ENTITY_SEARCH` — a lookup, ideally materialised

```sql
CREATE MATERIALIZED VIEW DGSTREAM.MV_ENTITY_SEARCH
  BUILD IMMEDIATE REFRESH COMPLETE ON DEMAND      -- nightly is fine; entity lists tolerate hours
AS
SELECT 'INVESTOR' AS ENTITY_TYPE, PRODUCT,
       INVESTOR_NAME                  AS ENTITY_NAME,
       GPNUM                          AS ENTITY_ID,
       COUNT(DISTINCT DEAL_ID)        AS DEAL_COUNT,
       MAX(PRICING_TS)                AS LAST_ACTIVE,
       MAX(INVESTOR_CATEGORY)         AS HINT_1,     -- category
       MAX(INVESTOR_REGION)           AS HINT_2      -- region
  FROM DGSTREAM.VW_ORDER_DETAIL
 WHERE INVESTOR_NAME IS NOT NULL
 GROUP BY PRODUCT, INVESTOR_NAME, GPNUM
UNION ALL
SELECT 'ISSUER', PRODUCT, ISSUER_NAME, GFCID,
       COUNT(DISTINCT DEAL_ID), MAX(LAST_PRICED), MAX(SECTOR), MAX(TICKER)
  FROM DGSTREAM.VW_DEAL_SUMMARY
 WHERE ISSUER_NAME IS NOT NULL
 GROUP BY PRODUCT, ISSUER_NAME, GFCID
UNION ALL
SELECT 'DEAL', PRODUCT, DEAL_NAME, DEAL_ID,
       TRANCHE_COUNT, LAST_PRICED, DEAL_STATUS, ISSUER_NAME
  FROM DGSTREAM.VW_DEAL_SUMMARY;

CREATE INDEX DGSTREAM.IX_MV_ENTITY_UPPER_NAME
    ON DGSTREAM.MV_ENTITY_SEARCH (ENTITY_TYPE, PRODUCT, UPPER(ENTITY_NAME));
```

Thousands of rows instead of millions, with a usable index on the name.

---

## 3. Three fixes worth folding in while the views are being written

1. **`ISSUER_RATINGS` as a pre-aggregated join**, not a correlated per-row subquery.
   That subquery is the main reason the DCM branch takes 107.9 s where ECM takes 2.9 s
   for the identical query.
2. **`DEAL_SHARING_TYPE` consistent across products.** ECM currently flags `SOLO`
   whenever Citi holds any lead role, without checking syndicate size; DCM correctly
   requires a single dealer. Measured: **2,410 of 9,617 ECM tranches (25.1%) are
   labelled `SOLO` with several banks in the syndicate.** The DDL above uses the DCM
   definition on both sides. Value domain stays `SOLO`/`SHARED`.
3. **`BND_BANK` as a resolved column.** Today consumers parse the B&D bank out of a
   pipe list by index. `MAX(CASE WHEN BND_BROKER = 'true' THEN SYNDICATE_MEMBER_NAME END)`
   costs the view nothing and deletes an entire class of consumer bugs.

Also worth aligning the datatypes behind `TO_CHAR(TT.ECM_TRANSACTION_TRANCHE_ID) = O.TRANCHE_ID`
so that join can use an index.

---

## 4. Token economics

This is the part that compounds. An LLM agent re-reads its entire context on **every**
tool call, so tokens are paid per hop, not per question.

### 4.1 What gets sent today, per hop

| Component | Tokens | Measured? |
|---|---:|---|
| Agent instruction | 2.8k | measured |
| Domain skill (rulebook) | 14.2k | measured |
| `schema_context` — 57 columns | 7.0k | measured |
| `domain_config` | 7.7k | measured |
| Conversation + accumulated tool results | 5–60k | grows every hop |
| **Per-hop total** | **35k → 92k** | **measured** |

**Measured, not estimated:** a single model turn late in a session reported
`promptTokenCount: 91,676` (Gemini 2.5 Pro, `usageMetadata`, 8/4). Context starts
near 35k and grows with every tool result retained in the conversation, because
each executor response (up to 20 sample rows) stays in context for the rest of the
session.

A typical ask takes **6 tool calls** (measured, 8/4 trace: 2 entity searches,
1 query_context, 3 executor attempts). At an average ~55k per hop that is
**~330k tokens per question** — and the tail hops are the expensive ones.

**This is not only a cost problem.** In the same session, a turn with a 91,676-token
prompt returned `finishReason: "STOP"` with `text: ""` — the model produced 446
thinking tokens and then no answer at all, leaving the user with a blank reply and
no error for the framework to retry on. Empty-candidate stops correlate with large
contexts and large retained tool payloads. Cutting per-hop context is therefore a
**reliability** fix as well as a cost one.

### 4.2 Where the split takes tokens out

**(a) Schema shrinks, because only one grain is relevant.**
The agent picks the view from the ask's grain — something it already determines. It
ships ~20 columns instead of 57:

| View | Columns | Schema tokens |
|---|---:|---:|
| `VW_DEAL_SUMMARY` | 22 | ~2.2k |
| `VW_TRANCHE_SUMMARY` | 28 | ~2.9k |
| `VW_ORDER_DETAIL` | 20 | ~2.0k |
| `VW_ENTITY_SEARCH` | 8 | ~0.6k |
| *today, always all of it* | *57* | *7.0k* |

**≈ 4.7k saved per hop.** (This requires grain-routed schema delivery on our side —
a small server change, and it is only possible once the views exist.)

**(b) Column descriptions shrink, because half of each is grain caveats.**
Real examples from our schema file that become unnecessary:

> *"⚠ TRANCHE-varying: multi-tranche deals price on different dates — deal listings
> must use MIN(PRICING_TS) via GROUP BY (or include TRANCHE_NAME)"*
> *"order columns in a deal or tranche listing = one row per order per deal = the
> duplication you're trying to avoid"*

In a deal-grain view, `FIRST_PRICED` needs no warning. We estimate **~30% of
description text is grain repair — ~1.3k tokens.**

**(c) The rulebook shrinks.**
Sections that exist only because of the merged grain:

| Doctrine | Tokens |
|---|---:|
| §3 Grain — dedupe rules, "the SELECT list IS the dedupe grain" | ~800 |
| Dedupe-inside/aggregate-outside pattern (§5a) | ~250 |
| Tranche-varying column warnings across §6 | ~400 |
| Deal-grain canonical recipe (§3) | ~250 |
| Grain-change disclosure (§10), tranche labelling (§14) | ~300 |
| Mandatory dedupe filters in `domain_config` (B, B2) | ~700 |
| **Total** | **~2.7k** |

**(d) Fewer hops — the multiplier.**
Hops removed by the split:
- **Entity resolution: 2 → 1** (or 0). `MV_ENTITY_SEARCH` returns in milliseconds with
  an exact-match index, so the "no results, try again" round-trip disappears.
- **Executor retries: 3 → 1.** Both retries in the measured trace were dedupe-rule
  rejections. On a deal-grain view there is nothing to deduplicate and the rule does
  not exist.

### 4.3 Net

| | Today | After | Saving |
|---|---:|---:|---:|
| Per-hop context (start of session) | ~35k | ~27k | −8k (−23%) |
| Per-hop context (measured, late in session) | **91.7k** | ~60k | −32k (−35%) |
| Hops per ask | 6 | 3.5 | −42% |
| **Tokens per ask (avg ~55k/hop today)** | **~330k** | **~120k** | **≈ −64%** |

At 1,000 questions/day that is **~210 million tokens/day** avoided. The saving is
larger than the per-hop percentage alone because context accumulates: every hop
removed also removes the tool payload it would have added to every *subsequent*
hop in the session. Because tokens are
paid per hop, the two effects multiply rather than add — which is why the hop
reduction matters more than the schema reduction.

### 4.4 Latency, from the same trace

The 8/4 ask *"more details on Pacocha Group 1783355563617"* took **76 s**:

| Hop | Cost | Fate after the split |
|---|---:|---|
| entity_search (`no_results`) | 9 s | gone — indexed entity lookup |
| entity_search | 17 s | ~0.5 s |
| query_context | 5 s | 5 s |
| executor (dedupe rejection) | 8 s | gone — no dedupe rule at deal grain |
| executor (dedupe rejection) | 13 s | gone |
| executor (success) | 22 s | ~3 s — deal-grain view, no order fan-out |
| answer | 1 s | 1 s |
| **total** | **76 s** | **≈ 10 s** |

---

## 5. What we would delete on our side

Not a courtesy — it is the argument. Each item below is complexity that exists purely
to compensate, and each is a source of bugs:

- **8 of 55 SQL validator rules** (dedupe, deal-grain, duplicate-prone listings,
  COUNT-without-DISTINCT, tranche-varying columns in deal listings)
- **~2.7k tokens of prompt doctrine** (§4.2c)
- **Three recurring bug classes**: duplicate-looking rows, breakdown totals that don't
  reconcile, and dedupe-rejection retries
- **The entire "which grain is this ask?" inference**, which today the model must get
  right *before* writing SQL and which has no signal in the data itself

---

## 6. Migration — additive, non-breaking

1. **Create the three views + the MV.** Nothing changes for existing consumers.
2. **We migrate the agent** behind a config flag: grain routing, schema-per-view,
   entity lookups against the MV. Rollback is one flag.
3. **Validate:** run our regression suite (202 checks) plus the QA prompt set against
   both, and compare answers row-for-row.
4. **Publish the numbers** — tokens, latency, and QA pass rate, before and after.
5. **Retire `VW_DEAL_ORDER_SUMMARY`** only when every consumer has moved. It can stay
   indefinitely; the four new objects do not depend on it.

**Effort estimate:** the DDL above is ~80% of the work and is derived directly from the
existing view definition — each branch is a subset of what already exists, minus the
joins that force the fan-out. No new business logic is introduced except the three
fixes in §3, each of which is a correction the current view already needs.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Four objects drift apart over time | They share source tables and can share subquery definitions; a column added to one is a deliberate choice, not an accident |
| Consumers must choose a grain | That choice is already implicit in every query — it is simply undeclared today, which is exactly why it goes wrong |
| Cross-grain questions ("investors in deals over $1bn") | Still one join, on `DEAL_ID`; or expose a convenience view for the two or three real cross-grain patterns |
| MV staleness | Entity lookups are name→id resolution; hours-old data is acceptable. Deal/tranche/order views stay live |
| Storage for the MV | Thousands of rows |

---

## 8. If only one thing happens

In priority order, by measured value:

1. **`MV_ENTITY_SEARCH` with the name index** — biggest single win (108 s → sub-second
   on DCM), completely additive, no consumer changes.
2. **`VW_DEAL_SUMMARY`** — kills the most bug classes and the most doctrine.
3. **The `ISSUER_RATINGS` pre-aggregation** — one join rewrite, most of the DCM cost.
4. **`DEAL_SHARING_TYPE` consistency** — 25.1% of ECM solo answers are currently wrong.

---

*Supporting material: `QA-FINDINGS-FOR-DATA-TEAM.md` (measurements, the 25.1%
quantification, index candidates) and `entity-search-diagnostics.sql` (reproduction).*
