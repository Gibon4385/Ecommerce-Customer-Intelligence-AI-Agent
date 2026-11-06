# Sprint 8 Verification Report

日期：2026-11-05

## 任務結果

| Task | 狀態 | 產物／證據 |
|---|---|---|
| S8-T01 Locked CI gate | done | `.github/workflows/ci.yml`, `uv.lock` |
| S8-T02 Ruff 與 mypy | done | `scripts/verify_all.sh` |
| S8-T03 Clean demo Raw bootstrap | done | `scripts/bootstrap_demo_raw.py` |
| S8-T04 Clean-runtime smoke | done | `scripts/verify_clean_runtime.py` |
| S8-T05 Machine-readable evidence | done | `reports/verification/` |
| S8-T06 三條作品集流程 | done | `scripts/run_portfolio_demos.py`, `docs/demos.md` |
| S8-T07 安裝與 troubleshooting 文件 | done | `README.md`, `docs/troubleshooting.md` |
| S8-T08 BigQuery parity | optional / not run | 尚未做 production adapter 決策 |

## Release gate 結果

本機以 `uv sync --frozen --dev && ./scripts/verify_all.sh` 完整執行：

- Ruff：通過。
- mypy：44 個 source files，0 issue。
- 資料契約：45 張表、490,720 列、0 issue。
- Deterministic tests：177 passed、0 failed、0 error、0 skipped。
- Coverage：96.07%，高於 85% 門檻。
- 三條 deterministic demo：通過。
- Clean-runtime smoke：通過。
- Release summary：`reports/verification/release_gate.json`，`ok=true`。

## 乾淨環境可重現性

`data/9_raw/` 不進版本控制。`bootstrap_demo_raw.py` 會在 Raw 不存在時由 committed staging
重建固定 demo row counts，Email 使用 `example.invalid`；不會把真實 PII 帶入驗證資料。
`verify_clean_runtime.py` 會建立隔離暫存目錄、不複製 Raw，接著重建 Raw、驗證 45 張表並啟動
DuckDB runtime 做 KPI smoke test。

目前專案目錄本身位於上層 repository 的 untracked 目錄，因此本輪沒有宣稱完成真正的全新
`git clone` 驗證；上述 isolated clean-runtime 是可在本機取得的等價應用層檢查。

## CI 邊界

GitHub Actions workflow 已建立，會執行 frozen install 與同一支 `verify_all.sh`，並在任何結果下
上傳 verification artifacts。本輪只驗證本機等價 gate；workflow 尚未 push 到 GitHub，因此沒有
宣稱 GitHub-hosted runner 已成功執行。

## BigQuery 選配項目

Runtime 與測試仍一律使用 DuckDB。因尚未決定正式 production adapter，BigQuery parity 本 Sprint
不執行，release summary 明確記錄 `not_run_no_production_decision`，不把它包裝成已通過。

## 人工驗證

```bash
uv sync --frozen --dev
./scripts/verify_all.sh
uv run python -m scripts.run_portfolio_demos
```

第一個命令驗證 lockfile 可安裝；第二個命令重跑完整 release gate；第三個命令可單獨查看三條
作品集流程的 JSON 結果。所有 external action 都使用 mock adapter，不會真的寄信或建立工單。
