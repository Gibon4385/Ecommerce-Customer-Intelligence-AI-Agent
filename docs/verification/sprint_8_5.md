# Sprint 8.5 Verification Report

日期：2026-11-06

## 任務結果

| Task | 狀態 | 產物／證據 |
|---|---|---|
| S8.5-T01 語言政策與追溯 | done | `docs/multilingual_safety_and_controlled_analytics.md`, traceability matrix |
| S8.5-T02 多語言 red-team corpus | done | `configs/red_team_multilingual.yaml` |
| S8.5-T03 canonical normalization | done | `guardrails/normalization.py` |
| S8.5-T04 guardrail 與 trace 接入 | done | `guardrails/input.py`, `agent/orchestrator.py` |
| S8.5-T05 classifier interface | done | `guardrails/classifier.py`, Fake classifier tests |
| S8.5-T06 Metric Registry 候選 | done | `configs/metric_registry.yaml` |

## 目前運作方式

### 請求處理流程

目前 CLI／Agent 自然語言請求依下列順序處理：

```text
可信 Identity
    ↓
InputGuardrail
    ├─ 空值與 4,000 字元上限
    ├─ NFKC、大小寫、空白及不可見字元 canonical normalization
    ├─ 語言與 mixed-script signals 偵測
    ├─ 現有繁中／英文 deterministic Regex
    └─ SafetyClassifier（只有明確注入實作時才執行）
    ↓
Router → LLM planning → ToolGateway
                         ├─ RBAC
                         ├─ data scope／parameter limits
                         └─ masking／trace
```

Normalization 只產生安全檢查用的 canonical representation，不會改寫送給 Router 或 LLM 的原始
商業問題，也不會參與身分或權限判定。ToolGateway 仍會在每次工具呼叫重新執行 RBAC、scope、limit
與 masking；即使語言偵測或分類器誤判，也不能提高使用者權限。

通過輸入護欄後，request trace 會記錄經遮罩的輸入、原文 SHA-256、偵測語言、信心、支援層級及
normalization signals。Email、電話、User ID 與 restricted hash 仍依既有規則遮罩；不保存未遮罩
的完整輸入副本。

### Provider-neutral interface 是什麼

`SafetyClassifier` 是 Python Protocol，只規定分類器接收 `NormalizedInput`，並回傳固定的
`SafetyClassification`：

```text
prompt_injection / jailbreak / role_impersonation / data_exfiltration / confidence
```

介面不綁定 OpenAI、Claude、本地模型或其他供應商，因此更換 provider 不需要改動 Agent、RBAC
或 ToolGateway。分類器只能回傳風險標籤與信心，不能宣告身分、選擇角色、授權工具或觸發動作。

### Runtime 現況

`MinimalAgent` 預設建立 `InputGuardrail()`，而 `classifier` 預設為 `None`。因此目前正式 Runtime
實際執行的是：

1. canonical normalization 與語言 metadata；
2. 現有繁中／英文 Regex 安全規則；
3. 原有 ToolGateway 後端授權。

目前不會呼叫外部安全模型，也不能宣稱日文、韓文或西班牙文已具有語意分類防護。這些語言仍是
有限支援；後端 RBAC 會繼續阻擋越權工具與資料，但第一層語意攻擊偵測仍待正式分類器補齊。

### Fake classifier 的用途

確定性測試中的 `FakeSafetyClassifier` 不是產品模型，也不會出現在 Runtime。它使用固定 corpus 與
固定結果驗證下列控制流程：

- 分類結果命中高風險標籤時，請求在 LLM／工具呼叫前被拒絕。
- 分類信心低於 `0.8` 時 fail closed，要求改寫或人工檢查。
- 正常的日文、韓文與西班牙文案例不會因語言本身被直接誤擋。
- 測試不呼叫真實 LLM 或外部 API，結果可重現且可進必經 CI。

它證明的是「分類器接上後，控制邏輯會正確執行」，不代表任何真實模型已達到多語言攔截率門檻。

### 正式分類服務接入條件

正式啟用前仍須完成：

1. 選定 provider 與資料保留／區域／timeout／失敗政策。
2. 實作 `SafetyClassifier` adapter，限制只回傳固定 schema。
3. 在 runtime composition root 明確注入 classifier；禁止由對話或 LLM 動態替換。
4. 以完整 red-team 與正常問題 corpus 量測攔截率、誤擋率及各語言結果。
5. 驗證 timeout、無效 schema、provider error 與低信心均採 fail closed，且不產生工具副作用。
6. 達到 `thresholds.md`：red-team 攔截率至少 95%、正常問題誤擋率不高於 5%，關鍵越權與副作用
   案例須 100% 安全。

## Release gate 結果

- Ruff：通過。
- mypy：46 個 source files，0 issue。
- 資料契約：45 張表、490,720 列、0 issue。
- Deterministic tests：189 passed、0 failed、0 error、0 skipped。
- Coverage：96.11%，高於 85% 門檻。
- Clean-runtime smoke：通過。
- Release summary：`reports/verification/release_gate.json`，`ok=true`。

## 尚未啟用的能力

- Runtime 尚未設定正式安全分類服務；目前只有 provider-neutral interface 與 Fake classifier
  控制流程測試，沒有對外部或本地安全模型作出通過聲明。
- 日文、韓文與西班牙文仍是有限支援，不能宣稱完整多語言安全。
- Metric Registry 為 `candidate_not_executable`，尚無 DSL schema、compiler 或已註冊 Agent tool。
- Level 3 任意 SQL 不在本 Sprint 範圍內。
