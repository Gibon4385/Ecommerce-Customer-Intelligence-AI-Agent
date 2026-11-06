# Sprint 7 Verification Report

日期：2026-11-05

## 任務結果

| Task | 狀態 | 產物／證據 |
|---|---|---|
| S7-T01 Deterministic router | done | `routing.py` |
| S7-T02 Small/large client selection | done | route-aware `MinimalAgent` |
| S7-T03 DuckDB exact cache | done | context-isolated hash key |
| S7-T04 Lexical semantic cache | done | role/scope/version pre-filter |
| S7-T05 PII/action cache policy | done | semantic exclusion、action bypass |
| S7-T06 Daily operations workflow | done | `workflows/daily_report.py` |
| S7-T07 Freshness與數字忠實度 | done | fixed snapshot assertions |
| S7-T08 Report dry-run 與稽核 | done | idempotent pending report task |
| S7-T09 CLI、文件與完整 gate | done | `--workflow daily-report` |

## 晨報工作流

晨報依序經 ToolGateway 呼叫：

1. `get_data_freshness`
2. `get_daily_kpi`
3. `get_conversion_funnel`
4. `get_category_sales`
5. `get_brand_health_alerts`
6. `list_priority_actions`
7. `list_tasks`
8. `search_knowledge`
9. `generate_report`（只建立 dry-run）

Markdown 將「資料事實」與「推論與建議檢查」分區，保留 completed-only、gross profit 與漏斗定義
邊界。資料失敗或 `data_as_of` 落後一天以上時，開頭標示資料延遲並降低結論確定度。相同身分與
資料版本重跑會取得相同 report task，不重複建立。

固定快照驗證會直接比較晨報內的最新營收、訂單與 `data_as_of` 是否等於工具結果，並確認引用
可定位到知識來源。Ops、PM、Marketing 可執行；Support 在 gateway 被拒絕。

## Router

| Intent | Tier | Cache |
|---|---|---|
| query | small | yes |
| diagnosis | large | yes |
| strategy | large | yes |
| action | large | no |
| report | large | no |
| unknown／低信心 | large | yes |

Router 的 tool set 會與角色 RBAC 取交集後才放入 planning prompt。`MinimalAgent` 支援分別注入
small/large `LLMClient`；目前開發 CLI 沒有可驗證的精確模型 entitlement，因此兩個 tier 預設
共用同一個已登入 Codex CLI adapter，不宣稱使用了不同實體模型。

## Cache 安全與失效

- Exact key：question + role + data scope + prompt version + data version。
- Semantic lookup 先以上述 context 過濾，再做 deterministic lexical Jaccard，門檻 0.6。
- Prompt 或 Mart pipeline version 改變會自然 miss，不需要危險的全表 cache flush。
- Email、電話、user ID、hash、姓名 label 出現在 question/answer 時，只能 exact cache，不能被
  semantic lookup 命中。
- Action/report route 不讀也不寫 cache；所有副作用仍必須經 Sprint 6 HITL。
- Cache answer 已通過 output guard，命中後仍再次套用 output guard。

## 人工驗證

```bash
uv run ecommerce-agent --as ops_01 --workflow daily-report
```

確認輸出包含：資料延遲提示、最新 completed-only 營收與訂單、近 28 日平均、ALL 漏斗、最高
營收品類、品牌風險、優先行動摘要、任務狀態、RAG citations，以及 `report_task_id`。

## 已知限制

- Semantic cache 是 lexical similarity，不是 embedding；它刻意偏保守，避免不相關回答誤命中。
- 晨報目前使用資料快照的前 7 筆與前 28 筆比較；正式排程跨缺日資料時應改成 calendar join。
- 優先行動只輸出 aggregate counts，不在晨報列出 user ID。
- 真正排程器與主動推播尚未建立；目前由 CLI 即時執行。
- `generate_report` 仍是 Sprint 6 dry-run，需核准後才由 mock adapter 產生 artifact。

## 最終 deterministic gate

- Ruff：通過。
- Schema contract：45 張表、490,720 列、0 issue。
- Pytest：176 tests passed。
- Coverage：96.05%；daily workflow 100%、router 100%、cache 98%、orchestrator 96%。
