# Deal Execution data products — setup steps

Three Starburst data products for the Deal Execution team, built from the live
OneBook MongoDB (catalog `ecm`). Each dataset is one collection, copied as is:
no joins, no business rules. Run everything in the Starburst SQL editor (DEV
first, then UAT, then PROD).

These are separate from our agent's product (`dp_ask_banking`), which reads
the DataGlobe tables and never the live MongoDB.

## 1. What to create

All three products live in catalog **`bds_iceberg_ref`**, next to the existing
`dp_deal_execution_ecm_orders`.

| Product (schema) | Datasets | Source collections (catalog `ecm`) |
|---|---|---|
| `dp_deal_execution_ecm_deal_tranche` | `ds_ecmo_orderbook_details`, `ds_deal`, `ds_syndicate`, `ds_trade_ref` | `ecmo_onebook.ecmo_orderbook_details`, `ecmo_adapter_dealaxis_archival.deal`, `ecmo_adapter_dealaxis_archival.syndicate`, `ecmo_items.trade_ref` |
| `dp_deal_execution_ecm_orders` (**exists**) | `ds_ecm_orders` (**exists**), `ds_pot_allocation`, `ds_pot_order`, `ds_pot_away_order`, `ds_pot_away_allocation` | `ecmo_onebook.ecmo_orders`, `ecmo_adapter_dealaxis_archival.pot_Allocation`, `.pot_Order`, `.pot_away_order`, `.pot_away_allocation` |
| `dp_deal_execution_ecm_trades` | `ds_trade_book`, `ds_trade_designations`, `ds_under_writing_trade_book` | `ecmo_items.trade_book`, `ecmo_items.trade_designations`, `ecmo_items.under_writing_trade_book` |

## 2. Access groups (Active Directory, one per product per environment)

| Product | DEV | UAT | PROD |
|---|---|---|---|
| deal_tranche | `app_banking_sb_dev_execution_ecm_tranche_non_restricted_dp` | `app_banking_sb_uat_execution_ecm_tranche_non_restricted_dp` | `app_banking_sb_execution_ecm_tranche_non_restricted_dp` |
| orders | `app_banking_sb_dev_execution_ecm_orders_non_restricted_dp` | `app_banking_sb_uat_execution_ecm_orders_non_restricted_dp` | `app_banking_sb_execution_ecm_orders_non_restricted_dp` |
| trades | `app_banking_sb_dev_execution_ecm_trades_non_restricted_dp` | `app_banking_sb_uat_execution_ecm_trades_non_restricted_dp` | `app_banking_sb_execution_ecm_trades_non_restricted_dp` |

Grant each group SELECT on its product's schema (Ranger policy or the data
product's access settings).

## 3. Step 1 — check the 12 collections resolve

`columns_ = 0` means Starburst can't see the collection.

```sql
SELECT w.s AS schema_, w.t AS collection_, count(c.column_name) AS columns_
FROM   (VALUES
  ('ecmo_onebook', 'ecmo_orderbook_details'),
  ('ecmo_adapter_dealaxis_archival', 'deal'),
  ('ecmo_adapter_dealaxis_archival', 'syndicate'),
  ('ecmo_items', 'trade_ref'),
  ('ecmo_onebook', 'ecmo_orders'),
  ('ecmo_adapter_dealaxis_archival', 'pot_allocation'),
  ('ecmo_adapter_dealaxis_archival', 'pot_order'),
  ('ecmo_adapter_dealaxis_archival', 'pot_away_order'),
  ('ecmo_adapter_dealaxis_archival', 'pot_away_allocation'),
  ('ecmo_items', 'trade_book'),
  ('ecmo_items', 'trade_designations'),
  ('ecmo_items', 'under_writing_trade_book')) AS w (s, t)
LEFT JOIN ecm.information_schema.columns c
       ON c.table_schema = w.s AND c.table_name = w.t
GROUP  BY 1, 2
ORDER  BY 1, 2;
```

**If `pot_allocation` or `pot_order` shows 0:** MongoDB has them as
`pot_Allocation` / `pot_Order`, and Starburst lower-cases names. Set this on
the `ecm` catalog, restart it, and run the check again:

```
mongodb.case-insensitive-name-matching=true
```

## 4. Step 2 — the schema (every column of the 12)

This is the column list the datasets will publish. It's long: export to CSV and
drop it in `~/Desktop/ADK` so the dataset queries can be generated from it.

```sql
SELECT c.table_schema, c.table_name, c.ordinal_position, c.column_name, c.data_type
FROM   ecm.information_schema.columns c
WHERE  (c.table_schema, c.table_name) IN (VALUES
  ('ecmo_onebook', 'ecmo_orderbook_details'),
  ('ecmo_adapter_dealaxis_archival', 'deal'),
  ('ecmo_adapter_dealaxis_archival', 'syndicate'),
  ('ecmo_items', 'trade_ref'),
  ('ecmo_onebook', 'ecmo_orders'),
  ('ecmo_adapter_dealaxis_archival', 'pot_allocation'),
  ('ecmo_adapter_dealaxis_archival', 'pot_order'),
  ('ecmo_adapter_dealaxis_archival', 'pot_away_order'),
  ('ecmo_adapter_dealaxis_archival', 'pot_away_allocation'),
  ('ecmo_items', 'trade_book'),
  ('ecmo_items', 'trade_designations'),
  ('ecmo_items', 'under_writing_trade_book'))
ORDER  BY 1, 2, 3;
```

## 5. Step 3 — row counts (one collection per line)

```sql
SELECT 'ecmo_onebook.ecmo_orderbook_details' AS collection_, count(*) AS rows_ FROM ecm.ecmo_onebook.ecmo_orderbook_details;
SELECT 'ecmo_adapter_dealaxis_archival.deal' AS collection_, count(*) AS rows_ FROM ecm.ecmo_adapter_dealaxis_archival.deal;
SELECT 'ecmo_adapter_dealaxis_archival.syndicate' AS collection_, count(*) AS rows_ FROM ecm.ecmo_adapter_dealaxis_archival.syndicate;
SELECT 'ecmo_items.trade_ref' AS collection_, count(*) AS rows_ FROM ecm.ecmo_items.trade_ref;
SELECT 'ecmo_onebook.ecmo_orders' AS collection_, count(*) AS rows_ FROM ecm.ecmo_onebook.ecmo_orders;
SELECT 'ecmo_adapter_dealaxis_archival.pot_allocation' AS collection_, count(*) AS rows_ FROM ecm.ecmo_adapter_dealaxis_archival.pot_allocation;
SELECT 'ecmo_adapter_dealaxis_archival.pot_order' AS collection_, count(*) AS rows_ FROM ecm.ecmo_adapter_dealaxis_archival.pot_order;
SELECT 'ecmo_adapter_dealaxis_archival.pot_away_order' AS collection_, count(*) AS rows_ FROM ecm.ecmo_adapter_dealaxis_archival.pot_away_order;
SELECT 'ecmo_adapter_dealaxis_archival.pot_away_allocation' AS collection_, count(*) AS rows_ FROM ecm.ecmo_adapter_dealaxis_archival.pot_away_allocation;
SELECT 'ecmo_items.trade_book' AS collection_, count(*) AS rows_ FROM ecm.ecmo_items.trade_book;
SELECT 'ecmo_items.trade_designations' AS collection_, count(*) AS rows_ FROM ecm.ecmo_items.trade_designations;
SELECT 'ecmo_items.under_writing_trade_book' AS collection_, count(*) AS rows_ FROM ecm.ecmo_items.under_writing_trade_book;
```

## 6. Step 4 — create each dataset

For every row in section 1, in the "Create data product" screen:

1. **Catalog:** `bds_iceberg_ref` · **Schema:** the product name from section 1.
2. **Published dataset name:** the `ds_` name.
3. **Query:** an explicit column list from the collection, nested columns kept
   as they are (same shape as the existing `ds_ecm_orders`):

```sql
SELECT
  <column_1>
, <column_2>
, ...
FROM "ecm"."<schema>"."<collection>"
```

   The ready-to-paste query for each dataset will be generated into this folder
   from the Step 2 export (`ds_<name>.sql`, one file per dataset).
4. Click **Show columns**, then **Publish**.
5. Attach the AD groups from section 2.

## 7. Open points

- **"Extract schema from latest code":** the schema above is what Starburst reads
  from MongoDB. If the ticket means the ECMO application's code, ask the ECMO
  developers to check the Step 2 list against it.
- **`ds_ecm_orders` already exists:** check its 12 columns are still the full set
  before publishing the other orders datasets.
