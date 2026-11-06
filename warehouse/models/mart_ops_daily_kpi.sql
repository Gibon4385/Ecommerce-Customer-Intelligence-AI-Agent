WITH completed_orders AS (
    SELECT order_id, user_id, CAST(order_date AS DATE) AS order_date, total_amount
    FROM stg_orders
    WHERE order_status = 'completed'
),
first_orders AS (
    SELECT user_id, MIN(order_date) AS first_order_date
    FROM completed_orders GROUP BY user_id
),
item_daily AS (
    SELECT CAST(o.order_date AS DATE) AS date, SUM(i.quantity) AS units
    FROM stg_orders o JOIN stg_order_items i USING (order_id)
    WHERE o.order_status = 'completed' GROUP BY 1
),
daily AS (
    SELECT o.order_date AS date,
           ROUND(SUM(o.total_amount), 2) AS revenue,
           CAST(NULL AS DECIMAL(18,2)) AS gross_profit,
           COUNT(DISTINCT o.order_id) AS orders,
           CAST(COALESCE(MAX(i.units), 0) AS BIGINT) AS units,
           ROUND(SUM(o.total_amount) / COUNT(DISTINCT o.order_id), 2) AS aov,
           COUNT(DISTINCT o.user_id) AS active_customers,
           COUNT(DISTINCT CASE WHEN f.first_order_date = o.order_date THEN o.user_id END) AS new_customers,
           COUNT(DISTINCT CASE WHEN f.first_order_date < o.order_date THEN o.user_id END) AS returning_customers
    FROM completed_orders o
    JOIN first_orders f USING (user_id)
    LEFT JOIN item_daily i ON i.date = o.order_date
    GROUP BY o.order_date
),
compared AS (
    SELECT *,
      ROUND(new_customers::DOUBLE / NULLIF(active_customers, 0), 6) AS new_customer_ratio,
      ROUND((revenue - LAG(revenue, 7) OVER (ORDER BY date)) * 100.0 /
            NULLIF(LAG(revenue, 7) OVER (ORDER BY date), 0), 4) AS revenue_wow_pct,
      ROUND((orders - LAG(orders, 7) OVER (ORDER BY date)) * 100.0 /
            NULLIF(LAG(orders, 7) OVER (ORDER BY date), 0), 4) AS orders_wow_pct,
      AVG(revenue) OVER (PARTITION BY EXTRACT(ISODOW FROM date) ORDER BY date
                         ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING) AS weekday_avg,
      STDDEV_SAMP(revenue) OVER (PARTITION BY EXTRACT(ISODOW FROM date) ORDER BY date
                                 ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING) AS weekday_stddev
    FROM daily
)
SELECT date, revenue, gross_profit, orders, units, aov, active_customers,
       new_customers, returning_customers, new_customer_ratio,
       revenue_wow_pct, orders_wow_pct,
       COALESCE(ABS(revenue - weekday_avg) > 2 * weekday_stddev, FALSE) AS is_anomaly,
       CASE WHEN ABS(revenue - weekday_avg) > 2 * weekday_stddev
            THEN 'Revenue differs from the prior four same-weekday observations by over 2 SD'
            ELSE NULL END AS anomaly_reason
FROM compared ORDER BY date;

