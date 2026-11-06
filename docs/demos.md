# Portfolio Demo Guide

三條流程全部使用 deterministic tools、DuckDB 與 mock adapter，不需要 LLM API，也不會呼叫真實
Email、Jira、Linear 或 Slack。

## 一鍵執行

```bash
uv run python -m scripts.run_portfolio_demos
```

輸出是一個 JSON summary，包含三條流程的 task status 與 mock external reference。重跑使用相同
idempotency keys，不會建立第二次外部副作用。

## Demo 1：每日營運晨報

單獨執行：

```bash
uv run ecommerce-agent --as ops_01 --workflow daily-report
```

展示重點：

- Freshness 先行；資料過期時在開頭警告。
- Completed-only 營收、訂單、AOV、前週與 28 日平均。
- ALL 漏斗、品類銷售、品牌風險與優先行動 aggregate。
- 事實與推論分區，並附 RAG 行號引用。
- 只建立 `pending_approval` report dry-run。

## Demo 2：沉睡高價值客群活動

一鍵腳本會依序執行：

1. `get_sleepy_product_review`
2. `list_churn_risk_customers`
3. `check_audience_quality`
4. 行銷頻率／核准政策 RAG
5. `draft_retention_edm`
6. `send_edm` dry-run
7. `marketing_approver` 核准
8. 原 Marketing 發起者執行 mock EDM

展示重點：角色限制、客群去重、折扣上限、獨立核准、頻率限制與 side-effect idempotency。

## Demo 3：商品問題分流

一鍵腳本會依序執行：

1. `get_brand_health_alerts`
2. `get_product_health`
3. `create_product_issue` dry-run
4. `pm_approver` 核准
5. 原 PM 發起者執行 mock issue

展示重點：證據由工具產生、同商品 active issue 去重、PM/Admin 核准與可追溯 external ref。

## 稽核檢查

```bash
uv run ecommerce-agent --as admin_01 --tool list_tasks --arguments '{"limit":100}'
tail -n 30 runtime/traces.jsonl
```

Mock artifacts 位於 `runtime/mock_external/`，持久化副作用索引位於
`runtime/mock_external.duckdb`。這些檔案全部被 gitignore。
