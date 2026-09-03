# Request to BDS/Starburst team — Oracle NUMBER mapping on `bds_dg_oraas`

## Ask
Raise the Oracle NUMBER default scale on the `bds_dg_oraas` catalog:

```
oracle.number.default-scale = 9      (currently effectively 0 — confirmed:
                                      DESCRIBE shows order_amount as decimal(38,0))
oracle.number.rounding-mode = HALF_UP
```

CONFIRMED MECHANISM (2026-09-03): with the current scale-0 mapping, whole-number
values read fine, but 1,051 of the failing query's 35,034 rows carry fractional
values → JDBC "Rounding necessary" on read. Note: rounding-mode ALONE (keeping
scale 0) is NOT acceptable — it would silently truncate every fractional value,
and fee columns (values like 0.0125) would collapse to 0.

If the connector exposes `number_default_scale` as a catalog SESSION property,
tell us — the MCP server could then set it per-session and no catalog-wide
change is needed.

## Why
The DGSTREAM `VW_*` views define their numeric columns as expressions
(NVL/SUM/ROUND/CASE), so Oracle publishes them as **unconstrained NUMBER — null
precision, null scale** (verified via ALL_TAB_COLUMNS on VW_ORDER_DETAIL:
ORDER_AMOUNT, ORDER_DEMAND_QTY, ORDER_ALLOCATION, DEAL_SIZE, TRANCHE_SIZE,
ACTIVE_PRICE all NUMBER/null/null). Without a default scale, the connector
cannot map these columns natively; production-path queries fail with Trino JDBC
**"Rounding necessary"** (and/or varchar fallback), observed 2026-09-02/03 on
`SELECT ... SUM(order_amount) ... FROM vw_order_detail WHERE currency='USD' ...`
— the query returns empty/errors while the same SQL run directly in Oracle
returns 35,034 rows / 3,501 investors.

## Why default-scale=9 is lossless here
The views bound every money value at source: amounts ROUND(...,4), fees
ROUND(...,6) (deployed 2026-09-03; verified 0 rows exceed 4dp in the failing
query's window). All values fit DECIMAL(38,9) exactly — the mapping cannot lose
or round anything real. HALF_UP is belt-and-braces for any future stray value.

## Scope / risk
Property affects only how unconstrained Oracle NUMBER columns MAP in Trino for
this catalog; constrained columns (declared precision/scale) are untouched.
No view, schema, or data changes involved. One catalog-wide effect to review:
every unconstrained NUMBER column shifts decimal(38,0) → decimal(38,9), which
reduces max integer digits from 38 to 29 — our largest observed values are
~14 digits, and any other catalog consumers should confirm the same headroom.

## PROD note (do not skip)
All measurements above are DEV/UAT data. Two things carry to PROD structurally,
two do not:
- CARRIES: the null-precision metadata (same view DDL) and the ROUND value
  bounds (they live IN the views, so any environment running the current view
  release is bounded the same way).
- DOES NOT CARRY: the specific counts (0 rows >4dp, fractional counts). At PROD
  promote time: (1) request the SAME two properties on the PROD catalog —
  this ask covers UAT's catalog only; (2) PROD must be running the ROUND-bounded
  view release BEFORE relying on the lossless argument; (3) re-run the scale
  probes (views/_checks/_scale-probes-2026-09-02.sql) against PROD as a fresh
  census, never assuming DEV numbers.

## Verification after the change
`DESCRIBE bds_dg_oraas.dgstream.vw_order_detail` should show order_amount as
decimal(38,9); then the failing banker query ("top 10 investors by order size,
USD, last 12 months") returns a populated top-10.
