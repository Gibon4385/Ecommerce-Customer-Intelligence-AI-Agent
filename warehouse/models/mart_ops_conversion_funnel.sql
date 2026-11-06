WITH event_base AS (
  SELECT CAST(e.event_timestamp AS DATE) AS date,
         p.category, e.user_id, e.event_type
  FROM stg_events e JOIN stg_products p USING (product_id)
  WHERE e.event_type IN ('view', 'cart', 'purchase')
),
expanded AS (
  SELECT date, category, user_id, event_type FROM event_base
  UNION ALL
  SELECT date, 'ALL', user_id, event_type FROM event_base
),
counts AS (
  SELECT date, category,
    COUNT(DISTINCT CASE WHEN event_type='view' THEN user_id END) AS view_users,
    COUNT(DISTINCT CASE WHEN event_type='cart' THEN user_id END) AS cart_users,
    COUNT(DISTINCT CASE WHEN event_type='purchase' THEN user_id END) AS purchase_users
  FROM expanded GROUP BY date, category
)
SELECT date, category, view_users, cart_users, purchase_users,
  ROUND(cart_users::DOUBLE / NULLIF(view_users,0), 6) AS view_to_cart_rate,
  ROUND(purchase_users::DOUBLE / NULLIF(cart_users,0), 6) AS cart_to_purchase_rate,
  ROUND(purchase_users::DOUBLE / NULLIF(view_users,0), 6) AS overall_conversion_rate,
  ROUND(1 - purchase_users::DOUBLE / NULLIF(cart_users,0), 6) AS cart_abandon_rate
FROM counts ORDER BY date, category;

