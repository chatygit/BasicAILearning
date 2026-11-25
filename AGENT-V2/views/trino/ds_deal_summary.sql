WITH
et AS (
    SELECT * FROM (
        SELECT x.*,
               row_number() OVER (PARTITION BY x.ecm_transaction_id
                                  ORDER BY try_cast(x.dg_version AS bigint) DESC NULLS LAST, try_cast(x.dg_updated_ts AS timestamp(6)) DESC NULLS LAST) AS rn_
        FROM ecm_history_data_iceberg.ecm_data_iceberg.opus_ecm_transaction_hist x
        WHERE x.deal_transaction_id IS NOT NULL
    ) WHERE rn_ = 1
),
st AS (
    SELECT ecm_transaction_id,
           max(status_value) AS status_value,
           max(status_type)  AS status_type
    FROM (
        SELECT x.*,
               row_number() OVER (PARTITION BY x.ecm_transaction_id, x.status_type
                                  ORDER BY try_cast(x.dg_version AS bigint) DESC NULLS LAST, try_cast(x.dg_updated_ts AS timestamp(6)) DESC NULLS LAST) AS rn_
        FROM ecm_history_data_iceberg.ecm_data_iceberg.opus_ecm_transaction_status_hist x
    )
    WHERE rn_ = 1
      AND status_type = 'Execution_Status'
      AND status_value NOT IN ('Confidential', 'Withdrawn', 'Terminated')
    GROUP BY ecm_transaction_id
),
tt AS (
    SELECT * FROM (
        SELECT x.*,
               row_number() OVER (PARTITION BY x.ecm_transaction_id, x.ecm_transaction_tranche_id
                                  ORDER BY try_cast(x.dg_version AS bigint) DESC NULLS LAST, try_cast(x.dg_updated_ts AS timestamp(6)) DESC NULLS LAST) AS rn_
        FROM ecm_history_data_iceberg.ecm_data_iceberg.opus_ecm_transaction_tranche_hist x
    ) WHERE rn_ = 1
),
dc AS (
    SELECT * FROM (
        SELECT x.*,
               row_number() OVER (PARTITION BY x.ecm_transaction_id, x.ecm_transaction_tranche_id, x.currency_id
                                  ORDER BY try_cast(x.dg_version AS bigint) DESC NULLS LAST, try_cast(x.dg_updated_ts AS timestamp(6)) DESC NULLS LAST) AS rn_
        FROM ecm_history_data_iceberg.ecm_data_iceberg.opus_ecm_transaction_tranche_demand_currency_hist x
    ) WHERE rn_ = 1
),
o AS (
    SELECT * FROM (
        SELECT x.*,
               row_number() OVER (PARTITION BY x.order_id
                                  ORDER BY try_cast(x.dg_version AS bigint) DESC NULLS LAST, try_cast(x.dg_updated_ts AS timestamp(6)) DESC NULLS LAST) AS rn_
        FROM ecm_history_data_iceberg.ecm_data_iceberg.ob_ecm_order_hist x
    ) WHERE rn_ = 1
),
iq AS (
    SELECT order_id, max(try_cast(ioi_qty AS decimal(38,4))) AS ioi_qty
    FROM (
        SELECT x.*,
               rank() OVER (PARTITION BY x.order_id ORDER BY try_cast(x.dg_version AS bigint) DESC NULLS LAST) AS rk_
        FROM ecm_history_data_iceberg.ecm_data_iceberg.ob_ecm_order_ioi_hist x
    )
    WHERE rk_ = 1
    GROUP BY order_id
),
tr AS (
    SELECT et.deal_transaction_id,
           count(DISTINCT CAST(tt.ecm_transaction_id AS varchar) || '~' ||
                          CAST(tt.ecm_transaction_tranche_id AS varchar)) AS tranche_count,
           min(try_cast(tt.pricing_ts AS timestamp(6))) AS first_priced,
           max(try_cast(tt.pricing_ts AS timestamp(6))) AS last_priced
    FROM tt
    JOIN et ON et.ecm_transaction_id = tt.ecm_transaction_id
    GROUP BY et.deal_transaction_id
),
tc AS (
    SELECT c.deal_transaction_id,
           listagg(c.tranche_currency, ' | ' ON OVERFLOW TRUNCATE '...' WITH COUNT)
             WITHIN GROUP (ORDER BY c.first_priced_ts ASC NULLS LAST, c.tranche_currency) AS currencies
    FROM (
        SELECT et.deal_transaction_id,
               coalesce(tdc.currency_name, gc.currency_name, CAST(tt.tranche_currency_id AS varchar)) AS tranche_currency,
               min(try_cast(tt.pricing_ts AS timestamp(6))) AS first_priced_ts
        FROM tt
        JOIN et ON et.ecm_transaction_id = tt.ecm_transaction_id
        LEFT JOIN dc tdc
          ON tdc.ecm_transaction_id = tt.ecm_transaction_id
         AND tdc.ecm_transaction_tranche_id = tt.ecm_transaction_tranche_id
         AND tdc.currency_id = tt.tranche_currency_id
        LEFT JOIN (SELECT currency_id, max(currency_name) AS currency_name FROM dc GROUP BY currency_id) gc
          ON gc.currency_id = tt.tranche_currency_id
        GROUP BY et.deal_transaction_id,
                 coalesce(tdc.currency_name, gc.currency_name, CAST(tt.tranche_currency_id AS varchar))
    ) c
    GROUP BY c.deal_transaction_id
),
od AS (
    SELECT CAST(o.deal_id AS varchar) AS deal_id,
           count(DISTINCT o.order_id) AS order_count,
           count(DISTINCT o.investor_gpnum) AS investor_count,
           sum(coalesce(try_cast(o.demand_qty AS decimal(38,4)),
                        CASE WHEN o.ioi_unit IN ('SHARES', 'BOND') THEN iq.ioi_qty END,
                        CAST(0 AS decimal(38,4)))) AS total_demand,
           sum(coalesce(try_cast(o.private_alloc AS decimal(38,4)), CAST(0 AS decimal(38,4)))) AS total_allocation
    FROM o
    LEFT JOIN iq ON iq.order_id = o.order_id
    WHERE o.order_status NOT IN ('CANCELLED', 'DELETED', 'PASS')
      AND ((CAST(o.is_matched AS varchar) = 'true' AND CAST(o.is_dominant AS varchar) = 'true')
           OR CAST(o.is_matched AS varchar) = 'false')
    GROUP BY CAST(o.deal_id AS varchar)
)
SELECT
    'ECM' AS product,
    CAST(t.deal_transaction_id AS varchar) AS deal_id,
    max(t.syndicate_deal_name) AS deal_name,
    max(try_cast(t.deal_size AS decimal(38,4))) AS deal_size,
    max(t.issuer_name_from_source) AS issuer_name,
    max(t.issuer_gfcid) AS gfcid,
    max(t.issuer_ticker) AS ticker,
    max(t.issuer_industry_sector) AS sector,
    max(t.use_of_proceeds) AS use_of_proceeds,
    max(t.product_equity_type_value) AS equity_type,
    max(t.product_offering_type_value) AS offering_type,
    max(s.status_value) AS deal_status,
    max(s.status_type) AS execution_status,
    CAST(NULL AS varchar) AS deal_region,
    max(try_cast(t.settlement_ts AS timestamp(6))) AS settlement_ts,
    max(t.settlement_currency_name) AS settlement_currency,
    CAST(max(tr.tranche_count) AS decimal(38,0)) AS tranche_count,
    CAST(max(tr.first_priced) AS timestamp(6)) AS first_priced,
    CAST(max(tr.last_priced) AS timestamp(6)) AS last_priced,
    max(tc.currencies) AS currencies,
    CAST(max(od.order_count) AS decimal(38,0)) AS order_count,
    CAST(max(od.investor_count) AS decimal(38,0)) AS investor_count,
    CAST(t.deal_transaction_id AS varchar) AS transaction_id,
    max(t.issuer_leid) AS issuer_lei,
    CAST(max(od.total_demand) AS decimal(38,4)) AS total_demand,
    CAST(max(od.total_allocation) AS decimal(38,4)) AS total_allocation,
    CAST(CASE WHEN max(try_cast(t.deal_size AS decimal(38,4))) > 0
              THEN round(max(od.total_demand) / max(try_cast(t.deal_size AS decimal(38,4))), 2)
         END AS decimal(38,6)) AS subscription_ratio,
    CAST(NULL AS decimal(38,6)) AS deal_fee_mm,
    CAST(NULL AS varchar) AS deal_fee_currency,
    CAST(NULL AS decimal(38,6)) AS deal_size_mm,
    CAST(NULL AS varchar) AS deal_size_currency,
    max(try_cast(t.announce_ts AS timestamp(6))) AS first_announced,
    max(try_cast(t.base_price AS decimal(38,6))) AS base_price,
    max(try_cast(t.reoffer_low_price AS decimal(38,6))) AS reoffer_low_price,
    max(try_cast(t.reoffer_high_price AS decimal(38,6))) AS reoffer_high_price,
    max(try_cast(t.fx_rate AS decimal(38,9))) AS fx_rate,
    max(t.issuer_country_name) AS issuer_country,
    max(t.issuer_domicile_country_name) AS issuer_domicile,
    max(t.offering_format) AS offering_format,
    max(t.product_equity_class_value) AS deal_class,
    CAST(NULL AS varchar) AS dcm_deal_class,
    max(CASE WHEN upper(t.product_equity_type_value) IN ('CONVERTIBLE BONDS', 'CONVERTIBLE PREFERRED', 'EXCHANGABLE NOTES', 'EXCHANGEABLE NOTES')
               OR (upper(t.product_equity_type_value) = 'EQUITY' AND upper(t.product_offering_type_value) LIKE 'CONVERTIBLE%')
             THEN 'bonds' ELSE 'shares' END) AS size_unit,
    CAST(NULL AS varchar) AS country_of_risk
FROM et t
JOIN st s ON s.ecm_transaction_id = t.ecm_transaction_id
LEFT JOIN tr ON tr.deal_transaction_id = t.deal_transaction_id
LEFT JOIN tc ON tc.deal_transaction_id = t.deal_transaction_id
LEFT JOIN od ON od.deal_id = CAST(t.deal_transaction_id AS varchar)
GROUP BY t.deal_transaction_id
