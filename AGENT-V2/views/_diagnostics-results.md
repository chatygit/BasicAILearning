# Diagnostics results — deployed DGSTREAM views

Answers to [`_diagnostics.sql`](_diagnostics.sql), captured as they come back.
Source of truth for the deployed shape — these override any column list in
`V1/docs/VIEW-SPLIT-PROPOSAL.md` or the `app/bqs/ontology/*.yaml` files.

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
| Q4–Q8 DCM allocation | ⏳ pending |
| Q9–Q12 grain integrity | ⏳ pending |
| Q13–Q16 typing | ⏳ pending |
| Q17–Q20 DCM status / counts | ⏳ pending |
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
