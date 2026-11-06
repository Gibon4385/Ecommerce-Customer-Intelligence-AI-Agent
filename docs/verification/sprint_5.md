# Sprint 5 Verification Report

日期：2026-11-05

## 任務結果

| Task | 狀態 | 產物／證據 |
|---|---|---|
| S5-T01 確定性輸入護欄 | done | `guardrails/input.py` |
| S5-T02 prompt injection／jailbreak | done | 中英文 pattern 與 red-team tests |
| S5-T03 角色冒充／惡意 SQL／長輸入 | done | pre-LLM blocking tests |
| S5-T04 PII 輸出遮罩 | done | Email、姓名、電話、user ID、hash tests |
| S5-T05 未授權承諾攔截 | done | 折扣、補償、退款、成效保證 tests |
| S5-T06 間接注入邊界 | done | final-answer phase 不接受第二次 tool call |
| S5-T07 CLI 與 trace | done | safe blocked JSON、category、trace_id |
| S5-T08 Golden evaluator 相容 | done | G024/G025 deterministic refusal |
| S5-T09 文件與完整 gate | done | README、traceability、`verify_all.sh` |

## 執行順序

```text
使用者訊息
  → InputGuardrail（規則、長度）
  → LLM planning
  → ToolGateway（可信身分、RBAC、scope、limit、欄位遮罩）
  → LLM final answer（不能再觸發工具）
  → OutputGuardrail（PII、承諾、offer）
  → 回答與最小化 trace
```

護欄不取代 ToolGateway。即使模型或 RAG 文件要求改變角色，gateway 仍只接受 channel identity。

## 輸入護欄結果

- Red-team 規則案例：12/12 攔截，100%，高於 95% 門檻。
- 正常業務問題：21/21 放行，觀察誤擋率 0%，低於 5% 門檻。
- 類別包含 `prompt_injection`、`jailbreak`、`role_impersonation`、`malicious_sql`、
  `oversized_input` 與 `empty_input`。
- 被阻擋內容不寫入 trace；trace 只保存方向、category、action 與 error type。

這些比例只描述目前固定 fixture，不代表對未知攻擊的一般化保證。

## 輸出與間接注入

- Email、電話、`U000001` 型 user ID、64 位 hash 及具 `姓名:` label 的姓名會被遮罩。
- 未否定的營收／收益／轉換保證，以及發放折扣、優惠券、退款或補償會被阻擋。
- 「不能保證營收」「未核准前不得提供折扣」等安全否定語境會放行。
- RAG／工具文字只進入 final-answer prompt；final phase 若回傳 tool request，Agent 會拒絕，不能
  形成第二次工具呼叫。

## 已知限制

- 規則層偏向高精確度，不是完整自然語言惡意意圖分類器；變形、錯字或跨語言隱晦攻擊仍需
  持續加入 fixture。小模型判斷層尚未導入。
- 無 label 的任意人名無法可靠以 regex 辨識；目前資料工具本身不提供姓名欄位，且 gateway
  仍是第一層資料最小化邊界。
- 直接 typed-tool CLI/MCP 不經 LLM input guard；其輸入有 typed schema、RBAC、scope 與 limit，
  輸出由 gateway 遮罩。`search_knowledge` query 只做 lexical retrieval，不執行內容。
- 真實外部 action 尚未存在；HITL、過期核准、頻率限制與 adapter 副作用於 Sprint 6 驗證。

## 最終 deterministic gate

- Ruff：通過。
- Schema contract：45 張表、490,720 列、0 issue。
- Pytest：146 tests passed。
- Coverage：94.93%；input guard 100%、output guard 96%、orchestrator 95%、gateway 98%。

## Sprint 6 前置條件

- 每個 action 先產生不可執行 dry-run preview。
- 錯誤核准者、自批、未核准與過期核准一律不可執行。
- 外部 adapter 必須用 mock 驗證成功、timeout、部分失敗、retry 與 idempotency。
