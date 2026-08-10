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
| Q35–Q37 allocation | ⏳ pending |
| Q9–Q12 grain integrity | ✅ captured below |
| Q13–Q14 typing | ✅ captured below |
| Q17 DCM status | ✅ captured below |
| Q18–Q20 DCM counts | ⏳ pending |
| Q21–Q27 list columns | ⏳ pending |
| Q28–Q29 entity view | ⏳ pending |
| Q30–Q33 dead columns | ⏳ pending |

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
