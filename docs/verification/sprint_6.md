# Sprint 6 Verification Report

日期：2026-11-05

## 任務結果

| Task | 狀態 | 產物／證據 |
|---|---|---|
| S6-T01 Action framework | done | `actions/service.py`, typed tool catalog |
| S6-T02 Dry-run previews | done | `executable=false`, payload/preview DuckDB tables |
| S6-T03 HITL 核准與期限 | done | 獨立 approver、30 分鐘 expiration |
| S6-T04 Mock external adapter | done | persistent DuckDB effects、JSON artifacts |
| S6-T05 Idempotent execution | done | unique external key、replay returns same ref |
| S6-T06 Timeout／部分失敗重試 | done | retryable approved state、append-only attempts |
| S6-T07 頻率限制 | done | 同 segment 七天最多兩次 EDM |
| S6-T08 Audit reconstruction | done | task log、attempts、trace IDs |
| S6-T09 CLI/MCP/RBAC 整合 | done | public catalog names、safe CLI failures |

## 公開工具與行為

- `draft_retention_edm`：建立 EDM 草稿，沒有副作用。
- `send_edm`：只建立 EDM dry-run 與 `pending_approval` 任務，不寄送。
- `create_product_issue`：只建立 issue dry-run；同商品已有未結案任務時拒絕重複建立。
- `generate_report`：只建立 report preview，不寫出正式報告。
- `approve_task`：由另一位符合 action 規則的角色核准，預設 30 分鐘有效。
- `execute_task`：僅已核准、未過期、未超過頻率限制的任務可進入 mock adapter。

角色規則：Marketing 可建立 EDM；PM 或 Ops 可提出 product issue，須由 PM/Admin 核准；Ops、
PM、Marketing 可提出 report；Admin 為明確管理例外。Support 無 action 權限。

## 安全與失敗語意

- Gateway 在任何 action method 前強制可信身分與 RBAC。
- 執行前再次確認 actor 是原發起者或 Admin，避免可看全部任務的 Ops 越權造成副作用。
- 自批、錯誤 approver、未核准、過期與頻率超限都在 adapter 前拒絕，副作用數為 0。
- Timeout 不建立 side effect；partial failure 保存一筆 `partial` effect，重試完成同一筆，不新增。
- 任務執行成功後再次呼叫會回傳既有 task/external ref，不再呼叫 adapter。
- 相同 idempotency key 配不同 payload 會拒絕，不能把舊核准套用到新內容。
- CLI 對 action failure 只回傳 error type、固定安全訊息與 trace ID，不輸出內部錯誤細節。

## 人工驗證流程

先建立草稿：

```bash
uv run ecommerce-agent --as marketing_01 --tool draft_retention_edm \
  --arguments '{"segment":"Manual Segment","goal":"Win back","subject":"Preview","idempotency_key":"manual-draft-1"}'
```

將回傳的 draft task ID 填入 dry-run：

```bash
uv run ecommerce-agent --as marketing_01 --tool send_edm \
  --arguments '{"draft_id":"<DRAFT_TASK_ID>","recipient_count":25,"discount_pct":10,"idempotency_key":"manual-send-1"}'
```

確認 preview 為 `executable: false`、狀態為 `pending_approval`。接著以不同身分核准：

```bash
uv run ecommerce-agent --as marketing_approver --tool approve_task \
  --arguments '{"task_id":"<SEND_TASK_ID>"}'
```

最後由原發起者執行：

```bash
uv run ecommerce-agent --as marketing_01 --tool execute_task \
  --arguments '{"task_id":"<SEND_TASK_ID>"}'
```

重送最後一個指令應回傳相同 `external_ref`。可用以下方式確認 mock side effect 只有一筆：

```bash
uv run python -c '
import duckdb
con = duckdb.connect("runtime/mock_external.duckdb", read_only=True)
print(con.execute("SELECT idempotency_key, state FROM mock_external_effects").fetchall())
'
```

## 已知邊界

- 沒有真實 Email、Jira、Linear 或 Slack 整合；JSON artifact 只寫入 `runtime/mock_external/`。
- 頻率限制目前以 EDM `target_summary`（segment）計算，不是逐一 recipient contact frequency；未來
  若接真實 recipient reference，必須在 adapter 前加入逐客戶七天限制。
- Approval TTL 固定預設 30 分鐘；正式通道的互動按鈕與 SSO approver 尚未實作。
- `generate_report` 的工作流程內容與晨報組合屬 Sprint 7；Sprint 6 只驗證 action/HITL 邊界。

## 最終 deterministic gate

- Ruff：通過。
- Schema contract：45 張表、490,720 列、0 issue。
- Pytest：164 tests passed。
- Coverage：95.98%；mock adapters 100%、action service 99%、task store 99%、gateway 98%、
  tools 96%。
