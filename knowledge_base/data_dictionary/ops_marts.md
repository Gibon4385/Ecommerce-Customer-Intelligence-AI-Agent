# Operational Marts Data Dictionary

## `mart_ops_daily_kpi`

粒度為 `date`。所有營收、訂單、單位與客戶指標只計 `completed` 訂單。`aov` 為
revenue / orders；new customer 以首次 completed order 日期判定。WoW 比較資料中的前 7 筆
日期；異常使用前四個相同星期幾觀察值的平均與樣本標準差。來源沒有成本，`gross_profit`
固定為 NULL。

欄位：`date` (date, PK)、`revenue`/`aov` (decimal)、`gross_profit` (nullable decimal)、
`orders`/`units`/`active_customers`/`new_customers`/`returning_customers` (integer)、
`new_customer_ratio`/`revenue_wow_pct`/`orders_wow_pct` (float)、`is_anomaly` (boolean)、
`anomaly_reason` (nullable string)。

## `mart_ops_conversion_funnel`

粒度為 `date + category`，另有 `ALL`。以 events 的 `view`、`cart`、`purchase` 計算 distinct
users。沒有 checkout event；purchase event 不等同 completed order。分母為 0 時 rate 為 NULL，
不補 0。

欄位：`date + category` (PK)、三個 distinct-user count (integer)、四個 rate (nullable float)。

## `mart_ops_category_sales`

粒度為 ISO week Monday + category。只計 completed orders；revenue 使用 item_total，units 使用
quantity，ASP 為 revenue / units。來源沒有成本，`gross_profit` 固定為 NULL。

欄位：`week_start + category` (PK)、`revenue`/`avg_selling_price` (decimal)、
`units`/`orders` (integer)、`gross_profit` (nullable decimal)、`revenue_wow_pct`
(nullable float)、`share_of_total_revenue` (float)。

## Synthetic marts

- `mart_ops_campaign_performance`: 固定 seed `20261105`，segment 取自實際資料。
- `mart_ops_customer_touch_log`: user_id 與 campaign_id 都有真實/模擬來源外鍵。
- `mart_ops_pipeline_status`: row_count 由 canonical Mart 實際檔案計算。

Campaign 欄位涵蓋識別、類型、日期、segment、offer、漏斗 counts、revenue/cost 與 rates/ROAS；
PK 是 `campaign_id + target_segment`。Touch log 的 PK 是 `touch_id`，`user_id` 為敏感識別碼。
Pipeline status 的 PK 是 `model_name + run_date`，其 timestamp 為帶 timezone 的 ISO-8601。

