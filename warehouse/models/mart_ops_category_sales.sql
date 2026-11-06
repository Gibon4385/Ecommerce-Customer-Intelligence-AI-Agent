WITH sales AS (
  SELECT DATE_TRUNC('week', CAST(o.order_date AS DATE))::DATE AS week_start,
         p.category, o.order_id, i.quantity, i.item_total
  FROM stg_orders o
  JOIN stg_order_items i USING (order_id)
  JOIN stg_products p USING (product_id)
  WHERE o.order_status = 'completed'
),
weekly AS (
  SELECT week_start, category, ROUND(SUM(item_total),2) AS revenue,
         CAST(SUM(quantity) AS BIGINT) AS units,
         COUNT(DISTINCT order_id) AS orders
  FROM sales GROUP BY week_start, category
),
enriched AS (
  SELECT *, SUM(revenue) OVER (PARTITION BY week_start) AS week_revenue,
         LAG(revenue) OVER (PARTITION BY category ORDER BY week_start) AS prior_revenue
  FROM weekly
)
SELECT week_start, category, revenue, units, orders,
       CAST(NULL AS DECIMAL(18,2)) AS gross_profit,
       ROUND((revenue-prior_revenue)*100.0/NULLIF(prior_revenue,0),4) AS revenue_wow_pct,
       ROUND(revenue/NULLIF(week_revenue,0),6) AS share_of_total_revenue,
       ROUND(revenue/NULLIF(units,0),2) AS avg_selling_price
FROM enriched ORDER BY week_start, category;

