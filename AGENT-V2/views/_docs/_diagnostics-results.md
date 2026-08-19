# Diagnostics results — deployed DGSTREAM views

Answers to [`_diagnostics.sql`](_diagnostics.sql), captured as they come back.
Source of truth for the deployed shape — these override any column list in
`V1/docs/VIEW-SPLIT-PROPOSAL.md` or the `app/bqs/ontology/*.yaml` files.

## Reading these numbers — QA, not PROD

This is the **QA** environment. Counts and percentages here do **not** size PROD
impact and must never be quoted as such. What QA gives us is **existence
proof**: if a fan-out, a bad value or a confidential row appears here, the
schema permits it and the view must handle it. Absence in QA proves nothing.

Every conclusion below is written as a structural yes/no for that reason.

## Scope rules — these bound every fix, not just this batch

1. **Do not add columns.** A column existing in a base table is not a reason to
   expose it. The four views were scoped to the columns the V1 view actually
   used; a few extra crept in and that is fine, but the list does not grow.
   This closes decision **D2** in `_diagnostics.sql`: fixes only.
   → withdrawn as a result: `MATCH_RANK` on the entity view, `DEAL_REGION` on
     the DCM deal branch, and any "real" `EXECUTION_STATUS`.
2. **Do not remove columns already exposed.** `SETTLEMENT_CURRENCY` is the
   worked example — it was not in the V1 view, it has no data flowing, it is a
   placeholder. It stays. Same reasoning applies to any other empty column.
3. **A view change is a 2–4 day cycle**, so everything ships in one pass, and
   every ontology file changes in the same PR.
4. Prefer fixes that *remove* SQL over fixes that add it.

---

| Query | Status |
|---|---|
| Q1 view column types | ✅ captured below |
| Q2 DCM order tables | ✅ captured below |
| Q3 remaining base tables | ⏳ pending |
| Q34 allocation source | ✅ captured below |
| Q6 match-group sample | ✅ captured below |
| Q8 allocation reconcile | ✅ captured below |
| Q34–Q37 allocation | ✅ complete |
| Q9–Q12 grain integrity | ✅ captured below |
| Q13–Q14 typing | ✅ captured below |
| Q17 DCM status | ✅ captured below |
| Q19–Q20 DCM counts | ✅ | Q18 NOT RUN (not needed) |
| Q21–Q26 list columns | ✅ complete |
| Q28–Q29 entity view | ✅ complete |
| Q32 settlement_ts | ✅ complete |

---

## Q1 — deployed column types of the four views

`all_tab_columns` where `owner = 'DGSTREAM'`.

### VW_DEAL_SUMMARY (22 columns)

| # | Column | Type | Length | Scale |
|---|---|---|---|---|
| 1 | PRODUCT | CHAR | 3 | |
| 2 | DEAL_ID | VARCHAR2 | 4000 | |
| 3 | DEAL_NAME | VARCHAR2 | 32767 | |
| 4 | DEAL_SIZE | NUMBER | 22 | |
| 5 | ISSUER_NAME | VARCHAR2 | 4000 | |
| 6 | GFCID | VARCHAR2 | 400 | |
| 7 | TICKER | VARCHAR2 | 4000 | |
| 8 | SECTOR | VARCHAR2 | 4000 | |
| 9 | USE_OF_PROCEEDS | VARCHAR2 | 4400 | |
| 10 | EQUITY_TYPE | VARCHAR2 | 4000 | |
| 11 | OFFERING_TYPE | VARCHAR2 | 4000 | |
| 12 | DEAL_STATUS | VARCHAR2 | 4000 | |
| 13 | EXECUTION_STATUS | VARCHAR2 | 4000 | |
| 14 | DEAL_REGION | VARCHAR2 | 400 | |
| 15 | SETTLEMENT_TS | TIMESTAMP(6) | 11 | 6 |
| 16 | SETTLEMENT_CURRENCY | VARCHAR2 | 4000 | |
| 17 | TRANCHE_COUNT | NUMBER | 22 | |
| 18 | FIRST_PRICED | TIMESTAMP(6) | 11 | 6 |
| 19 | LAST_PRICED | TIMESTAMP(6) | 11 | 6 |
| 20 | CURRENCIES | VARCHAR2 | 32767 | |
| 21 | ORDER_COUNT | NUMBER | 22 | |
| 22 | INVESTOR_COUNT | NUMBER | 22 | |

### VW_TRANCHE_SUMMARY (39 columns)

| # | Column | Type | Length | Scale |
|---|---|---|---|---|
| 1 | PRODUCT | CHAR | 3 | |
| 2 | DEAL_ID | VARCHAR2 | 4000 | |
| 3 | DEAL_NAME | VARCHAR2 | 32767 | |
| 4 | ISSUER_NAME | VARCHAR2 | 4000 | |
| 5 | GFCID | VARCHAR2 | 400 | |
| 6 | TICKER | VARCHAR2 | 4000 | |
| 7 | SECTOR | VARCHAR2 | 4000 | |
| 8 | DEAL_REGION | VARCHAR2 | 40 | |
| 9 | TRANCHE_ID | VARCHAR2 | 400 | |
| 10 | TRANCHE_NAME | VARCHAR2 | 32767 | |
| 11 | TRANCHE_SIZE | VARCHAR2 | 480 | |
| 12 | PRICING_TS | TIMESTAMP(3) | 11 | 3 |
| 13 | CURRENCY | VARCHAR2 | 4000 | |
| 14 | TRANCHE_REGION | VARCHAR2 | 4000 | |
| 15 | PRODUCT_CLASS | VARCHAR2 | 16000 | |
| 16 | SENIORITY | VARCHAR2 | 1600 | |
| 17 | REG_CATEGORY | VARCHAR2 | 1600 | |
| 18 | ESG_BOND | VARCHAR2 | 800 | |
| 19 | COUPON_TYPE | VARCHAR2 | 1600 | |
| 20 | COUPON_FREQ | VARCHAR2 | 1600 | |
| 21 | USE_OF_PROCEEDS | VARCHAR2 | 4400 | |
| 22 | PRODUCT_TYPE | VARCHAR2 | 4000 | |
| 23 | EXCHANGE | VARCHAR2 | 4000 | |
| 24 | SETTLEMENT_CURRENCY | VARCHAR2 | 4000 | |
| 25 | TRANCHE_STATUS | VARCHAR2 | 16000 | |
| 26 | DEAL_STATUS | VARCHAR2 | 4000 | |
| 27 | EXECUTION_STATUS | VARCHAR2 | 4000 | |
| 28 | SYNDICATE_MEMBER_NAME | VARCHAR2 | 32767 | |
| 29 | SYNDICATE_ROLE | VARCHAR2 | 32767 | |
| 30 | BROKER_CODE | VARCHAR2 | 32767 | |
| 31 | BND_BROKER | VARCHAR2 | 32767 | |
| 32 | BND_BANK | VARCHAR2 | 4000 | |
| 33 | IDENTIFIER_TYPE | VARCHAR2 | 32767 | |
| 34 | IDENTIFIER_VALUE | VARCHAR2 | 32767 | |
| 35 | DELIVERY_TYPE | VARCHAR2 | 32767 | |
| 36 | ISSUER_RATINGS | VARCHAR2 | 32767 | |
| 37 | TENORS | VARCHAR2 | 16000 | |
| 38 | SECURITIES_MATURITY | VARCHAR2 | 16000 | |
| 39 | DEAL_SHARING_TYPE | VARCHAR2 | 6 | |

### VW_ORDER_DETAIL (20 columns)

| # | Column | Type | Length | Scale |
|---|---|---|---|---|
| 1 | PRODUCT | CHAR | 3 | |
| 2 | DEAL_ID | VARCHAR2 | 400 | |
| 3 | DEAL_NAME | VARCHAR2 | 32767 | |
| 4 | TRANCHE_ID | VARCHAR2 | 400 | |
| 5 | TRANCHE_NAME | VARCHAR2 | 32767 | |
| 6 | ORDER_ID | VARCHAR2 | 600 | |
| 7 | INVESTOR_NAME | VARCHAR2 | 800 | |
| 8 | INVESTOR_GP_ID | VARCHAR2 | 400 | |
| 9 | INVESTOR_REGION | VARCHAR2 | 1020 | |
| 10 | INVESTOR_CATEGORY_KEY | VARCHAR2 | 1020 | |
| 11 | INVESTOR_CATEGORY | VARCHAR2 | 1020 | |
| 12 | MEETING_TYPE_KEY | VARCHAR2 | 1020 | |
| 13 | MEETING_TYPE | VARCHAR2 | 1020 | |
| 14 | ORDER_TYPE | VARCHAR2 | 1020 | |
| 15 | IOI_TYPE | VARCHAR2 | 400 | |
| 16 | ORDER_AMOUNT | NUMBER | 22 | |
| 17 | ORDER_DEMAND_QTY | NUMBER | 22 | |
| 18 | ORDER_ALLOCATION | NUMBER | 22 | |
| 19 | PRICING_TS | TIMESTAMP(3) | 11 | 3 |
| 20 | CURRENCY | VARCHAR2 | 4000 | |

### VW_ENTITY_SEARCH (8 columns)

| # | Column | Type | Length | Scale |
|---|---|---|---|---|
| 1 | ENTITY_TYPE | VARCHAR2 | 8 | |
| 2 | PRODUCT | CHAR | 3 | |
| 3 | ENTITY_NAME | VARCHAR2 | 32767 | |
| 4 | ENTITY_ID | VARCHAR2 | 4000 | |
| 5 | ENTITY_ACTIVITY_COUNT | NUMBER | 22 | |
| 6 | LAST_ACTIVE | TIMESTAMP(6) | 11 | 6 |
| 7 | CONTEXT_VALUE_1 | VARCHAR2 | 4080 | |
| 8 | CONTEXT_VALUE_2 | VARCHAR2 | 4080 | |

---

## Q2 — DCM order-side base tables

`all_tab_columns` where `owner = 'DGSTREAM'`. N/Y = nullable.

### OB_ORDER (82 columns)

| # | Column | Type | Len | Null |
|---|---|---|---|---|
| 1 | UUID | NUMBER | 22 | N |
| 2 | ORDER_ID | VARCHAR2 | 600 | N |
| 3 | ITEM_TYPE | VARCHAR2 | 400 | Y |
| 4 | ITEM_SOURCE | VARCHAR2 | 280 | Y |
| 5 | ITEM_DEFINITION_ID | VARCHAR2 | 400 | Y |
| 6 | VERSION | VARCHAR2 | 400 | Y |
| 7 | UPDATED_BY | VARCHAR2 | 80 | Y |
| 8 | UPDATED_TS | TIMESTAMP(6) | 11 | Y |
| 9 | CREATED_BY | VARCHAR2 | 80 | Y |
| 10 | CREATED_TS | TIMESTAMP(6) | 11 | Y |
| 11 | IS_ACTIVE | VARCHAR2 | 40 | Y |
| 12 | ROOT_ID | VARCHAR2 | 400 | Y |
| 13 | PARENT_ID | VARCHAR2 | 400 | Y |
| 14 | STATUS | VARCHAR2 | 400 | Y |
| 15 | IS_FIRM_ORDER | VARCHAR2 | 40 | Y |
| 16 | BND | VARCHAR2 | 800 | Y |
| 17 | OWNER | VARCHAR2 | 800 | Y |
| 18 | SETTLEMENT_SUBSIDIARY | VARCHAR2 | 400 | Y |
| 19 | IS_POT | VARCHAR2 | 40 | Y |
| 20 | MASK_INVESTOR | VARCHAR2 | 400 | Y |
| 21 | DRAFT_BND | VARCHAR2 | 800 | Y |
| 22 | NAME | VARCHAR2 | 800 | Y |
| 23 | GPID | VARCHAR2 | 400 | Y |
| 24 | LEGAL_ID | VARCHAR2 | 400 | Y |
| 25 | COUNTRY | VARCHAR2 | 200 | Y |
| 26 | COUNTRY_NAME | VARCHAR2 | 400 | Y |
| 27 | TYPE | VARCHAR2 | 200 | Y |
| 28 | SUB_TYPE | VARCHAR2 | 200 | Y |
| 29 | QIB_STATUS | VARCHAR2 | 400 | Y |
| 30 | PM_ID | VARCHAR2 | 400 | Y |
| 31 | ALIAS | VARCHAR2 | 600 | Y |
| 32 | ONE_OFF_INVESTOR | VARCHAR2 | 400 | Y |
| 33 | ACCOUNT_X_PM_ID | VARCHAR2 | 400 | Y |
| 34 | FIRST_NAME | VARCHAR2 | 200 | Y |
| 35 | LAST_NAME | VARCHAR2 | 200 | Y |
| 36 | SOEID | VARCHAR2 | 40 | Y |
| 37 | SALES_ID | VARCHAR2 | 400 | Y |
| 38 | REGION | VARCHAR2 | 200 | Y |
| 39 | EU_FIRST_NAME | VARCHAR2 | 200 | Y |
| 40 | EU_LAST_NAME | VARCHAR2 | 200 | Y |
| 41 | EU_SOEID | VARCHAR2 | 40 | Y |
| 42 | **FINAL_ALLOC** | **NUMBER** | 22 | Y |
| 43 | AFFIRM | VARCHAR2 | 200 | Y |
| 44 | DRAFT_ALLOC | VARCHAR2 | 200 | Y |
| 45 | SOFT_ALLOC | VARCHAR2 | 200 | Y |
| 46 | RECONCILE | VARCHAR2 | 200 | Y |
| 47 | ISN_ALLOC | VARCHAR2 | 200 | Y |
| 48 | RETENTION | VARCHAR2 | 200 | Y |
| 49 | RATIONALE | VARCHAR2 | 1020 | Y |
| 50 | RATIONALE_TYPE | VARCHAR2 | 400 | Y |
| 51 | CRITERIA | VARCHAR2 | 200 | Y |
| 52 | FX_CURRENCY | VARCHAR2 | 200 | Y |
| 53 | OBO_NAME | VARCHAR2 | 800 | Y |
| 54 | OBO_LEGAL_ENTITY_ID | VARCHAR2 | 400 | Y |
| 55 | OBO_PM_ID | VARCHAR2 | 400 | Y |
| 56 | PROCESSED_BY | VARCHAR2 | 80 | N |
| 57 | PROCESSED_DATE | DATE | 7 | N |
| 58 | DG_VERSION | NUMBER | 22 | Y |
| 59 | SOURCE_SYSTEM | VARCHAR2 | 240 | Y |
| 60 | CLASSIFICATION | VARCHAR2 | 200 | Y |
| 61 | DG_ENTITY_KEY | VARCHAR2 | 240 | N |
| 62 | DG_ENTITY_ID | VARCHAR2 | 600 | N |
| 63 | PUBLISHED_TS | TIMESTAMP(6) | 11 | Y |
| 64 | LOCATION | VARCHAR2 | 400 | Y |
| 65 | ORDER_SIZE_CHANGE | NUMBER | 22 | Y |
| 66 | IS_AFFILIATED | VARCHAR2 | 40 | Y |
| 67 | INVESTOR_CLASSIFICATION | VARCHAR2 | 800 | Y |
| 68 | MISC_DRB_FILL_OR_KILL_INDICATOR | VARCHAR2 | 4 | Y |
| 69 | ALLOCATION_COMMS_BANK | VARCHAR2 | 400 | Y |
| 70 | ISN_BND | VARCHAR2 | 400 | Y |
| 71 | ISN_INVESTOR_NAME | VARCHAR2 | 800 | Y |
| 72 | GEOGRAPHY | VARCHAR2 | 400 | Y |
| 73 | CUSTOM_TAG | VARCHAR2 | 400 | Y |
| 74 | ESG_TAG | VARCHAR2 | 400 | Y |
| 75 | MISC_DRB_INVESTOR_ORDER_ID | VARCHAR2 | 800 | Y |
| 76 | MISC_DRB_INVESTOR_OU | VARCHAR2 | 2000 | Y |
| 77 | EXTERNAL_ORDER_ID | VARCHAR2 | 200 | Y |
| 78 | ALL_OWNERS | VARCHAR2 | 2000 | Y |
| 79 | DIRECT_INVESTOR_ORDER | VARCHAR2 | 24 | Y |
| 80 | EXTERNAL_NAME | VARCHAR2 | 1200 | Y |
| 81 | SCRUBBED_INVESTOR_NAME | VARCHAR2 | 800 | Y |
| 82 | DG_EVENT_ID | VARCHAR2 | 240 | Y |

### OB_ORDER_MATCH_GROUP (61 columns)

| # | Column | Type | Len | Null |
|---|---|---|---|---|
| 1 | UUID | NUMBER | 22 | N |
| 2 | **ORDER_GROUP_ID** | VARCHAR2 | 600 | N |
| 3 | **PRIMARY_ORDER_ID** | VARCHAR2 | 600 | Y |
| 4 | ITEM_TYPE | VARCHAR2 | 400 | Y |
| 5 | ITEM_DEFINITION_ID | VARCHAR2 | 400 | Y |
| 6 | ITEM_SOURCE | VARCHAR2 | 280 | Y |
| 7 | ROOT_ID | VARCHAR2 | 400 | Y |
| 8 | PARENT_ID | VARCHAR2 | 400 | Y |
| 9 | IS_ACTIVE | VARCHAR2 | 40 | Y |
| 10 | STATUS | VARCHAR2 | 400 | Y |
| 11 | BND | VARCHAR2 | 800 | Y |
| 12 | ISN_BND | VARCHAR2 | 400 | Y |
| 13 | **FINAL_ALLOC** | **NUMBER** | 22 | Y |
| 14 | AFFIRM | VARCHAR2 | 200 | Y |
| 15 | DRAFT_ALLOC | VARCHAR2 | 200 | Y |
| 16 | ISN_ALLOC | VARCHAR2 | 200 | Y |
| 17 | SOFT_ALLOC | VARCHAR2 | 200 | Y |
| 18 | RECONCILE | VARCHAR2 | 200 | Y |
| 19 | RETENTION | VARCHAR2 | 200 | Y |
| 20 | RATIONALE | VARCHAR2 | 1020 | Y |
| 21 | RATIONALE_TYPE | VARCHAR2 | 1000 | Y |
| 22 | CRITERIA | VARCHAR2 | 200 | Y |
| 23 | FX_CURRENCY | VARCHAR2 | 200 | Y |
| 24 | ACTION | VARCHAR2 | 120 | Y |
| 25 | EVENT_ID | VARCHAR2 | 240 | Y |
| 26 | PUBLISHED_TS | TIMESTAMP(6) | 11 | Y |
| 27 | SOURCE_SYSTEM | VARCHAR2 | 240 | Y |
| 28 | CLASSIFICATION | VARCHAR2 | 200 | Y |
| 29 | APP_ID | NUMBER | 22 | Y |
| 30 | DG_ENTITY_KEY | VARCHAR2 | 240 | N |
| 31 | DATASET | VARCHAR2 | 240 | Y |
| 32 | VERSION | VARCHAR2 | 400 | N |
| 33 | UPDATED_BY | VARCHAR2 | 80 | Y |
| 34 | UPDATED_TS | TIMESTAMP(6) | 11 | Y |
| 35 | CREATED_BY | VARCHAR2 | 80 | Y |
| 36 | CREATED_TS | TIMESTAMP(6) | 11 | Y |
| 37 | REF_SOURCE_VERSION | VARCHAR2 | 400 | Y |
| 38 | REF_SOURCE_REF_ID | VARCHAR2 | 200 | Y |
| 39 | REF_SOURCE_PRIMARY_ORDER_ID | VARCHAR2 | 600 | Y |
| 40 | **REF_SOURCE_SECONDARY_ORDER_LIST** | VARCHAR2 | 20000 | Y |
| 41 | REF_SOURCE_GROUP_STATUS | VARCHAR2 | 600 | Y |
| 42 | REF_SOURCE_LAST_MODIFIED_BANK | VARCHAR2 | 1020 | Y |
| 43 | REF_SOURCE_IS_ALIVE | VARCHAR2 | 40 | Y |
| 44 | REF_SOURCE_LAST_ACTION_MATCHGROUP_ID | VARCHAR2 | 600 | Y |
| 45 | REF_SOURCE_ACTION_TYPE | VARCHAR2 | 600 | Y |
| 46 | REF_SOURCE_LAST_ACTION_DESCRIPTION | VARCHAR2 | 2000 | Y |
| 47 | REF_SOURCE_LAST_MODIFIED_USER | VARCHAR2 | 80 | Y |
| 48 | REF_SOURCE_SYSTEM | VARCHAR2 | 280 | Y |
| 49 | DG_CREATED_BY | VARCHAR2 | 200 | Y |
| 50 | DG_CREATED_TS | TIMESTAMP(6) | 11 | Y |
| 51 | DG_UPDATED_BY | VARCHAR2 | 200 | Y |
| 52 | DG_UPDATED_TS | TIMESTAMP(6) | 11 | Y |
| 53 | DG_PROCESSED_BY | VARCHAR2 | 200 | N |
| 54 | DG_PROCESSED_TS | TIMESTAMP(6) | 11 | N |
| 55 | DG_EVENT_ID | VARCHAR2 | 60 | N |
| 56 | DG_VERSION | NUMBER | 22 | N |
| 57 | CUSTOM_TAG | VARCHAR2 | 400 | Y |
| 58 | ESG_TAG | VARCHAR2 | 400 | Y |
| 59 | GB_ALLOC | NUMBER | 22 | Y |
| 60 | GB_BND | VARCHAR2 | 800 | Y |
| 61 | INVESTOR_CLASSIFICATION | VARCHAR2 | 800 | Y |

### OB_ORDER_SIZE (28 columns)

| # | Column | Type | Len | Null |
|---|---|---|---|---|
| 1 | UUID | NUMBER | 22 | N |
| 2 | ORDER_ID | VARCHAR2 | 600 | N |
| 3 | **TYPE** | VARCHAR2 | 400 | Y |
| 4 | **AMT** | NUMBER | 22 | Y |
| 5 | AMT_CHANGE | NUMBER | 22 | Y |
| 6 | PRICE_DEMAND | NUMBER | 22 | Y |
| 7 | SPREAD_DEMAND | NUMBER | 22 | Y |
| 8 | MIN_SIZE | NUMBER | 22 | Y |
| 9 | MAX_SIZE | NUMBER | 22 | Y |
| 10 | MIN_YIELD | NUMBER | 22 | Y |
| 11 | GSP_ENTITY_ID | NUMBER | 22 | Y |
| 12 | FLOATING_RATE_INDEX | VARCHAR2 | 400 | Y |
| 13 | ISIN | VARCHAR2 | 80 | Y |
| 14 | CUSIP | VARCHAR2 | 80 | Y |
| 15 | MATURITY_TS | VARCHAR2 | 200 | Y |
| 16 | COUPON | VARCHAR2 | 80 | Y |
| 17 | COUPON_TYPE | VARCHAR2 | 400 | Y |
| 18 | BS_FLOATING_RATE_INDEX | VARCHAR2 | 400 | Y |
| 19 | BS_FLOATING_RATE_TENOR | VARCHAR2 | 400 | Y |
| 20 | ISSUER | VARCHAR2 | 400 | Y |
| 21 | SPREAD | VARCHAR2 | 80 | Y |
| 22 | EMPTY_BENCHMARK | VARCHAR2 | 80 | Y |
| 23 | PROCESSED_BY | VARCHAR2 | 80 | N |
| 24 | PROCESSED_DATE | DATE | 7 | N |
| 25 | DG_VERSION | NUMBER | 22 | Y |
| 26 | CREATED_TS | TIMESTAMP(7) | 11 | Y |
| 27 | UPDATED_TS | TIMESTAMP(7) | 11 | Y |
| 28 | MIN_ALLOCATION | NUMBER | 22 | Y |

---

## Q34 — do the two FINAL_ALLOC columns agree?

`OB_ORDER_MATCH_GROUP m JOIN OB_ORDER o ON o.ORDER_ID = m.PRIMARY_ORDER_ID`

| Metric | Count | % |
|---|---|---|
| PRIMARY_ORDERS_MATCHED | 29,681 | 100% |
| ALLOC_EQUAL | 24,230 | 81.6% |
| ALLOC_DIFFERS | 5,451 | 18.4% |
| ONLY_MATCHGROUP_HAS | 5,413 | 18.2% |
| ONLY_ORDER_HAS | 4 | 0.01% |

Decomposition of the 5,451 differences:

| Case | Count |
|---|---|
| order NULL, match group has a value | 5,413 |
| order has a value, match group NULL | 4 |
| both non-null but values disagree | **34** |

### What this settles

- **`OB_ORDER.FINAL_ALLOC` alone is NOT sufficient.** It is NULL for 5,413
  primary orders (18.2%) where the match group carries the allocation.
  Dropping the join would silently zero those out — `NVL(...,0)` in the view
  turns a missing allocation into a reported **0**, not a NULL.
- **The match group is very nearly a superset**: only 4 rows have an order-side
  value the match group lacks.
- **Genuine conflicts are rare** — 34 rows where both are populated and differ.
  Needs a tiebreak rule but is not a blocker.
- **`PRIMARY_ORDER_ID` is a usable join key**, which is the real fix: replace
  the `(ROOT_ID, PARENT_ID)` key with it.

### Still open before the fix can be written

1. **Non-primary orders.** This query only covers orders that ARE a
   `PRIMARY_ORDER_ID`. Orders appearing only in
   `REF_SOURCE_SECONDARY_ORDER_LIST` are untested — do they get an allocation?
   → Q6, Q8.
2. **Which side wins on the 34 conflicts** — inspect a sample.
3. **Match-group grain per primary order** — if `PRIMARY_ORDER_ID` is not
   unique in `OB_ORDER_MATCH_GROUP`, joining on it still fans out. Not yet
   measured; added as Q35.

---

## Q6 — what a match group actually is (sample of 20)

Read via OCR (screenshot exceeded the image-reader size cap), so **per-row
column alignment is unreliable**. The structural facts below are legible and
consistent across all 20 rows; do not quote individual cell values.

Fetched 20 rows in 0.059s.

| Field | What the sample shows |
|---|---|
| ORDER_GROUP_ID | unique per row (`I-240723-885637490490`, …) |
| PRIMARY_ORDER_ID | populated on most rows, **NULL on some** (rows 2, 3) |
| ROOT_ID / PARENT_ID | **repeat heavily** — 13 of 20 rows share `I-240618-062736259063` / `I-240618-062736669439` |
| STATUS | `updated` on every row |
| IS_ACTIVE | `Y` on every row |
| FINAL_ALLOC | mix of `0` and real notionals (3.5m, 7m, 11m, 12m, 13m, 15m, 44m, 100k, 123m) |
| GB_ALLOC | almost entirely NULL |
| SECONDARY_LIST_LEN | almost entirely NULL |

### What this settles

1. **The fan-out is real and large.** 13 of 20 sampled rows sit on a single
   `(ROOT_ID, PARENT_ID)`. The current view joins on exactly that pair, so
   every DCM order on that tranche is currently multiplied ~13×, each copy
   carrying a different `FINAL_ALLOC`. This is worse than "same value on every
   order" — it is duplication *and* wrong values.
2. **A match group is one-per-order, not one-per-tranche.** `ORDER_GROUP_ID` is
   unique per row and `SECONDARY_LIST_LEN` is almost always NULL, so these are
   not aggregating several orders. Combined with Q34 (81.6% agree with the
   order's own allocation) the table behaves as an order-level allocation
   record keyed by `PRIMARY_ORDER_ID`.
3. **`PRIMARY_ORDER_ID` is nullable**, so a plain inner join on it drops rows —
   the replacement join must be a LEFT JOIN from the order side, which is the
   correct direction anyway.
4. **`FINAL_ALLOC` includes legitimate `0`s**, so the view's `NVL(...,0)` makes
   "allocated nothing" and "no allocation record" indistinguishable.

### Emerging fix for vw_order_detail (DCM branch)

Replace the `(ROOT_ID, PARENT_ID)` join with a `PRIMARY_ORDER_ID` join, and
coalesce order-side over match-group side (or the reverse — Q36 decides).
Still gated on **Q35** (is `PRIMARY_ORDER_ID` unique in the match-group table?)
and **Q37** (do non-primary orders get an allocation at all?).

---

## Q9 / Q9b — grain integrity  ⚠️ ALL FOUR VIEWS FAIL

| Object | rows_ | grain_ | verdict |
|---|---|---|---|
| deal | 43,415 | 39,467 | **fails** |
| tranche | 89,651 | 69,380 | **fails** |
| order | 11,881,246 | 5,874,386 | **fails — ~2× duplication** |
| entity | 177,972 | 51,169 | fails (partly by design — branches also group by NAME) |

Deal view split by product (Q9b):

| PRODUCT | rows_ | deals_ |
|---|---|---|
| ECM | 22,347 | 18,399 |
| DCM | 21,068 | 21,068 |

**The deal-view violation is entirely ECM.** DCM is exactly 1:1. The ECM gap
(3,948) accounts for the whole deal-object gap.

## Q10 — is a deal one ECM transaction?  NO

`OPUS_ECM_TRANSACTION`: 44,829 rows / 43,718 distinct `ECM_TRANSACTION_ID` /
41,779 distinct `DEAL_TRANSACTION_ID`.

Two separate defects feeding the ECM fan-out:
1. One deal maps to **several ECM transactions** (43,718 txns > 41,779 deals),
   so keying the deal view on `DEAL_TRANSACTION_ID` while joining on
   `ECM_TRANSACTION_ID` cannot yield one row per deal.
2. `OPUS_ECM_TRANSACTION` itself has **duplicate `ECM_TRANSACTION_ID`s**
   (44,829 rows > 43,718 distinct).

## Q11 — multiple Execution_Status rows per transaction:  1,356

Confirmed. This INNER JOIN appears in the deal, tranche **and** order views, so
one offending transaction multiplies all three simultaneously.

## Q12 — unguarded joins:  every single one fans out

| Check | Offenders |
|---|---|
| OPUS_BASE_TRANSACTION per TRANSACTION_ID | 39,606 |
| TRANCHE_PRODUCT_DETAIL per tranche | 1,737 |
| TRANCHE_DEMAND_CURRENCY per tranche+ccy | 4,547 |
| OB_ECM_ORDER_IOI per ORDER_ID | 20,739 |
| OB_ECM_ORDER per ORDER_ID | 101 |
| OB_ORDER_SIZE per ORDER_ID | 314 |
| OB_ORDER per ORDER_ID | 6 |
| OB_DEAL_ISSUER per DEAL_TRANCHE_ID | 156 |
| OB_DEAL_TRANCHE per DEAL_ID+TRANCHE_ID | (not legible) |

⚠️ OCR could not reliably pair value to label; treat the individual numbers as
indicative. The conclusion that matters is unambiguous and mapping-independent:
**every join on this list has offenders, so every one must be guarded.** The
fix is designed to that, not to the counts.

`OPUS_BASE_TRANSACTION` is the worst — it is a plain `LEFT JOIN` in both the
deal and tranche views purely to fetch `DEAL_REGION`.

## Q13 / Q14 — TRANCHE_OFFER_SIZE is 100% numeric

66,571 non-null values, **0 non-numeric**. Q14 returned zero rows.

The `CAST(... AS VARCHAR2(120))` in the ECM branch is pure damage — no data
requires it. Removing it makes `TRANCHE_SIZE` a proper `NUMBER` and fixes the
lexical sort ('900' beating '1000000') with no conversion risk.

## Q17 — DCM statuses  ⚠️ `confidential` EXISTS AND IS NOT FILTERED

16 distinct values on `OB_DEAL_TRANCHE.STATUS`:

| Status | rows_ | deals_ |
|---|---|---|
| Settled | 25,772 | 15,513 |
| priced | 4,231 | 2,505 |
| announced | 2,187 | 1,564 |
| Announced | 2,076 | 649 |
| draft | 923 | 623 |
| freeToTrade | 403 | 240 |
| cancelled | 304 | 226 |
| allocated | 212 | 163 |
| Priced | 111 | 74 |
| subject | 58 | 47 |
| archived | 33 | 26 |
| deleted | 17 | 16 |
| postponed | 16 | 14 |
| **confidential** | **14** | **12** |
| (null) | 12 | 2 |
| Final Settled | 2 | — |

Three findings:

1. **`confidential` exists on DCM and no view excludes it.** ECM excludes
   Confidential/Withdrawn/Terminated everywhere; DCM excludes nothing. Also
   unfiltered: `cancelled`, `deleted`, `archived`, `draft`, `postponed`.
2. **Case-variant duplicates**: `announced`/`Announced` and `priced`/`Priced`
   are distinct stored values. Any status filter — in the view or the
   ontology — must be case-insensitive, and the ontology's allowed-value list
   is currently wrong.
3. A NULL status and a space-containing value (`Final Settled`) both exist.

## Q8 — allocation reconciliation  ✅ OB_ORDER.FINAL_ALLOC IS AUTHORITATIVE

Five busiest DCM tranches. Query took **28.9 seconds**.

| ROOT_ID | ORDER_CNT | TRANCHE_SIZE | SUM_ORDER_ALLOC | ORDERS_WITH_ALLOC | MATCH_GROUP_ROWS |
|---|---|---|---|---|---|
| I-230109-…011684 | 2,870 | (null) | 749,800,000 | 401 | **(null)** |
| I-230109-…011684 | 2,820 | (null) | 992,000,000 | 406 | **(null)** |
| 1500009396 | 2,762 | 3,000,000,000 | 2,958,900,000 | 2,762 | **(null)** |
| 1447715114 | 2,723 | 1,000,000,000 | 1,000,000,000 | 2,723 | **(null)** |
| 1447601646 | 2,522 | 2,250,000,000 | 2,239,050,000 | 2,522 | **(null)** |

Two decisive results:

1. **`SUM(OB_ORDER.FINAL_ALLOC)` reconciles to `TRANCHE_SIZE`** — exactly on one
   tranche, 98.6% and 99.5% on the others. That is the allocation book.
2. **`OB_ORDER_MATCH_GROUP` has NO rows at all for these tranches.** So the
   view's `LEFT JOIN` yields NULL and `NVL(OMT.FINAL_ALLOC, 0)` reports
   **ORDER_ALLOCATION = 0 for every order on the busiest tranches.**

So the DCM allocation defect is not merely "wrong value" — for high-volume
tranches it is **silently zero**, while the correct figure sits unused on the
order row. Fix: source `ORDER_ALLOCATION` from `OB_ORDER.FINAL_ALLOC` and drop
the match-group join. Q34's 5,413 order-NULL/matchgroup-populated rows are the
only reason to keep a coalesce; Q35/Q37 decide whether that is worth a join.

Incidental: DCM ids come in two formats — `I-230109-080151011684` and bare
numerics like `1500009396`. Consistent with `TRANCHE_SIZE` being NULL on the
`I-`-prefixed rows. Two source systems behind `OB_DEAL_TRANCHE`.

---

## Q35 / Q36 / Q37 — allocation source, settled

**Q35** `OB_ORDER_MATCH_GROUP`: 78,027 rows with a primary order / 76,085
distinct / **worst case 4 rows per primary order**. So `PRIMARY_ORDER_ID` is
NOT unique — joining on it would still fan out.

**Q37 — the decisive one.**

| Metric | Count |
|---|---|
| all DCM orders | 5,863,603 |
| is a PRIMARY_ORDER_ID | 27,739 (**0.47%**) |
| not a primary order | 5,835,864 |
| non-primary orders carrying their OWN FINAL_ALLOC | 5,266,360 |

The match-group table is reachable from **less than half a percent** of DCM
orders, while 5.27M non-primary orders carry their own allocation. Combined
with Q8 (order-side sums reconcile to tranche size; match group absent entirely
for the busiest tranches), this is conclusive:

> **Delete the `OB_ORDER_MATCH_GROUP` join. Source `ORDER_ALLOCATION` from
> `OB_ORDER.FINAL_ALLOC`.** No coalesce, no replacement join — the fix removes
> SQL rather than adding it.

**Q36** — the 34 conflicts are mostly `ORD_ALLOC = 0` against a populated
`MG_ALLOC`, i.e. `0` is sometimes used where no allocation was recorded. 34
rows against 5.27M; not worth a join. One row shows `mg_status = 'pending'`
where the rest are `updated`.

## Q19 — DCM order statuses are unfiltered

25 combinations of `STATUS` / `IS_ACTIVE` / `IS_FIRM_ORDER`. Dominated by two
opaque codes — `XB` (2,675,885) and `B` (2,038,170) — which together are ~80%
of all DCM orders. Also present and **not excluded anywhere**: `cancelled`
(9,869), `deleted` (2,903 + 275 + 24), plus `A`, `D`, `R`, `FR`, `PN`, `F`,
`XR`, `new`, `booked`, `accepted`, `updated`, `subject`, and NULL.

ECM excludes `CANCELLED`/`DELETED`/`PASS` and requires `IS_OWNED = 'true'`.
DCM applies no equivalent. `IS_FIRM_ORDER` (true/false/null) and `IS_ACTIVE`
(Y/null) exist and are also unused.

## Q20 — DCM order counts genuinely diverge

5,863,603 orders total; **37,517 have no matching `(DEAL_ID, TRANCHE_ID)` row**
in `OB_DEAL_TRANCHE`, spanning 586 deals, out of 19,155 deals with orders.

Those 37,517 are dropped by the order view's INNER JOIN but still counted by
the deal view's unfiltered `OB_ORDER` subquery. Confirms the count-honesty
break: the deal card and the paged order list disagree on 586 deals.

## Q21 — DCM repeated currencies: 6,940 deals

Confirmed at scale. Those deals render `CURRENCIES` as `USD | USD | USD`.

## Q23 — DELIVERY_TYPE should not be a LISTAGG at all

| Metric | Value |
|---|---|
| tranches | 32,862 |
| exactly one distinct DELIVERY_TYPE | 6,054 |
| more than one | **17** |
| max identifier rows per tranche | **1,304** |

Only 17 tranches out of 32,862 have more than one distinct delivery type, so
`DELIVERY_TYPE` is effectively **per-tranche, not per-identifier**. But it is
`LISTAGG`-ed across identifier rows, so a tranche with 1,304 identifiers
renders the same value **1,304 times**, pipe-separated. That is both unreadable
and a genuine ORA-01489 risk even against the 32,767 limit.

Fix: `MAX(T.DELIVERY_TYPE)`, not `LISTAGG`.

## Q24 — identifier zip misalignment: 6,223 tranches

Tranches with two or more identifiers sharing one `IDENTIFIER_TYPE`. The ECM
LISTAGGs order by `IDENTIFIER_TYPE` alone, so within those ties the type list
and value list can zip in different orders. Needs `IDENTIFIER_VALUE` as a
tiebreaker on both LISTAGGs.

## Q25 — BND_BANK drops co-B&D banks: 850 tranches

850 tranches have more than one syndicate member flagged `BND_BROKER = 'true'`.
`MAX(CASE WHEN ...)` silently keeps only the alphabetically-last.

## Q26 — TENORS renders a bare hyphen

| Metric | Value |
|---|---|
| rows | 36,371 |
| both TENOR_VALUE and TENOR_PERIOD null | **4,808** |
| value null only | 21 |
| period null only | 21 |

`NULL || '-' || NULL` is `'-'`, so **4,808 tranches show a lone hyphen** where
the answer is "not recorded", plus 42 rows rendering `'5-'` or `'-Y'`.

## Q28 / Q29 — entity view

**Q28 returned FIVE groups, not six.**

| ENTITY_TYPE | PRODUCT | rows_ | distinct_ids | null_names |
|---|---|---|---|---|
| DEAL | DCM | 21,068 | 21,068 | 1 |
| DEAL | ECM | 22,347 | 18,399 | 343 |
| INVESTOR | DCM | 124,668 | 9,871 | 0 |
| INVESTOR | ECM | 2,982 | 1,157 | 0 |
| ISSUER | DCM | 6,907 | 671 | 0 |
| **ISSUER** | **ECM** | **— absent —** | | |

Findings:

1. **There are no ECM issuer entities at all.** Issuer name resolution silently
   returns nothing for ECM users. The ISSUER branch filters
   `WHERE D.ISSUER_NAME IS NOT NULL` against `VW_DEAL_SUMMARY`, so ECM's
   `ISSUER_NAME_FROM_SOURCE` appears to be entirely NULL.
2. **Grain violation confirmed** — INVESTOR/DCM has 124,668 rows for 9,871 ids
   (12.6 name variants per investor); DEAL/ECM 22,347 rows for 18,399 ids.
3. **343 NULL entity names** on the DEAL/ECM branch — the missing
   `IS NOT NULL` guard, exactly as predicted.
4. This query took **79.4 seconds**.

**Q29** — the BlackRock lookup took **9.4 seconds** and returned:

- `ENTITY_ID` is **NULL** on 2 of 10 candidates (`BlackRock London`,
  `BlackRock (Singapore) Limited`) — useless as drill-down handles.
- Duplicate ids across rows: `00918` for both `BlackRock` and `BLACKROCK`;
  `41364` for both `Blackrock Financial Mgmt - NY` and
  `Blackrock Financial Management, Inc.`

Case-variant and punctuation-variant names under one id are exactly the
`entity_count` vs `row_count` problem in the ontology.

## Q32 — SETTLEMENT_TS is empty

22,347 ECM deals, **0 with a settlement timestamp**. It is a placeholder like
`SETTLEMENT_CURRENCY`. Do not model it — instead correct the ontology refusal
text that currently promises "pricing and settlement dates".

## Q18 — NOT RUN, and not needed

Q18 would have counted DCM deals with tranches in mixed statuses, to judge
whether `MAX(ODT.STATUS)` is safe on the deal view. Q17 already settles it:
`STATUS` contains case-variant duplicates (`priced`/`Priced`,
`announced`/`Announced`), and `MAX()` on text picks lowercase over uppercase by
codepoint. So the aggregate is unsound regardless of how often statuses differ.

---
---

# ROUND 2 — validation of the rewritten views (V1–V17)

Each V-query ran the rewritten view body as a SELECT, so a result proves both
that the SQL compiles and whether the grain assertion holds.

| Query | Verdict |
|---|---|
| V1 ECM deal branch | ✅ **PASS** |
| V2 DCM currency dedupe | ✅ **PASS** |
| V3 ECM order branch | ❌ **FAIL** — 365 residual duplicates |
| V4 DCM order branch | ✅ **PASS** grain; allocation now non-zero |
| V5 tranche spine | ❌ **FAIL** — 1,835 duplicate (txn,tranche) pairs |
| V8 DCM tranche size | 💥 **ORA-01722** |
| V12 allocation reconcile | 💥 **ORA-01722** |
| V15 | still running |

## V1 — ECM deal branch: PASS

| rows_ | deals_ | total_tranches | max_currencies_len |
|---|---|---|---|
| 18,399 | 18,399 | 34,599 | 19 |

**rows_ = deals_.** The old view was 22,347 rows for 18,399 deals; the
GROUP BY collapse works, and it ran in 0.9s.

## V2 — DCM currency dedupe: PASS

Zero rows. No deal renders a repeated currency any more (was 6,940).

## V3 — ECM order branch: FAIL

| rows_ | orders_ | excess |
|---|---|---|
| 48,667 | 48,302 | **365** |

Cause identified by V5: `OPUS_ECM_TRANSACTION_TRANCHE` was the one join in
this branch still going in raw. Fixed; re-test is **V22**.

(48,302 ECM + 5,826,084 DCM = 5,874,386 = exactly the Q9 distinct-order total,
so the two branches reconcile.)

## V4 — DCM order branch: PASS

| rows_ | orders_ | sum_alloc | orders_with_alloc |
|---|---|---|---|
| 5,826,084 | 5,826,084 | 1,308,958,060,851,846.4 | 1,747,582 |

Grain holds, and allocation is populated where the deployed view reports zero.
`sum_alloc` looks high against tranche sizes — **V21** re-checks it.

## V5 — tranche spine: FAIL ⚠️ this was my known gap

`OPUS_ECM_TRANSACTION_TRANCHE` has **1,835** duplicate `(ECM_TRANSACTION_ID,
ECM_TRANSACTION_TRANCHE_ID)` pairs. It is the FROM of the tranche view and a
raw join in the order view, so both still fan out.
-> both now dedupe it by ROWID. The deal view is unaffected because its tranche
subqueries already use `COUNT(DISTINCT ...)` and `SELECT DISTINCT`, which V1
confirms.

## V6 — tranche id uniqueness

72,403 rows / 70,568 distinct tranche ids / 70,567 distinct (txn,tranche).
Excess of ~1,836 matches V5. Tranche ids are effectively globally unique, so
the `txn||'~'||tranche` composite in the deal view is belt-and-braces, not
load-bearing.

## V7 — NULL DEAL_TRANSACTION_ID

44,829 transaction rows; the guard I added costs nothing measurable.

## V8 — 💥 ORA-01722 — **DCM TRANCHE_SIZE IS NOT NUMERIC**

`COUNT(CASE WHEN TRANCHE_SIZE > 1000000000 ...)` raised *invalid number*.
Comparing the column to a number forces a conversion that fails, which proves
it is character data holding values Oracle cannot convert.

**This disproves the reasoning I used to revert the DCM guard.** I argued from
the deployed `VARCHAR2(480)` = 120 CHAR × 4 bytes that DCM was already numeric
and only the ECM cast was widening it. Wrong. Removing the ECM cast alone will
NOT yield a NUMBER column while DCM stays text.
-> blocked on **V18/V19** to see the bad values before writing the conversion.

## V9 — ECM tranche size expression: PASS

72,403 rows, min 0, max 1.0000E+11 (100bn), **would_become_zero = 0**.
The expression now in the view is safe on every current ECM row.

## V10 — MAX() collapse blast radius: small

~20 multi-transaction ECM deals, ~9 disagreeing. Partially legible; the
magnitude is what matters and it is negligible.

## V11 — where MAX() is CHOOSING, not deduplicating

| Aggregate | Keys whose duplicates hold different values |
|---|---|
| OPUS_BASE_TRANSACTION.DEAL_REGION | 261 |
| TRANCHE_PRODUCT_DETAIL.SECURITY_TYPE_NAME | 0 |
| TRANCHE_DEMAND_CURRENCY.CURRENCY_NAME | 0 |
| **OB_ECM_ORDER_IOI.LIMIT_VALUE** | **14,341** |
| OB_ORDER_SIZE.AMT | 264 |
| OB_DEAL_ISSUER.NAME | 0 |
| EXEC_STATUS.STATUS_VALUE | 115 |

Three are lossless. Four are real choices, and `LIMIT_VALUE` is the one that
matters: 14,341 ECM orders have several IOI limit points — a demand curve —
and `MAX()` now reports the highest. That is a defensible reading of
ORDER_AMOUNT but it IS a decision, and it must be stated in the ontology.

## V13 — list lengths under the new keying: PASS

deal currencies 22 chars · bnd_bank 101 · dcm identifier values 531.
All far below 32,767; no overflow risk from the re-keying.
(Supersedes the Q23 reading of 1,304 identifiers per tranche, which the OCR
likely garbled.)

## V14 — ⚠️ ECM ISSUER NAME **IS** POPULATED

44,829 transaction rows, with issuer name / gfcid / ticker / sector all in the
42,203–42,872 range, and deal name on 18,156.

**This contradicts the conclusion I drew from Q28.** I reported "there are no
ECM issuer entities at all" from a five-group result where ISSUER/ECM was
absent. The source column is well populated, so that was almost certainly an
OCR-dropped row, not a real defect. V15 settles it.

## V12 — 💥 ORA-01722, same root cause as V8

`SUM` over `NVL(TRANCHE_SIZE,0)` inherits the character type and fails.
Re-run guarded as **V21**.

---

# ROUND 3 — V18–V24

| Query | Verdict |
|---|---|
| V18/V19 TRANCHE_SIZE values | ✅ diagnosed — scientific notation, not garbage |
| V20 DEAL_ISSUE_SIZE | ✅ clean |
| V21 allocation reconcile | ⚠️ inconclusive **by design flaw in my query** |
| V22 ECM order grain | ✅ **PASS** 48,302 = 48,302 |
| V23 ECM tranche grain | ❌ 33,011 vs 33,010 — **one** duplicate |
| V24 DCM tranche grain | ❌ 36,371 vs 36,370 — **one** duplicate |
| V15 | cancelled, too slow — moot after V14 |

## V18 / V19 — the "invalid number" values are SCIENTIFIC NOTATION

34,861 non-null DCM tranche sizes, **44 non-numeric** under my strict regex.
And they are not garbage:

`11.25E9` ×6 · `21.0E9` ×5 · `6.0E8` ×4 · `5.0E8` ×4 · `7.5E8` ×4 ·
`3.0E8` ×2 · `1.4E9` ×2 · `2.3E9` · `5.5E8` · `8.5E8` · `1.6E9` · `2.25E9` ·
`9.0E8` · `1.5E8` · `4.0E8` · `1.5E9` · `4.5E8` · `1.1E9` · `8.0E8` · `5.0E7` ·
`2.0E9` · `3.25E8` · `1.7E9` … and one literal **`1k`**.

43 of the 44 are E-notation for real multi-billion tranches. **My original
strict regex would have converted every one of them to 0** — silently
destroying the largest tranches in the book while appearing to fix the column.
Catching this is the single best return from this round.

-> regex widened to accept `[Ee][+-]?[0-9]+` on both branches. The one
   unparseable value becomes NULL, never 0.

## V20 — DEAL_ISSUE_SIZE is clean

35,268 non-null, 0 non-numeric. DCM `DEAL_SIZE` needs no change.

## V21 — inconclusive, and that is my query's fault

| sum_tranche_size | sum_order_alloc | sum_matchgroup_alloc | tranches |
|---|---|---|---|
| 70,262,179,462,948.87 | 1,308,958,138,351,846.4 | 12,856,146,081,514,577.21 | 36,370 |

Order allocation is ~18.6× tranche size, which looks alarming until you notice
the query **sums raw notionals across currencies**. A JPY tranche contributes
~150× a USD tranche of equal value, so the global total is meaningless as a
reconciliation. I should not have written it that way.

The valid evidence is still Q8, which compared **per tranche** (single currency
within a tranche) and found order-side sums matching tranche size exactly on
one and at 98.6% / 99.5% on two others.

What V21 *does* show usefully: `sum_matchgroup_alloc` is ~10× `sum_order_alloc`,
consistent with the match-group table fanning out — more support for dropping
that join.

## V22 — ECM order branch: PASS

48,302 rows = 48,302 orders. Deduping the tranche spine cleared the 365
residual duplicates from V3.

## V23 / V24 — one duplicate each

| Branch | rows_ | tranches_ |
|---|---|---|
| ECM | 33,011 | 33,010 |
| DCM | 36,371 | 36,370 |

**ECM**: I deduped the spine at `(txn, tranche)`, but the declared grain is
`(deal, tranche)`. A deal spanning two transactions that share a tranche id
yields two rows. V6 showed tranche ids are near-globally unique, hence exactly
one collision. -> the dedupe now partitions by `(DEAL_TRANSACTION_ID,
TRANCHE_ID)`, matching the declared grain rather than the physical key.

**DCM**: `OB_DEAL_TRANCHE` has one duplicate `(DEAL_ID, TRANCHE_ID)` — this is
the V5 line the OCR could not read. -> deduped by ROWID.

Both are single rows, but a view whose declared grain is violated at all is a
view the planner cannot trust, which is the entire premise of the split.

---

# ROUND 4 — V25/V26/V27: ALL PASS

| Query | Result | Verdict |
|---|---|---|
| V25 TRANCHE_SIZE | 34,861 non-null · **43** e-notation converted · **1** unconvertible · max 10,000,000,000,000 | ✅ |
| V26 ECM tranche grain | 33,010 = 33,010 | ✅ |
| V27 DCM tranche grain | 36,370 = 36,370 | ✅ |

All four views now hold their declared grain on QA:

| Object | rows = grain | evidence |
|---|---|---|
| deal (ECM) | 18,399 = 18,399 | V1 |
| order (ECM) | 48,302 = 48,302 | V22 |
| order (DCM) | 5,826,084 = 5,826,084 | V4 |
| tranche (ECM) | 33,010 = 33,010 | V26 |
| tranche (DCM) | 36,370 = 36,370 | V27 |

## ⚠️ THESE NUMBERS ARE QA. THEY ARE NOT THE ACCEPTANCE CRITERIA.

The acceptance criterion is the **invariant** `rows_ = grain_`, not any of the
figures above. PROD is larger and more varied; every count here will differ.
Re-run V26/V27 and the Q9 grain check against PROD before and after deploy.

Specifically, QA under-represents:

- **Volume.** PROD deals carry ~2,000 orders. QA's largest tranche had 2,870
  orders across the whole book.
- **Variety.** QA had exactly ONE unparseable tranche size (`1k`) and ONE
  duplicate `(deal, tranche)` key. Both are certain to be more common in PROD.
  Both are handled by construction — unparseable becomes NULL, duplicates are
  deduped — so the design scales even though the counts do not.
- **List lengths.** V13 measured 531 chars max. A PROD tranche with far more
  identifiers or syndicate members could approach the 32,767 ceiling, where
  LISTAGG raises ORA-01489 and kills the entire query.
  -> **all 12 LISTAGGs now carry `ON OVERFLOW TRUNCATE '...' WITH COUNT`**, so
     an oversized list truncates visibly instead of failing the query.
     Requires Oracle 12.2+; if the data team hits a compile error on that
     clause, deleting it is a safe one-line revert per LISTAGG.

## Open PROD-scale risks that the SQL cannot solve on its own

1. **The ROW_NUMBER dedupes sort large tables.** `OB_ORDER` (5.86M in QA,
   more in PROD) and `OB_ECM_ORDER` are each wrapped in a window function to
   remove 6 and 101 duplicate rows respectively. If `ORDER_ID` is indexed
   Oracle can satisfy this without a full sort; if not, every query against
   the order view — and therefore every entity-search resolution, which sits
   on top of it — pays a sort of the whole table.
   **Ask the data team to confirm an index on `ORDER_ID`, and to fix the
   source duplicates so the window can be removed entirely.**
2. **`MAX()` is choosing, not deduplicating, in four places** (V11), the
   largest being 14,341 ECM orders whose IOI rows hold different
   `LIMIT_VALUE`s — a demand curve. `ORDER_AMOUNT` currently reports the
   highest limit. That ratio will hold or grow in PROD. Still an open
   business decision: highest, lowest, or latest.
3. **`max_size` of 10,000,000,000,000** on a DCM tranche (V25) is either a
   large JPY notional or a data error. Not blocking, worth a look.
