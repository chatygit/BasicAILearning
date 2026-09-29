# Capital Markets data on Iceberg — the plan (2026-09-21, for the 22-Sep meeting)

## The one-line proposal
Move the DGSTREAM feed tables and our nine agent objects from Oracle-behind-Trino
onto a Starburst-native Iceberg catalog, keep every column contract the agent
already speaks, and let the first ask in a conversation take seconds instead
of half a minute to seven minutes.

## Why now (measured, UAT, 2026-09-18 K series)
| Ask shape | Today (Oracle via bds_dg_oraas) | Why it is slow |
|---|---|---|
| DCM deal count, no demand columns (K2) | 28.7 s | party-master windows + LISTAGGs recomputed per query |
| DCM total demand (K3) | 29.0 s | 5.0M-row order book deduped per query |
| entity search full pass (K4) | 146.7 s | two books recomputed per name resolution |
| investor-name-scoped orders, 6 months (K6) | 17.0 s | filter is not a PARTITION BY key → full window |
| unscoped order aggregate (K7) | 25.1 s | inherent scan of 5.0M rows, over the federation link |
| worst observed (deal_count, 2026-09-02) | 401 s + 37 s probes | HAVING on a computed expression: nothing pushes down |
| deal-scoped orders, literal id (K1b) | 0.6 s | the only shape where a predicate reaches the window |

Everything above is `execute=` time. Our Python is 0.00 s. Three structural
causes, none fixable from our side of the Oracle link: (1) the views dedupe and
aggregate the SAME rows on every query, (2) the Oracle connector pushes down only
simple predicates, so anything computed pulls the matched set across the
federation link, (3) stats and indexes belong to another team and are stale.

## Design in one picture
```
DataGlobe feed ──► RAW (Iceberg, append-only mirrors of DGSTREAM tables)
                        │  incremental by SOURCE_PUBLISHED_TS / DG_VERSION
                        ▼
                   CORE (Iceberg, deduped current state: deal, tranche, order,
                        │  trade, hedge, designation, party, issue)
                        │  the ROW_NUMBER windows run ONCE per load, not per query
                        ▼
                   SERVE (Iceberg, the nine agent objects AS TABLES —
                        │  same columns, same types, same names as today's views)
                        ▼
              BQS engine ──► agent   (base_view: nine one-line changes, nothing else)
```

Three schemas in ONE Iceberg catalog (`cm_raw`, `cm_core`, `cm_serve`), not three
catalogs: cross-schema grants are simpler than cross-catalog ones, the MCP's
`source` resolution stays one string, and the agent's Trino role is granted
`cm_serve` only. Object storage under the catalog is whatever the Starburst
platform already provisions (S3-compatible / ADLS / HDFS) — we do not pick it.

## What the agent sees (the contract we protect)
- `base_view` in nine ontology yamls: `bds_dg_oraas.dgstream.vw_deal_summary`
  → `cm_iceberg.cm_serve.deal_summary` (and the eight others). No field, type,
  product, or example changes. `tests/test_catalog_view_contract.py` and the
  golden-SQL corpus keep this honest: the SERVE tables are built from the same
  branch SQL that the views hold today, so the alias lists match position for
  position.
- The dialect is already Trino (`app/bqs/dialects/trino.py`); Iceberg is a
  native Trino connector, so every generated statement (LIKE, IN-lists,
  partition_by, having, offset paging) runs unchanged.
- One new thing the agent gains: a "data as of" timestamp. Each load writes
  `cm_serve._load_meta (object, loaded_at, source_watermark, row_count)`;
  `fetch_as_of_date` in `app/bqs/executor.py` is explicitly unwired for Trino
  today ("the agent has no data-as-of date to show") — wiring it to this table
  is a 20-line change and closes a standing disclosure gap.
- Entitlement stays exactly as it is: product scope is an injected `product`
  filter in the SQL; Starburst role grants on `cm_serve` add a second wall.

## Physical layout, chosen for our query shapes
| Object | Partition | Sort within files | Why |
|---|---|---|---|
| deal_summary | product, year(pricing_ts) | deal_id | product filter on every query; year windows are the banker's default |
| tranche_summary | product, year(pricing_ts) | deal_id, tranche_id | deal card → its tranches |
| order_detail | product, year(pricing_ts) | deal_id, investor_gp_id | deal-scoped books (K1b shape) and investor-scoped asks (K6 shape) both become file skips |
| trade_detail, hedge_* | product, year(trade_ts) | deal_id | deal-scoped trades (K5) |
| entity_search | none (tens of thousands of rows) | entity_name | one small file set, sub-second contains-match |
| designation, trade_syndicate | product | deal_id | the moving surface; small |

Also: 128–512 MB target files with scheduled `OPTIMIZE` + `expire_snapshots`;
Iceberg column statistics (NDV / min-max) so the Trino cost-based optimizer picks
join orders — the thing Oracle's stale stats never gave us; Parquet with
dictionary encoding on status / category / currency columns.

Size check: 5.0M orders + 4.8M size rows + 0.7M Ipreo orders + the deal, tranche,
trade and hedge books ≈ 12M rows — about 2 GB as Parquet. Small enough that
`cm_serve` is rebuilt in full every load in Phase 0; incremental MERGE comes in
Phase 1 only where it earns its complexity.

## Speed: expected, not yet measured
| Ask shape | Today | On Iceberg (expected) | Mechanism |
|---|---|---|---|
| deal count / deal list (K2) | 28.7 s | < 1 s | pre-computed table, partition prune on product |
| total demand (K3, K7) | 25–29 s | 1–3 s | column scan of ~5M rows, no dedupe window |
| entity search (K4) | 146.7 s | < 0.5 s | materialized once per load |
| investor-scoped orders (K6) | 17.0 s | < 1 s | sort-order skip on investor_gp_id |
| the 401 s HAVING case | 401 s | 1–3 s | HAVING runs inside Trino on local files |
| MCP round trip floor | ~1–2 s | ~1–2 s | unchanged (transport + CyberArk cache hit + entitlement cache) |

The honest floor: a banker question is still ~5 model turns on Gemini 2.5 Pro
(~10 s irreducible on the model side; see ecm-dcm-v2-latency). Iceberg removes
the DB share, which today is 60–95 % of wall-clock on anything but a deal card.

## Caching: four layers, each doing one job
1. **Starburst file cache (Warp Speed / caching file system)** — hot Parquet
   files pinned on worker SSD; zero code, a catalog property. Covers the
   "second banker, same year" case.
2. **Starburst materialized views with `GRACE PERIOD`** — an option for
   `cm_serve` instead of plain tables: Starburst refreshes them on schedule and
   answers from the stored result inside the grace window. Choose this only if
   the platform team prefers Starburst-owned scheduling over our load job
   (decision 5 below).
3. **MCP result cache** (`_review/cache-design.md`, designed, release-train) —
   SHA-256 of (source, sql, params) → rows, TTL tiers by object, entity snapshot
   in process. Turns every repeat and drill-down into ~0 s. Its 1-hour TTLs were
   licensed by "no live deals"; with Iceberg, the load watermark becomes the
   invalidation key instead of a clock — near-perfect freshness, unlimited
   retention until the next load.
4. **Gemini context caching** (ASKS-external §1a) — the model side; unrelated to
   storage but it is the other half of the wall-clock.

## Freshness
Bankers never use the agent for live deals (user, 2026-09-02). Proposed SLA:
`cm_raw` and `cm_core` loaded hourly from the feed watermarks
(SOURCE_PUBLISHED_TS / DG_PROCESSED_TS / DG_VERSION exist on every DGSTREAM
table — the DG team must confirm they are monotonic per row); `cm_serve`
rebuilt after each core load; designations / closeouts on the same hour.
The `_load_meta` row makes the lag visible in every answer.

## Snapshots and time travel — two problems solved for free
- **Regression on a fixed dataset.** Tag a `cm_serve` snapshot (`uat_2026_09`)
  and point the QA prompt runs at it: the "UAT is a mess and keeps moving"
  problem disappears, and a K-series probe becomes reproducible.
- **A PROD-shaped UAT** (ASKS-external §5): a masked copy of a PROD snapshot is
  a branch of the same tables — the masking job runs once, the copy is bytes.

## Phases
| Phase | What | Exit test |
|---|---|---|
| 0 — prove it (1–2 weeks after approval) | `cm_serve` only: nightly `CREATE TABLE AS SELECT * FROM bds_dg_oraas.dgstream.vw_*` for the nine objects (Oracle pays the 400 s ONCE a night), `_load_meta`, the nine `base_view` lines, UAT agent pointed at it | K2/K3/K4/K6/K7 re-run on the tables; contract test + corpus green; QA-PROMPTS 15/3/20 answers byte-identical to the Oracle path (same day's data) |
| 1 — own the pipeline | `cm_raw` incremental by watermark; `cm_core` dedupe as Trino SQL (the view branches ported: LISTAGG → `listagg`, NVL → `coalesce`, TO_NUMBER … DEFAULT NULL → `try_cast`, NUMBER(38,4) → DECIMAL(38,4)); `cm_serve` built from core; Oracle views no longer in the path | parallel run for one week: per product / per year row counts and sums of the metric columns equal between Oracle views and cm_serve within the load lag; deploy-check ported to Trino |
| 2 — cut over | PROD `base_view` switch (an ontology change — rides the release train); Oracle views kept one release as fallback; result cache keyed on the load watermark | one release with no fallback use; PROD OCP log shows execute ≤ 3 s at p95 |
| 3 — what cheap compute unlocks | the backlog items blocked on "views are expensive": tranche pricing stages (IPT → guidance → launch), the ECM IOI curve grain, deal class, SIZE_UNIT, status exclusion, entity search as a table; snapshot-pinned regression; PROD-shaped UAT branch | each item lands as a core/serve SQL change with its own contract-test row, no Flyway, no per-view approval |

Phase 0 needs nothing from the DB team and no view rewrite. It is the whole
argument, and it is reversible with nine one-line edits.

## Bucket layout (added 2026-09-27 — DataGlobe now writes S3, not Oraas)
One bucket per environment, same layout in all three. Three Iceberg schemas map
to three prefixes; the metastore holds the mapping, queries use schema.table.

```
s3://<env>-capital-markets-iceberg/
  raw/        DataGlobe-owned. One Iceberg table per DG table, Oracle column
              names and types, DG metadata on every row (SOURCE_PUBLISHED_TS,
              DG_PROCESSED_TS, DG_VERSION, DG_EVENT_ID, DG_ENTITY_KEY).
              Append-only: every published version is a row. WE DO NOT WRITE HERE.
  core/       Ours. Deduped current state, one table per business grain per
              source family, built from raw by our load. The ROW_NUMBER windows
              and LISTAGGs of today's views run here, once per load.
  serve/      Ours. The nine agent objects as tables — today's view contracts,
              column for column. The ONLY schema the agent's role can read.
  ops/        Ours. load_meta (object, loaded_at, source watermark, row count),
              reconciliation results, the deploy-check as a table.
```

### raw — the 35 DG tables the nine views read (as DataGlobe lands them)
| Family | Tables | Grain / notes |
|---|---|---|
| OneBook orderbook `OB_*` (15) | OB_DEAL_TRANCHE, OB_DEAL_ISSUER, OB_TRANCHE, OB_TRANCHE_RATING, OB_TRANCHE_SYNDICATE_MEMBER, OB_ORDER, OB_ORDER_SIZE, OB_ECM_ORDER, OB_ECM_ORDER_IOI, OB_ORDER_TRADE, OB_ORDER_TRADE_SYNDICATE, OB_HEDGE_ORDER, OB_HEDGE_TRADE, OB_ECM_TRADE_BOOK_INVESTOR_TRADE, OB_ECM_TRADE_BOOK_DESIGNATION | DCM deals/tranches/orders/trades/hedges; ECM orderbook + trade book. OB_ORDER 5.0M / OB_ORDER_SIZE 4.8M rows are the two big ones |
| OPUS ECM `OPUS_ECM_*` (7) | OPUS_ECM_TRANSACTION, _STATUS, _TRANCHE, _TRANCHE_DEMAND_CURRENCY, _TRANCHE_SYNDICATE, _TRANCHE_PRODUCT_DETAIL, _TRANCHE_PRODUCT_DETAIL_IDENTIFIER | ECM system of record (deal/tranche masters) |
| Ipreo `IPREO_*` (13) | IPREO_OPUS_ECM_TRANSACTION, _STATUS, _TRANCHE, _TRANCHE_PRODUCT_DETAIL, _TRANCHE_SYNDICATE, IPREO_OB_ECM_ORDER, IPREO_OB_ECM_ORDER_IOI, IPREO_ISSUE, IPREO_TRANCHE, IPREO_ORDER, IPREO_ORDERIOI, IPREO_PRODUCT, IPREO_PRODUCTFEE | second ECM source, mirror + raw tables |
| NOT in our bucket (2) | OPUS_BASE_TRANSACTION, OPUS_BASE_TRANSACTION_RELATED_PARTIES | the origination team's bucket — read by the core load from their catalog, or dropped (previous section) |
| Coming | DealLogic (Mongo catalog) | a source for the core load, one more ECM/DCM branch |

Raw partitioning is DataGlobe's call; ask them for `day(DG_PROCESSED_TS)` so our
incremental core load reads one day of files, not the table.

### core — deduped current state (ours)
| Table | Built from | Dedupe key (today's window) | Partition |
|---|---|---|---|
| core.ecm_transaction | OPUS_ECM_TRANSACTION ∪ IPREO_OPUS_ECM_TRANSACTION (+ DealLogic later), with a `source_system` column | deal_transaction_id, ecm_transaction_id | source_system |
| core.ecm_transaction_status | both _STATUS tables | ecm_transaction_id (Execution_Status only) | source_system |
| core.ecm_tranche | both _TRANCHE tables + product detail + Ipreo raw tranche/product/fee | deal_transaction_id, tranche_id | source_system, year(pricing_ts) |
| core.ecm_tranche_syndicate | both _SYNDICATE tables, Citi label normalised | tranche_id, member | source_system |
| core.ecm_order | OB_ECM_ORDER + OB_ECM_ORDER_IOI ∪ IPREO_OB_ECM_ORDER + IOI + IPREO_ORDER (category/region/billed-by) | deal_id, tranche_id, order_id | source_system, year(pricing_ts) |
| core.dcm_deal_tranche | OB_DEAL_TRANCHE + OB_TRANCHE + ratings + syndicate members (the LISTAGGs) | deal_id, tranche_id | year(pricing_ts) |
| core.dcm_order | OB_ORDER + OB_ORDER_SIZE | root_id, parent_id, order_id | year(pricing_ts) |
| core.trade | OB_ORDER_TRADE, OB_ECM_TRADE_BOOK_INVESTOR_TRADE | product, trade_id | product, year(trade_ts) |
| core.hedge_order / core.hedge_trade | OB_HEDGE_ORDER / OB_HEDGE_TRADE | hedge id | year |
| core.designation / core.trade_syndicate | OB_ECM_TRADE_BOOK_DESIGNATION / OB_ORDER_TRADE_SYNDICATE | card id / (trade, dealer) | product |
| core.issuer | OB_DEAL_ISSUER (+ the party master from the other team's catalog if readable) | gfcid | — |
| core.currency_name | OPUS_ECM_TRANSACTION_TRANCHE_DEMAND_CURRENCY (global id→name) | currency_id | — |

`source_system` (OPUS / IPREO / DEALLOGIC) is a core column for lineage and
reconciliation; serve does not expose it — the agent sees one ECM, as agreed.

Normalise once, at load: core stores statuses canonicalised (one spelling per
value) and a `name_key` (upper-cased, trimmed) beside every name column, so
the view-era `UPPER(col)` predicates become plain equality on serve and the
file statistics prune on them. Case variants are a load-time problem, never
a query-time one.

### serve — the nine objects (ours; the agent's only read surface)
| Table | From core | Partition | Sort within files |
|---|---|---|---|
| serve.deal_summary | ecm_transaction + tranche + order roll-ups; dcm_deal_tranche + dcm_order roll-ups | product, year(last_priced) | deal_id |
| serve.tranche_summary | ecm_tranche + syndicate; dcm_deal_tranche | product, year(pricing_ts) | deal_id, tranche_id |
| serve.order_detail | ecm_order; dcm_order | product, year(pricing_ts) | deal_id, investor_gp_id |
| serve.trade_detail | trade | product, year(trade_ts) | deal_id |
| serve.hedge_order / serve.hedge_trade | hedge_* | product, year | deal_id |
| serve.designation / serve.trade_syndicate | designation / trade_syndicate | product | deal_id |
| serve.entity_search | deal_summary + order_detail (tens of thousands of rows) | none | entity_name |

Sizes: ≈12M rows across serve, ≈2 GB Parquet; a full rebuild per load is
minutes, so Phase 0/1 rebuild serve in full and only core is incremental.

### Load cadence and ownership
- DataGlobe: Kafka → raw, continuous (their sink, their SLA).
- Ours, hourly: `INSERT INTO core … SELECT … FROM raw WHERE DG_PROCESSED_TS >
  last watermark` per family, then `CREATE OR REPLACE TABLE serve.x AS SELECT …
  FROM core`, then one row into ops.load_meta and the reconciliation query.
- Snapshot expiry: 7 days on core/serve (time travel for regression pins),
  DataGlobe's rule on raw.

### Migration of the SQL we already have
The nine view files ARE the core+serve definitions, minus dialect: Oracle
`NVL`→`coalesce`, `LISTAGG … ON OVERFLOW`→`listagg` (Trino ≥ 0.4) or
`array_join(array_agg(...))`, `TO_NUMBER … DEFAULT NULL ON CONVERSION
ERROR`→`try_cast`, `NUMBER(38,4)`→`DECIMAL(38,4)`, `ROWID` tie-breaks→
`DG_VERSION DESC` (a better dedupe order than ROWID ever was), `REGEXP_LIKE`→
`regexp_like`, `FETCH FIRST`→`LIMIT`. The UNION ALL branches become the
`source_system` branches of the core loads. The contract test and golden corpus
run unchanged against serve because the column names and types are the same.

## Sources that live outside our bucket (added 2026-09-27)
The migration splits DGSTREAM by owning team. Two tables the ECM branches read
today will belong to the origination platform's team, not to us:
OPUS_BASE_TRANSACTION and OPUS_BASE_TRANSACTION_RELATED_PARTIES. They feed
exactly three things: ECM `deal_region` (and the tranche-region fallback), the
deal-grain `deal_fee_mm` / `deal_size_mm` pair with their currencies, and the
Primary-Client issuer overlay (name, GFCID, ticker) behind an NVL fallback.

Rule: a source outside our bucket is read the same way DealLogic-in-Mongo is —
by the core LOAD, as a scheduled INSERT from that team's catalog, never by a
join at question time. If their catalog is not readable by our load role, the
column is dropped (the removal wave is preserved in git 78b3c4c; issuer names
fall back to the orderbook issuer, deal region to `issuer_country`, deal fees
to the tranche fee columns). Decision per column, taken when the platform team
says which catalogs our role may read. DealLogic follows the identical path:
its Mongo catalog is a source, its rows become one more branch in core.

- **DealLogic fills a gap our own sources cannot (found 2026-09-29):** the Ipreo history (1990–2013, ~19,300 ECM deals) stores no IPO-versus-follow-on flag anywhere, and no column derives it. DealLogic carries the deal type on every ECM deal. The core-layer LOAD matches Ipreo issues to DealLogic on issuer and pricing date and writes `offering_type` (with `offering_type_source = 'deallogic'`) — never a join at question time. Needs read rights on the DealLogic catalog (asks upward).

## What does not change
BQS contract (one metric per request, ANDed filters, 40-id in-lists, partition_by,
having, offset paging) · the nine objects and every column in them · SKILL and
agents.yaml doctrine · the entitlement gate · the Ipreo branch just built (it
becomes core/serve SQL like every other branch) · Starburst as the query engine.

## Risks and how each is bounded
| Risk | Bound |
|---|---|
| Who owns the Iceberg catalog and its storage | decision 2; if BDS owns it, our schemas are a whitelist entry once, then tables are ours |
| Watermark columns not monotonic (late-arriving corrections) | Phase 0 rebuilds in full, so it does not depend on them; Phase 1 verifies with a one-week parallel run before trusting increments |
| Two copies of the data drift | `_load_meta` + the per-product / per-year reconciliation query runs after every load and posts to the OCP log |
| Type fidelity (Oracle NUMBER → DECIMAL) | every metric is already CAST NUMBER(38,4/6) in the views; the S3 SHOW COLUMNS check moves to `cm_serve` |
| Governance: is Iceberg-on-object-storage approved for this data class | decision 4; the data already leaves Oracle through Trino today, so the classification question is storage, not access |
| Cost | ~2 GB storage; compute is the same Starburst cluster; the load job is nine statements an hour |

## Decisions to take in the room
1. Approve Phase 0 in UAT (copy path, nine tables, nightly).
2. Catalog and storage owner (BDS / Starburst platform vs DataGlobe).
3. Freshness SLA: hourly core, hourly serve — yes or a different number.
4. Data-classification sign-off for Iceberg storage of DGSTREAM-derived tables.
5. Who runs the loads: our scheduled Trino SQL (Airflow / OCP cron) vs
   Starburst materialized views with GRACE PERIOD vs DataGlobe publishing to
   Iceberg directly (the DG_* columns suggest an event pipeline already exists).
6. Whether PROD cut-over (Phase 2) can ride the next release train after Phase 1's
   parallel week, or needs its own window.

## Open questions for the platform team (to send after the meeting)
- Is the Iceberg connector enabled on this Starburst cluster, and which metastore
  (Hive / Glue / Iceberg REST)? Is Warp Speed licensed?
- Can our Trino role `CREATE TABLE` in a schema of a shared catalog, or must each
  table be whitelisted like the Oracle views are?
- DataGlobe: are `SOURCE_PUBLISHED_TS` / `DG_PROCESSED_TS` / `DG_VERSION`
  monotonic per row, and is there a direct Iceberg or Kafka sink already?
- Scheduling: is there an approved scheduler for Trino SQL jobs on OCP?
