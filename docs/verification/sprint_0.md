# Sprint 0 Verification Report

日期：2026-11-05

## 完成項目

| Task | 結果 | 主要產物 |
|---|---|---|
| S0-T01 資料契約基線 | done | `data/schema.yml`, `contracts.py`, `data_quality.json` |
| S0-T02 canonical 與敏感路徑 | done | canonical schema rule、Raw deny tests |
| S0-T03 營運 Mart SQL | done | `warehouse/models/`, `data/ops_marts/` |
| S0-T04 固定種子模擬資料 | done | `generate_synthetic_ops.py`、reproducibility tests |
| S0-T05 Repository | done | strict CSV Mart Repository、contract tests |
| S0-T06 跨工具規則與文件 | done | `AGENTS.md`, `CLAUDE.md`, kickoff prompt、資料字典 |
| S0-T07 驗證與追溯 | done | thresholds、matrix、`verify_all.sh` |
| S0-T08 CLI 可行性 | done（設計確認） | Codex CLI 為 Sprint 1 首個 adapter；實作留 Sprint 1 |

## 重要決策與變更

- 營收只計 `completed` 訂單。
- 漏斗以 events 的 `purchase` 為轉換終點，不宣稱存在 checkout event。
- 缺少成本來源，因此兩張 Mart 的 `gross_profit` 為 NULL。
- 僅接受小數部分為 0 的數值安全轉 integer。
- Raw reviews 的實際 `review_date` 是 timestamp，schema 已依實際資料修正。
- 非 canonical hashed-email 副本與 canonical 內容完全相同，已移出工作區至
  `/private/tmp/mart_lookalike_hashed_email.duplicate.csv`；可手動恢復，但不應載入。

## 驗證指令與結果

```bash
./scripts/verify_all.sh
```

完整入口依序執行 lint、營運 Mart 建置、固定種子資料產生、45 張表資料契約驗證及
deterministic tests。最終實測摘要：

- Ruff：通過。
- Schema contract：45 張表、490,720 列、0 issue。
- `mart_ops_daily_kpi`：911 列。
- `mart_ops_conversion_funnel`：10,079 列。
- `mart_ops_category_sales`：1,317 列。
- campaign：5 列；touch log：500 列；pipeline status：15 列。
- Pytest：25 tests passed。
- Coverage：88.84%，高於已確認的 85% 整體門檻；Repository 達 100%。

機器可讀資料品質結果：`reports/verification/data_quality.json`（由驗證入口重建）。

## 已知限制

- Sprint 0 尚未實作 MCP tools、RBAC、Agent、LLMClient 或 task state machine；依 Sprint
  規劃分別於後續 Sprint 完成。
- BigQuery adapter 為選配，尚未建立。
- 毛利沒有來源，因此不進行毛利對帳。
- LLM 層評測尚未進行，Golden Set 從 Sprint 2 開始。

## Sprint 1 前置條件

- 使用 Codex CLI 建立首個 `CliLLMClient` adapter。
- 查詢工具只能經 Repository 與工具授權骨架進入資料。
- tracing 必須從第一個 request/tool call 即存在。

