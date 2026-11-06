# Multilingual Safety and Controlled Analytics

狀態：Sprint 8.5 基礎完成；已建立政策、測試 corpus、normalization 與安全介面，尚未接入正式分類服務或開放 Analytics DSL 執行
優先級：高於 Sprint 9～15 roadmap  
建立日期：2026-11-06

## 為什麼這份設計優先

目前 Sprint 0～8 已建立可信身分、RBAC、typed tools、RAG、護欄、HITL 與稽核基線，但仍有兩個
進入 Slack、排程、Dashboard 或 BigQuery 前應先處理的核心問題：

1. 安全偵測主要針對繁體中文與英文，其他語言或 Unicode 變形可能繞過第一層護欄。
2. 固定 typed tools 安全且可測試，但無法涵蓋所有臨時分析問題；直接開放 text-to-SQL 又會破壞
   資料權限、成本控制與答案可信度。

目標不是讓 Regex 支援世界上所有語言，也不是讓 LLM 自由撰寫 SQL，而是讓使用者能以不同語言
提出更彈性的分析需求，同時確保語言與模型都不能改變身分、權限、資料範圍或執行任意指令。

## 現況與已知限制

### 多語言安全

- `InputGuardrail` 以中英文 Regex 偵測 prompt injection、jailbreak、角色冒充與惡意 SQL。
- 日文、韓文、阿拉伯文等語言，以及拆字、零寬字元、homoglyph 或編碼內容可能不會命中。
- `DeterministicRouter` 的 action、report、strategy 與 diagnosis keywords 主要是中英文；其他語言
  可能被降級成一般 query。
- RAG tokenizer 支援拉丁字母 token 與中文雙字詞，但沒有完整處理日文假名、韓文、阿拉伯文、
  泰文或跨語言查詢。
- Email、電話、固定格式 User ID 與 hash 的遮罩較不依賴語言；姓名標籤、折扣、補償與成效保證
  的輸出規則仍偏中英文。
- System Prompt 要求以繁體中文回答，因此目前應宣稱「繁體中文／英文優先」，不能宣稱完整多語言。

### 查詢彈性

- 現有 Agent 只能選擇已註冊 typed tools，不能執行任意 SQL。
- 這可保護 Mart-only、RBAC、欄位遮罩、limit、資料定義與 audit，但特殊分析問題可能沒有對應工具。
- 直接加入 `run_sql(sql: string)` 會引入越權讀取、PII 外洩、錯誤 join、高額掃描、長時間查詢與
  prompt injection 轉成資料外洩等風險。

## 不變的安全原則

無論使用何種語言、LLM 或資料後端，下列規則都不能交給模型決定：

- Identity 只能由可信 Channel Adapter／Identity Provider 建立。
- 對話內容與 LLM 輸出不能修改使用者角色。
- 每次工具呼叫都由 Tool Gateway 重新檢查 RBAC、scope、limit 與 denied fields。
- Agent 只能存取 Mart／營運 Mart，不開放 Raw、Staging 或 Intermediate。
- LLM 不直接產生可執行 SQL、shell command 或任意資料庫操作。
- 外部副作用仍須 HITL、冪等與完整 audit trail。
- 安全分類器與翻譯可能判錯，因此不能取代後端授權邊界。

## Workstream A：Multilingual Safety

### A1. 輸入正規化

所有自然語言入口先建立 canonical representation，再執行安全偵測：

- Unicode normalization。
- 移除或標記零寬字元與不可見控制字元。
- 全形／半形、大小寫與空白正規化。
- 偵測混合 script 與常見 homoglyph。
- 保存原始輸入 hash 與正規化後的安全事件，但 trace 仍需遮罩 PII。

正規化只能提高偵測率，不能改寫使用者實際商業問題或作為授權依據。

### A2. 語言偵測與支援政策

為每次請求產生：

```json
{
  "detected_language": "ja",
  "confidence": 0.97,
  "supported": true
}
```

第一版建議明確支援繁體中文與英文，並為其他語言採取其中一種政策：

- 支援：進入多語言安全分類與後續流程。
- 有限支援：翻譯成 canonical language 後檢查，並告知翻譯限制。
- 未支援：安全拒絕或要求改用支援語言。

不能在未測試的情況下自動宣稱所有語言皆受支援。

### A3. 多語言安全分類

在 Regex 之外增加只負責分類、沒有工具權限的安全層，輸出固定 schema：

```json
{
  "prompt_injection": true,
  "jailbreak": false,
  "role_impersonation": true,
  "data_exfiltration": false,
  "confidence": 0.94
}
```

- Regex 保留為快速且可解釋的高信心規則。
- 分類器處理不同語言、語意改寫與混合語言。
- 高風險或低信心請求採 fail closed、要求改寫或進入人工檢查。
- 分類器不可回傳角色、授權工具或直接觸發動作。

### A4. 多語言路由與 RAG

- 將 router 從中英文 substring 擴充為可測試的 multilingual intent classifier。
- action／report 等高風險 intent 在低信心時走 large tier 並禁止自動副作用。
- RAG 改用支援目標語言的 tokenizer、multilingual embeddings，或 query translation＋原文引用。
- 文件權限仍必須在 similarity ranking 前過濾。
- 翻譯後的回答必須保留原始 citation、版本與行號。

### A5. 多語言輸出安全

- 擴充折扣、補償、保證與角色承諾的多語言偵測。
- PII 遮罩加入不同語言姓名標籤與地區格式。
- 優先依欄位 schema 移除 PII，而不是只靠輸出文字 Regex。
- 回答語言由明確 policy 決定，不讓模型自行猜測敏感語境。

### A6. Red Team 與驗收門檻

測試集至少涵蓋：

- 繁體中文、英文、日文、韓文、西班牙文與混合語言。
- Unicode homoglyph、零寬字元、拆字、Base64／編碼提示。
- 直接、間接與 RAG 文件內 prompt injection。
- 角色冒充、System Prompt extraction、資料外洩與惡意 SQL 意圖。
- 正常業務問題與安全否定語境，控制 false positive。

建議門檻：

- 關鍵角色冒充與越權案例：100% 被後端 RBAC 阻擋。
- 已知高風險多語言 red-team cases：100% 不得產生工具副作用。
- 支援語言的正常業務問題誤擋率：不高於既有 5% 門檻。
- 不隱藏 skipped／xfail；每個案例對應 traceability ID。

## Workstream B：Controlled Analytics Query

### B1. 三層查詢模型

#### Level 1：固定 typed tools

保留現有工具處理高頻、關鍵且需要穩定口徑的問題，例如 KPI、漏斗、品類銷售、商品健康與
資料新鮮度。這一層最容易測試，也應繼續作為預設路徑。

#### Level 2：受限 Analytics DSL

新增通用分析工具，但輸入是結構化 JSON，不是 SQL：

```json
{
  "metric": "repeat_purchase_rate",
  "dimensions": ["category", "city"],
  "filters": {
    "customer_type": "new"
  },
  "date_range": {
    "days": 90
  },
  "limit": 100
}
```

後端依 registry 驗證後，才由程式編譯成 DuckDB 或 BigQuery query。可控制：

- Allowlisted metrics、dimensions、filters 與 operators。
- Metric 定義、aggregation grain 與合法 join path。
- 角色可用欄位與資料範圍。
- 日期範圍、row limit、timeout 與查詢成本。
- completed-only、NULL、cohort 等既有業務口徑。
- 回傳 schema、data-as-of、notices 與 trace ID。

#### Level 3：受控進階分析

只有確定存在必要性時，才評估提供少數 Analyst／Admin 使用的獨立查詢服務。即使建立，也必須：

- 僅允許 `SELECT` 與 authorized views。
- 使用 SQL AST parser，不以 Regex 判斷 SQL 安全。
- 禁止 DDL、DML、Raw、Staging、Intermediate 與敏感欄位。
- 限制 function、join、subquery、掃描量、timeout 與 rows。
- BigQuery 先執行 dry run 與 maximum bytes billed 檢查。
- 完整記錄 query fingerprint、身份、成本、資料版本與結果筆數。
- 必要時要求人工核准。

Level 3 不代表允許 LLM 直接輸出並執行任意 SQL；若無法證明安全需求，應維持不提供。

### B2. Metric Registry

每個 metric 必須定義：

- 名稱與業務說明。
- 來源 Mart／view。
- 計算公式與 aggregation grain。
- 可搭配 dimensions、filters 與 date fields。
- NULL、分母為零與缺日處理。
- 允許角色與 denied fields。
- DuckDB 與 BigQuery 實作。
- 測試 fixture 與預期結果。

模型只能選擇 registry 中存在的項目，不能自行發明欄位、join 或公式。

### B3. Query Compiler 與 Policy Engine

建議資料流：

```text
Natural Language
      ↓
Structured Analysis Intent
      ↓
Schema Validation
      ↓
RBAC／Scope／Cost Policy
      ↓
Server-side Query Compiler
      ↓
DuckDB／BigQuery Read-only Marts
      ↓
Masked Typed Result＋Trace
```

- LLM 只產生 Analysis Intent。
- Policy Engine 在編譯前拒絕不合法組合。
- Compiler 使用受控 templates／query builder，不拼接模型輸出的 SQL fragment。
- Repository 使用唯讀 credential，資料庫權限作為最後防線。

### B4. 驗收門檻

- 不允許未註冊 metric、dimension、filter、operator 或 join。
- 所有 query 都必須通過相同 RBAC、scope、limit 與 masking。
- DuckDB／BigQuery parity tests 驗證 schema、排序、NULL、日期與 completed-only 定義。
- 惡意 DSL payload、超大日期範圍與高成本查詢在執行前被拒絕。
- 每個結果均包含 data version、data-as-of、notices 與 trace ID。
- Golden cases 比對 typed tool 與 DSL 對相同問題的數字一致性。

## 建議實作順序

這兩條 workstream 應作為 Sprint 9 前置 gate，而不是等到 BigQuery 上線後才補：

1. 文件化目前只支援繁體中文／英文優先，以及固定 typed tools 的限制。
2. 建立多語言與 Unicode red-team corpus，先量測現有失敗率。
3. 實作輸入正規化與語言偵測，不改變現有 RBAC 邊界。
4. 加入多語言安全分類與輸出安全測試。
5. 定義 Metric Registry 與 Analytics Intent schema。
6. 在 DuckDB 完成 DSL compiler、policy tests 與數字忠實度測試。
7. Slack 接入時共用同一套 multilingual guardrail 與 Identity boundary。
8. BigQuery 接入時只替換 Repository backend，並執行 parity、成本與 dry-run gates。

## 與 Sprint 9～15 的關係

- Sprint 9 Slack：多語言正規化、可信 Identity 與安全分類必須在 channel boundary 生效。
- Sprint 10 原因分析：優先使用 typed diagnosis tools／Analytics DSL，不讓模型自由拼湊數字。
- Sprint 11～12 任務與排程：任何語言都不能繞過確認、HITL 與 workflow allowlist。
- Sprint 13 Dashboard：只顯示經 RBAC 與 masking 的 typed results。
- Sprint 14 BigQuery：使用唯讀 Repository、authorized views、cost guard 與 parity tests。
- Sprint 15 正式部署：將多語言 red team、query policy 與安全事件納入 monitoring。

## 明確非目標

- 不以增加大量 Regex 宣稱完整多語言安全。
- 不讓翻譯服務或安全分類器決定使用者角色。
- 不讓 LLM 直接執行 SQL、shell 或資料庫管理命令。
- 不因提高查詢彈性而開放 Raw、Staging、Intermediate 或 PII。
- 不在缺少測試、成本限制與 audit 的情況下開放任意分析。

## 下一步決策

正式實作前需要確認：

1. 第一批正式支援語言及未支援語言的處理政策。
2. 安全分類器使用本地模型、OpenAI、Claude 或其他服務。
3. Metric Registry 第一批 metrics、dimensions 與角色矩陣。
4. 是否有真實需求需要 Level 3 SQL；若沒有，先只做 typed tools＋Analytics DSL。
5. 多語言安全與查詢彈性的 release gate 門檻及負責人。

## Sprint 8.5 已確認決策

- 正式支援語言：繁體中文與英文。
- 有限支援語言：日文、韓文與西班牙文；低安全信心時 fail closed，要求改寫或人工檢查。
- 安全分類器先採 provider-neutral interface；確定性測試只使用 Fake classifier，不呼叫外部 LLM。
- Controlled Analytics 先維持 Level 1 typed tools，並設計 Level 2；不實作 Level 3 SQL。
- 第一批 Metric Registry 候選為 daily KPI、conversion funnel、category sales。
- `configs/metric_registry.yaml` 是不可執行的候選規格；在 DSL schema、compiler 與 policy tests
  完成前，不得註冊為 Agent tool。
