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
