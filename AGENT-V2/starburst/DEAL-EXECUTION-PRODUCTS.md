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
| `dp_deal_execution_ecm_deal_tranche` | `ds_ecmo_orderbook_details`, `ds_deal`, `ds_syndicate`, `ds_trade_refdata` | `ecmo_onebook.ecmo_orderbook_details`, `ecmo_adapter_dealaxis_archival.deal`, `ecmo_adapter_dealaxis_archival.syndicate`, `ecmo_items.trade_refdata` (ticket says trade_ref) |
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
  ('ecmo_items', 'trade_refdata'),
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

**Result (DEV, 2026-11-26):** 11 of 12 resolve: deal 9 columns,
syndicate 10, the four pot_* 10 each (the capital-letter names resolve, so no
catalog change is needed), trade_book 13, trade_designations 40,
under_writing_trade_book 28, ecmo_orderbook_details 5, ecmo_orders 27.
**`ecmo_items.trade_ref` = 0:** Starburst can't see it. It's spelled
differently, it's empty (the MongoDB connector reads a collection's columns
from its documents, so an empty collection has none), or it's not readable.

### Step 1b — trade_ref is `trade_refdata`

**Result (2026-11-26):** `ecmo_items` holds all_trades_view, dataglobe_ack,
dataglobe_publish, db_sequence, investor_trades_view, trade_book,
trade_designations, **trade_refdata**, under_writing_trade_book and
underwriting_trades_view. The ticket's `trade_ref` is `trade_refdata`.

`ds_trade_refdata.sql` uses `SELECT *` for now: "Show columns" expands it, and the
publish works. To publish an explicit list like the others, run this and send
the result:

```sql
SELECT ordinal_position, column_name, data_type
FROM   ecm.information_schema.columns
WHERE  table_schema = 'ecmo_items' AND table_name = 'trade_refdata'
ORDER  BY 1;
```

**Note:** `ecmo_orders` now has 27 columns, but the existing `ds_ecm_orders`
publishes 12. Decide with the Deal Execution team whether to add the other 15.

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
  ('ecmo_items', 'trade_refdata'),
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
SELECT 'ecmo_items.trade_refdata' AS collection_, count(*) AS rows_ FROM ecm.ecmo_items.trade_refdata;
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

   **Ready-to-paste queries are in this folder, one file per dataset** (generated
   2026-11-26 from the Step 2 column list; every top-level column, in source order):

   | Product | Dataset | File | Columns |
   |---|---|---|---|
   | deal_tranche | `ds_ecmo_orderbook_details` | `ds_ecmo_orderbook_details.sql` | 5 |
   | deal_tranche | `ds_deal` | `ds_deal.sql` | 9 |
   | deal_tranche | `ds_syndicate` | `ds_syndicate.sql` | 10 |
   | deal_tranche | `ds_trade_refdata` | `ds_trade_refdata.sql` (source is `trade_refdata`; `SELECT *` until its columns are listed, see Step 1b) | ? |
   | orders | `ds_ecm_orders` | `ds_ecm_orders_full.sql` (all 27; publish only if the team wants the full set, see note) | 27 |
   | orders | `ds_pot_allocation` | `ds_pot_allocation.sql` | 10 |
   | orders | `ds_pot_order` | `ds_pot_order.sql` | 10 |
   | orders | `ds_pot_away_order` | `ds_pot_away_order.sql` | 10 |
   | orders | `ds_pot_away_allocation` | `ds_pot_away_allocation.sql` | 10 |
   | trades | `ds_trade_book` | `ds_trade_book.sql` | 13 |
   | trades | `ds_trade_designations` | `ds_trade_designations.sql` | 40 |
   | trades | `ds_under_writing_trade_book` | `ds_under_writing_trade_book.sql` | 28 |

   Column names are in double quotes because `_id` and `_class` start with an
   underscore.

4. Click **Show columns**, then **Publish**.
5. Attach the AD groups from section 2.

## 7. Open points

- **`sourcexml` and `_class`:** `sourcexml` is the raw XML message each record was
  built from (large), and `_class` is the application's internal type marker.
  Both are included so the published schema matches the collection. Delete those
  two lines from a file if the team doesn't want them published.
- **`data` columns:** in the dealaxis and trade_book collections, the real fields
  sit inside one nested `data` record (the deal record alone has about 200
  fields). They're published as one nested column, like `investordetails` in
  `ds_ecm_orders`. Users read a field as `data.issname`. Flattening it into
  separate columns is a later decision for the team.
- **`ecmo_orderbook_details` has no `_id`:** it has 5 columns, none of them a key;
  `externaldealcode` is the only identifier.
- **"Extract schema from latest code":** the schema above is what Starburst reads
  from MongoDB. If the ticket means the ECMO application's code, ask the ECMO
  developers to check the Step 2 list against it.
- **`ds_ecm_orders` already exists:** check its 12 columns are still the full set
  before publishing the other orders datasets.
