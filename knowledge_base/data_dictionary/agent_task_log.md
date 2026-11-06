# agent_task_log

Sprint 3 的 Agent 任務稽核表，僅存在 `runtime/agent_tasks.duckdb`，不屬於 CSV Mart，也不提交
版本控制。所有時間欄位都是 UTC，使用 DuckDB `TIMESTAMP` 儲存。

| Column | Type | Meaning |
|---|---|---|
| task_id | VARCHAR | UUID 任務主鍵 |
| created_at | TIMESTAMP | 建立時間（UTC） |
| requested_by | VARCHAR | 可信 channel identity |
| requester_role | VARCHAR | 建立當下角色 |
| task_type | VARCHAR | 任務類型 |
| status | VARCHAR | draft、pending_approval、approved、executed、failed 或 cancelled |
| target_summary | VARCHAR | 不含敏感明細的目標摘要 |
| payload_ref | VARCHAR nullable | payload 的安全參照，不直接存大量敏感內容 |
| approved_by | VARCHAR nullable | 核准者；不可等於 requested_by |
| approved_at | TIMESTAMP nullable | 核准時間（UTC） |
| approval_expires_at | TIMESTAMP nullable | 核准失效時間（UTC） |
| executed_at | TIMESTAMP nullable | 執行時間（UTC） |
| external_ref | VARCHAR nullable | 未來外部 adapter 的回傳識別碼 |
| idempotency_key | VARCHAR unique | 防止重複建立／重複副作用 |
| trace_id | VARCHAR | 對應 JSONL trace |
| attempt_count | INTEGER | 執行與拒絕嘗試次數 |
| last_error | VARCHAR nullable | 最近一次失敗的例外型別；成功或重新核准後清除 |

角色可見範圍：Admin、Ops 可查全部；其他角色只能查 `requested_by` 等於自己的任務。

## agent_task_payloads

同一個 DuckDB runtime 中的 action payload 與 dry-run preview。以 `task_id` 為主鍵；不放入
`agent_task_log`，避免一般任務清單攜帶完整內容。Preview 的 `executable` 必須是 `false`。

## agent_task_attempts

每次執行成功、可重試失敗或拒絕都新增一列，包含 actor、outcome、error type、external ref 與
trace ID。這張表是 append-only audit evidence；重試不覆蓋先前失敗。
