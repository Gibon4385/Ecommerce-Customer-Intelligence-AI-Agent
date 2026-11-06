# Sprint 1 Verification Report

日期：2026-11-05

## 任務結果

| Task | 狀態 | 產物／證據 |
|---|---|---|
| S1-T01 Identity 與 CLI channel | done | `auth/identity.py`, `configs/dev_users.yaml` |
| S1-T02 基礎 tracing | done | `observability/tracing.py`, JSONL trace tests |
| S1-T03 工具授權入口 | done | `tools/gateway.py`, `configs/rbac.yaml` |
| S1-T04 查詢工具 | done | `tools/query.py`, `tools/catalog.py` |
| S1-T05 LLMClient | done | Codex CLI + Fake adapters、timeout/error tests |
| S1-T06 最小 Agent 與 CLI | done | 單工具、雙工具、direct-tool CLI |
| S1-T07 MCP stdio server | done | 18 個 typed tools、可信環境身分 |
| S1-T08 文件與驗證 | done | README、AGENTS、traceability、完整測試 |

## 驗證範圍

- 所有第 7.1 節查詢意圖已有工具入口；`list_tasks` / `get_task_status` 明確回報 Sprint 3
  才建立持久化狀態機，沒有假造任務資料。
- `priority_score` 排序不排除 Monitor；所有工具回傳 `data_version`、`data_as_of` 與 notices。
- Gateway 在直接 CLI、Agent 與 MCP 路徑共用，不能繞過授權與 trace。
- 對話內容中的「我是 admin」不會改變 `--as` 或 MCP 環境注入的可信身分。
- `CliLLMClient` 測試涵蓋成功、timeout、非零退出、非 JSON、缺 final message 與 final 非 JSON。
- `FakeLLMClient` 驅動所有 deterministic agent tests，未呼叫真實模型。
- Trace 串接 request、authorization、tool result/error、response；輸入有基本 Email/電話遮罩。

## 驗證指令

```bash
./scripts/verify_all.sh
```

另有直接人工 smoke test：

```bash
uv run ecommerce-agent --as ops_01 --tool get_daily_kpi --arguments '{"limit": 2}'
```

最終實測結果：

- Ruff：通過。
- Schema contract：45 張表、490,720 列、0 issue。
- Pytest：53 tests passed。
- Coverage：92.54%；auth、identity、tracing、tool gateway 與 tool catalog 為 100%，query
  tools 為 95%。
- 6 張 ops marts 重建與 Sprint 0 對帳持續通過。

## 已知限制

- Sprint 1 的 RBAC 是工具級骨架；欄位遮罩、單一 user scope、完整 allow/deny matrix 在 Sprint 3。
- `check_audience_quality` 目前只做去重與排除 synthetic touch log 中出現過的使用者；正式頻率
  上限與高風險規則待後續 Sprint。
- task query 工具尚無持久化 task store，依規劃留到 Sprint 3。
- 自然語言 `--ask` 會使用已登入的 Codex CLI；Release deterministic tests 不呼叫真實 LLM。
- System Prompt v1 與 Golden Set 屬 Sprint 2，因此本 Sprint 不宣稱 LLM 回答品質已達門檻。
- 基本 trace 遮罩不是 Sprint 5 的完整 PII output guardrail。

## Sprint 2 前置條件

- 以現有 tool catalog 建立 System Prompt v1。
- 建立約 30 題 Golden Set，包含 expected tool/arguments/facts/forbidden content/role。
- LLM 層評測與 deterministic evaluator 分離，真實 CLI 結果不進必經 CI。

