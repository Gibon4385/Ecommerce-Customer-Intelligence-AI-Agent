# Next Phase Roadmap：Sprint 9～15

狀態：規劃中，尚未開始  
建立日期：2026-11-05

> **優先前置設計：** 多語言護欄與受控彈性查詢的風險會同時影響 Slack、排程、RAG、Dashboard
> 與 BigQuery，因此應先完成
> [`multilingual_safety_and_controlled_analytics.md`](multilingual_safety_and_controlled_analytics.md)
> 的決策與驗收基線，再開始 Sprint 9～15。

## 目前基線

本專案目前以 Sprint 0～8 的成果作為穩定基線，暫不繼續增加產品功能。現階段優先事項是：

1. 將專案整理並上傳至 GitHub。
2. 熟悉安裝、資料初始化、角色權限、CLI、RAG、HITL、晨報、測試與 release gate。
3. 透過不同角色完成人工驗證，理解資料與安全邊界。
4. 保存目前 177 個 deterministic tests 全數通過、coverage 96.07% 的驗證狀態。

Sprint 9～15 是下一階段候選規劃，不代表已承諾、已實作或已驗證。正式開始前仍需逐一確認需求、
部署環境、Slack 資產、身分來源、LLM provider 與資料存取方式。

## 架構方向

```text
Slack／CLI／HTML Dashboard
            │
      Channel Adapter
            │
       Agent Service
   ┌────────┼────────┐
   │        │        │
ToolGateway RAG   Scheduler
   │                 │
DuckDB／BigQuery   Tasks／Runs
```

- Slack 屬於訊息 Channel Adapter，負責可信身分、收送訊息與 thread context。
- BigQuery 不屬於 Channel Adapter；它是唯讀的 Repository／warehouse adapter。
- CLI、Slack 與 Dashboard 必須共用同一套 Tool Gateway、RBAC、遮罩、HITL 與 trace。
- 開發階段先使用 Codex CLI；正式多人環境可再選擇 OpenAI API 或 Claude API。
- 開發與目前 runtime 繼續使用 DuckDB，不使用 SQLite。

## Sprint 9：Slack Channel 基礎

目標：讓已授權使用者能透過 Slack 安全詢問現有資料。

預定工作：

- 盤點先前申請或建立的 Slack App／ChannelAdapter。
- 確認 App ID、Bot token、signing secret、OAuth scopes 與 event subscriptions。
- 定義共用 `ChannelAdapter` interface。
- 建立 `SlackChannelAdapter`，並保留現有 CLI adapter。
- 將 Slack user ID 對應到可信內部 Identity 與角色。
- 支援 thread conversation、trace ID 與基本 Block Kit 回覆。
- 將 CLI 入口與核心 Agent 邏輯拆成共用 `AgentService`。
- 驗證角色冒充、未註冊使用者與跨 thread／跨使用者資料隔離。

完成條件：Slack 可以查詢現有 typed tools；權限結果必須與 CLI 完全一致。

## Sprint 10：近期成效與原因分析

目標：透過 Slack 詢問近期營運成效，並取得有證據、有限度的原因推測。

預定工作：

- 支援營收、訂單、AOV、漏斗、品類、活動與資料新鮮度比較。
- 建立 deterministic period comparison 與 diagnosis tools。
- 回答明確區分「資料事實」、「可能原因」與「無法證明的因果」。
- 樣本不足、NULL 或資料延遲時降低結論確定度。
- 所有分析附資料截止日、使用指標與 trace ID。
- LLM 不得自行產生或執行 SQL。

完成條件：回答中的數字可回溯到 Mart，且不把相關性描述成已證實因果。

## Sprint 11：Slack 任務指派

目標：讓使用者用自然語言建立、指派與追蹤團隊協作任務。

預定工作：

- 新增 collaboration task，與既有 action HITL task 分離。
- 支援負責角色／人員、優先級、期限、證據與狀態。
- 自然語言先解析成結構化草稿，再由使用者確認建立。
- 支援 `open → in_progress → completed/cancelled`。
- 保存 assignment、comment 與 status history。
- Slack thread 與 task 建立固定對應。

完成條件：任務的建立、修改、完成與取消都有可信身分及完整 audit trail。

## Sprint 12：自然語言排程

目標：讓使用者透過 Slack 建立白名單工作流排程。

第一批候選工作流：

- 每日營運晨報。
- 每週營收摘要。
- 資料延遲提醒。
- 我的待辦與待核准提醒。
- 高風險商品提醒。
- 行銷活動成效摘要。

預定工作：

- 建立 `scheduled_jobs`、`scheduled_job_runs` 與 `notification_deliveries`。
- 自然語言解析成受限的 schedule intent。
- 建立前顯示頻率、時區、目的地與內容確認卡片。
- 建立 scheduler worker、retry、失敗通知及執行歷史。
- 支援暫停、恢復、修改與取消。
- 每次執行時重新檢查角色與資料權限。
- 具副作用的 EDM／外部工單每次仍須走 HITL，不因排程而自動放行。

完成條件：排程只能觸發已註冊 workflow，不能執行任意 SQL、shell command 或任意 prompt。

## Sprint 13：固定版型 HTML Dashboard

目標：先確認固定 HTML 版型，後續只更新內容與資料，不讓 AI 任意改動版面或 JavaScript。

Dashboard 第一版範圍：

- 營運 KPI。
- 資料新鮮度。
- 我的待辦／待核准。
- 排程執行狀態。

預定工作：

- 先製作純靜態 HTML/CSS mockup 供版型確認。
- 定義 dashboard JSON schema。
- 使用固定 renderer 將資料填入模板。
- 固定 KPI 卡片、趨勢圖、待辦與排程區塊位置。
- AI 只產生或更新符合 schema 的內容，不直接輸出可執行 JavaScript。
- Dashboard API 經過同一套 RBAC；瀏覽器不得直接讀取 DuckDB 或 BigQuery。

完成條件：不同角色只看到授權內容，且資料更新不會改變已確認的視覺版型。

## Sprint 14：BigQuery 唯讀 Repository Adapter

目標：讓既有 typed tools 可以改由 BigQuery Marts 提供資料，而不改變安全邊界。

預定工作：

- 建立 `BigQueryRepositoryAdapter`。
- 使用專用 GCP Service Account。
- 僅授權必要 Mart dataset 或 authorized views 的讀取權限。
- 禁止 Raw、Staging、Intermediate 與所有資料寫入權限。
- 使用 table／view allowlist 與固定參數化查詢。
- 保留 RBAC、欄位遮罩、limit、data-as-of 與 trace。
- 建立 DuckDB／BigQuery parity tests，驗證 schema、NULL、completed-only、排序與日期行為一致。

完成條件：同一 typed tool 在 DuckDB 與 BigQuery 的契約一致，且 AI 無法提交任意 SQL。

## Sprint 15：GCP 與正式 LLM 部署

目標：將開發原型轉為可供多人使用的受控服務。

候選架構：

```text
Slack
  ↓
GCP Webhook／Bot Service
  ↓
Agent Service
  ├─ OpenAI API 或 Claude API
  ├─ BigQuery read-only
  └─ Scheduler／Task State
```

預定工作：

- 評估 Slack Events API、Socket Mode 與 GCP hosting 方式。
- 改用適合多人服務的 OpenAI 或 Claude API adapter。
- Codex CLI 保留為本機開發工具，不作為正式多人後端。
- 導入 Secret Manager、webhook signature 驗證與 rate limit。
- 建立 queue、worker isolation、delivery retry、monitoring 與成本追蹤。
- 決定 DuckDB 在 GCP 部署的持久化與單 writer 策略；若無法滿足需求，另行提出架構決策，
  不在未經確認時擅自更換資料庫。

完成條件：正式環境的身分、密鑰、資料權限、併發、重試、監控與災難復原都有可驗證方案。

## 下一階段開始前的決策點

1. 先前 Slack ChannelAdapter／Slack App 的實際完成狀態與可用憑證。
2. Slack 第一版採 Socket Mode 或公開 webhook。
3. Slack user 與企業身分、角色的 canonical mapping 來源。
4. Dashboard 版型、品牌樣式與預期使用裝置。
5. 排程可用 workflow、最低／最高頻率與預設時區。
6. GCP project、BigQuery dataset 與 authorized views 範圍。
7. 正式 LLM provider 選擇及資料保留政策。

## 現階段建議操作

在 Sprint 9 正式開始前，先依現有文件熟悉專案：

```bash
uv sync --frozen --dev
./scripts/verify_all.sh
uv run python -m scripts.run_portfolio_demos
```

並依序人工體驗 Support、PM、Marketing、Ops、Admin 的查詢、越權阻擋、RAG、HITL、晨報與稽核。
GitHub 上傳前應再確認 `.gitignore`，避免提交金鑰、明文 PII、`runtime/*.duckdb`、trace、mock artifacts
與本機 cache。
