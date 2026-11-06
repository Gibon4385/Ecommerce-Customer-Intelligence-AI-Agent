# Ecommerce Customer Intelligence AI Agent

這是一個電商客戶情報 AI Agent 專案，延伸自另一個資料與預測專案
`Ecommerce-Customer-Intelligence-Predictive-Growth-Suite`，並獨立成可單獨開發、測試與部署的
Agent 系統。

上游專案負責整理電商資料、建立客戶與商品分析模型，以及產出營運 Marts；本專案目前將那些
最終產出匯出為 CSV，作為可重現的開發資料。長期目標是讓 Agent 直接連接上游資料平台，讓不同
團隊能用自然語言查詢營運狀況、取得有依據的建議，並在權限與人工核准下執行後續工作。

目前完成 Sprint 0～8，包含資料契約、查詢工具、RAG、角色權限、安全護欄、HITL action、晨報
工作流、快取、路由、稽核與 deterministic release gate。詳細實作與驗證證據集中在
[`docs/verification/`](docs/verification/)。

## 一個問題如何走完整個系統

假設星期一早上，營運主管問 AI：

> 最近十天營收為什麼下降？請找出可能原因，並整理今天需要處理的事項。

AI 不會立刻自由發揮。首先，**系統提示詞**會告訴它這是一位電商營運助手，營收只能計算
completed orders，推測必須和資料事實分開，也不能做出未經核准的商業承諾。

接著，**護欄**會先檢查問題是否包含 prompt injection、角色冒充或惡意 SQL；**權限層**則從可信
來源確認提問者是 Ops，而不是相信他在對話中自稱 Admin。系統因此只開放 Ops 被允許使用的資料、
工具與查詢範圍。

確認安全後，**路由器**判斷這不是單純查數字，而是需要比較趨勢與推測原因的診斷問題，因此選擇
較完整的推理路徑；簡單查詢則可交給較小的模型，降低延遲與成本。目前開發環境共用 Codex CLI
adapter，架構已保留未來分接 small／large model 的能力。

在重新計算前，系統會先檢查 **Cache**。只有角色、資料範圍、提示詞版本與資料版本都一致時，
相同問題才可以直接沿用答案；包含個資或會產生行動的請求不會使用不安全的 semantic cache。

若沒有可用快取，AI 會透過 **MCP tools** 查詢每日營收、訂單、AOV、轉換漏斗、品類表現與資料
新鮮度。這些工具只讀取允許的 Marts，具有固定參數與筆數上限；LLM 不會接觸 Raw data，也不能
自行產生任意可執行 SQL。資料口徑也由工具固定：營收只計 completed orders；來源沒有 `checkout` event，
漏斗終點使用 purchase event；成本資料尚未提供，因此 `gross_profit` 的 `NULL`
代表不可得，不能解讀為零。

如果需要確認公司對異常指標或後續處理的規範，AI 會使用 **RAG** 搜尋政策、資料字典與操作文件，
並在回答中附上來源版本與行號。目前知識層使用 DuckDB 的 deterministic lexical index，未來可隨
文件規模擴充為 embedding／向量資料庫。

最後，AI 將回答整理成「資料事實、可能原因、建議行動」，輸出護欄會再次遮罩 Email、電話、
User ID、姓名與 hashed identifier。若主管進一步要求建立報告或執行行動，系統只會先建立 dry-run，
並等待另一位有權限的人核准，不會直接產生外部副作用。

整段流程都受 **可觀測性**管理：每次請求、身分判定、工具呼叫、核准與執行結果都有 trace ID。
系統保存經遮罩的請求資訊、提示詞版本和流程事件；每次提示詞或流程改動，也必須重新執行 Golden
Set、安全案例與 deterministic release gate，確認既有能力沒有退化。

目前 release gate 的基線為：177 個 deterministic tests 全數通過、coverage 96.07%，資料契約驗證
涵蓋 45 張表與 490,720 列。完整結果見
[`docs/verification/sprint_8.md`](docs/verification/sprint_8.md)。

## 在自己的電腦上執行

目前 Sprint 0～8 是可在本機完整重現的開發原型；正式的 GCP／Slack 多人部署屬於下一階段。
本機需要 Git、[uv](https://docs.astral.sh/uv/) 與 Python 3.12 以上版本。

```bash
git clone <repository-url>
cd Ecommerce-Customer-Intelligence-AI-Agent
uv sync --frozen --dev
```

Demo Raw 不放入版本控制。下列指令會從 committed staging data 重建開發資料、建立營運 Marts，
並驗證資料契約：

```bash
uv run python scripts/bootstrap_demo_raw.py
uv run python scripts/build_ops_marts.py
uv run python scripts/generate_synthetic_ops.py
uv run python scripts/validate_data.py
```

### 驗證專案

一個指令即可執行 lint、type check、資料重建、177 個 deterministic tests、coverage、三條展示流程
與 clean-runtime smoke test：

```bash
./scripts/verify_all.sh
```

成功後，機器可讀的測試、coverage、資料品質與 release summary 會產生在
`reports/verification/`。這套必經驗證不呼叫真實 LLM，也不會寄信或建立外部工單。

### 體驗目前功能

直接呼叫 typed tool 不需要 LLM，可以先查看最新十天的 completed-order KPI：

```bash
uv run ecommerce-agent \
  --as ops_01 \
  --tool get_daily_kpi \
  --arguments '{"limit":10}'
```

執行包含營收、漏斗、品類、風險、待辦與 RAG 引用的每日營運晨報：

```bash
uv run ecommerce-agent --as ops_01 --workflow daily-report
```

一次執行晨報、行銷留存與商品問題三條 deterministic 展示流程：

```bash
uv run python -m scripts.run_portfolio_demos
```

若電腦上的 Codex CLI 已登入，才需要使用自然語言入口：

```bash
uv run ecommerce-agent \
  --as ops_01 \
  --ask '請分析資料中最新十天的收入趨勢'
```

開發身分包含 `support_01`、`pm_01`、`marketing_01`、`ops_01` 與 `admin_01`；切換 `--as`
可以人工驗證不同角色的工具權限、資料範圍與欄位遮罩。更完整的角色與 HITL 操作流程見
[`docs/demos.md`](docs/demos.md)，常見問題見
[`docs/troubleshooting.md`](docs/troubleshooting.md)。

## 下一階段

Sprint 9～15 暫列為下一階段，尚未開始實作：

- 透過 Slack 與 Agent 對話。
- 分析近期成效並提出有證據的可能原因。
- 用自然語言建立、指派與追蹤任務。
- 建立白名單工作流排程與執行紀錄。
- 提供固定版型的 HTML 營運 Dashboard。
- 以唯讀權限連接 BigQuery Marts。
- 部署至 GCP，並評估 OpenAI 或 Claude API 作為正式多人服務的模型後端。

在開始上述功能前，優先處理多語言 prompt injection、非中英文路由／RAG，以及在不開放任意 SQL
下提供彈性分析的設計。詳見
[`docs/multilingual_safety_and_controlled_analytics.md`](docs/multilingual_safety_and_controlled_analytics.md)。

完整規劃見 [`docs/next_phase_roadmap.md`](docs/next_phase_roadmap.md)。現階段專案維持 Sprint 0～8
的穩定狀態，優先進行 GitHub 整理、人工驗證與熟悉整體運作方式。
