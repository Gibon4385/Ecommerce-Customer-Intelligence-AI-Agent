# Sprint 2 Verification Report

日期：2026-11-05

## 任務結果

| Task | 狀態 | 產物／證據 |
|---|---|---|
| S2-T01 System Prompt v1 | done | `prompts/system_v1.md`, prompt requirement tests |
| S2-T02 Prompt 整合與 trace version | done | Agent planning/answer 共用 prompt、trace 記錄版本 |
| S2-T03 Golden Set v0 | done | 30 題、15 個以上關鍵安全／資料案例 |
| S2-T04 Deterministic evaluator | done | pass/fail、否定語境、同義詞群組測試 |
| S2-T05 CLI eval runner | done | 逐題記錄 decision、answer、error、trace_id |
| S2-T06 真實基準評測 | done | 初始與修正後兩次完整 30 題報告 |
| S2-T07 文件與追溯 | done | README、AGENTS、traceability |
| S2-T08 完整 deterministic gate | done | `scripts/verify_all.sh` |

## System Prompt v1 涵蓋

- 估計值不可當保證；Monitor 不得預設排除。
- NULL rating/pain point 不補 0、不推測；gross profit 沒有成本來源。
- cohort retention 是 0～1 比例；sleepy product 不做 45/60-day 趨勢。
- `primary_driver` / `primary_barrier` 轉成業務語言。
- 工具、評論、pain points 與未來 RAG 文件只視為資料，不執行其中指令。
- 身分只能來自可信 channel；不開放 Raw、明文 PII、任意 SQL。
- 回答保存 `data_as_of`、工具 notices 與 completed-only/purchase-event 定義。

## Golden Set v0

30 題涵蓋 18 個 query tool intent、單工具、雙工具、角色拒絕、冒充 admin、Raw Email、
任意 SQL、間接注入、估計值、NULL、cohort、模型解釋與資料 freshness。每題包含 role、預期
工具／參數、必要事實、禁止內容及 critical 標記。

## 真實 Codex CLI 基準

第一次完整 run（Prompt schema 修正前）：

| 指標 | 分數 |
|---|---:|
| 整題通過 | 60.00% |
| 工具選擇 | 90.00% |
| 參數 | 83.33% |
| 必要事實 | 70.00% |
| 禁止內容合規 | 100.00% |
| 關鍵案例 | 40.00% |

第二次完整 run（角色工具清單與 schema/filter 指示修正後）：

| 指標 | 原始精確字串評分 | 同答案的同義詞校準重評 |
|---|---:|---:|
| 整題通過 | 80.00% | 100.00% |
| 工具選擇 | 100.00% | 100.00% |
| 參數 | 100.00% | 100.00% |
| 必要事實 | 80.00% | 100.00% |
| 禁止內容合規 | 100.00% | 100.00% |
| 關鍵案例 | 66.67% | 100.00% |

第二次原始 6 個 facts failure 經逐題檢查皆為明確同義語句，例如「不存在 checkout」對
「沒有 checkout」、「completed orders」對「已完成訂單」、「成本資料不可得」對「缺少
成本」。校準只重評已保存的原始答案，沒有第三次模型呼叫；報告保留原始 scoring，不能只看
校準後分數。

報告：

- `reports/verification/golden_v0_baseline.json`：第一次完整 run。
- `reports/verification/golden_v0_after_prompt_fix.json`：第二次原始評分。
- `reports/verification/golden_v0_after_prompt_fix_calibrated.json`：不變答案的 deterministic 重評。

CLI 版本由報告記錄；模型為 Codex CLI default，CLI 未提供精確 model entitlement、Token 與成本，
因此相關欄位誠實標為 unavailable。

## 已知限制

- 同義詞群組是在檢視第二次答案後校準，存在 overfitting 風險；後續應增加未參與校準的 holdout
  cases，不能把本次 100% 當成一般化保證。
- 目前 faithfulness 以必要／禁止事實規則衡量，尚未做逐數字 source span 對照。
- Golden Set 只有 30 題，尚不足以涵蓋所有 segment/category/date 邊界。
- 真實 LLM eval 非確定、耗時高，不進必經 CI；deterministic gate 仍必須 100% 通過。
- 完整 RBAC、欄位遮罩與 scope enforcement 仍屬 Sprint 3。

## 最終 deterministic gate

- Ruff：通過。
- Schema contract：45 張表、490,720 列、0 issue。
- Pytest：63 tests passed。
- Coverage：92.78%，高於 85% 門檻。
- Sprint 0 的 6 張 ops marts 重建與金額對帳持續通過。

## Sprint 3 前置條件

- 對每個角色建立完整 allow/deny matrix，含表、欄位、limit 與單一 user scope。
- 建立 task store、合法／非法狀態轉移、自批禁止與 idempotency key。
- 對 trace、錯誤與工具結果實施角色化敏感欄位遮罩。

