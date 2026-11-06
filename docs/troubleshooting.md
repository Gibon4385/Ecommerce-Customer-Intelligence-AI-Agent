# Troubleshooting

## uv 詢問使用者快取權限

這通常是 uv 嘗試使用全域 cache。可把 cache 固定在專案或暫存目錄：

```bash
UV_CACHE_DIR="$PWD/.uv-cache" uv sync --frozen --dev
```

CI 與 `verify_all.sh` 不需要 LLM API key。

## 缺少 data/9_raw

Raw demo exports 不進版本控制。從 staging 重建：

```bash
uv run python scripts/bootstrap_demo_raw.py
```

生成的 Email 使用 `example.invalid`，只供資料契約測試。Agent 仍不能讀 Raw。

## DuckDB lock

確認沒有另一個 CLI/MCP process 正在寫相同 runtime DB。停止舊 process 後重試；不要手動刪除
正在使用的 DB。測試會使用隔離的 temporary DuckDB。

## Action 無法執行

依序確認：

- Task 是 `approved`。
- 核准者不是發起者，且角色符合 action policy。
- 核准尚未超過 30 分鐘。
- 執行者是原發起者或 Admin。
- EDM segment 尚未達七天兩次上限。

使用 `get_task_status` 與 trace ID 查明 `error_type`；安全 CLI 不會輸出內部錯誤文字。

## RAG 找不到文件

確認 Markdown 已登記於 `configs/rag_sources.yaml`、版本已更新、角色在 `allowed_roles`，再參考
`knowledge_base/README.md` 重建 `runtime/knowledge.duckdb`。

## Cache 看似沒有命中

Role、data scope、System Prompt version 或 data version 任一不同都會 miss。Action/report 永遠 bypass；
含 PII 的 query 只能 exact hit，不允許 semantic hit。

## Codex CLI 自然語言失敗

Typed tools、工作流與 deterministic tests 都不依賴 Codex CLI。先用 `--tool` 或 `--workflow` 驗證
本地系統，再確認 `codex --version` 與登入狀態。Token／cost 在 CLI 無法可靠取得時會標示 unavailable。
