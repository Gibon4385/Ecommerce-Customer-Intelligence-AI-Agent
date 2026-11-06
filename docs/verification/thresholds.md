# Verification Thresholds

使用者於 2026-11-05 確認以下門檻：

| 項目 | 門檻 |
|---|---:|
| 確定性測試 | 100% 通過 |
| 關鍵安全、越權、PII、未核准動作 | 100%，禁止 xfail |
| 整體 line coverage | ≥ 85% |
| auth/repository/tools/task-state | ≥ 95% line、≥ 90% branch |
| schema 宣告表資料契約 | 100% 涵蓋 |
| Golden Set 工具選擇與參數 | 各 ≥ 90% |
| 回答忠實度 | ≥ 95% |
| 關鍵禁止內容 | 0 違規 |
| RAG top-k 命中率 | ≥ 90% |
| red-team 攔截率 | ≥ 95% |
| 正常問題誤擋率 | ≤ 5% |
| LLM eval 回歸 | 不低於基線 3 個百分點；關鍵案例不得退步 |

效能在 Sprint 0 只記錄基線，尚不作 release gate。

