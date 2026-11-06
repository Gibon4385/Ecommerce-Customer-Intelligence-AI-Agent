# Sprint 3 Verification Report

日期：2026-11-05

## 任務結果

| Task | 狀態 | 產物／證據 |
|---|---|---|
| S3-T01 五角色 RBAC matrix | done | `configs/rbac.yaml`, `test_rbac_matrix.py` |
| S3-T02 角色化欄位遮罩 | done | gateway deny fields、跨角色 profile 測試 |
| S3-T03 單一 customer scope | done | Support batch identifier rejection |
| S3-T04 DuckDB task store | done | `tasks/store.py`, `agent_task_log.md` |
| S3-T05 任務狀態機 | done | 合法／非法 transition 測試 |
| S3-T06 核准與禁止自批 | done | requester/approver role tests |
| S3-T07 idempotency | done | 唯一鍵、相同重試、衝突測試 |
| S3-T08 trace persistence-boundary redaction | done | identifier/contact/hash tests |
| S3-T09 文件與完整 gate | done | README、traceability、`verify_all.sh` |

## 實作邊界

- Runtime persistence **只使用 DuckDB**；沒有 SQLite adapter、檔案或相依套件。
- 任務基本狀態機已完成；真正的 EDM／Issue 外部副作用、dry-run、過期核准和頻率限制保留至
  Sprint 6。
- 專案目前沒有應用層結果快取，因此不存在會保存未遮罩工具結果的 cache surface。未來加入
  cache 時必須以角色與 data scope 隔離，並在寫入前套用同一遮罩政策。
- `TIMESTAMP` 儲存 naive UTC，由應用程式統一產生，避免 DuckDB `TIMESTAMPTZ` 的額外時區套件
  依賴；資料字典明確標記 UTC。

## 安全驗證

- 五個角色都有完整工具 allow/deny 集合，且各有至少一個成功執行案例。
- 所有角色的資料表設定只允許 Mart 或 `agent_task_log`；Admin 的 `*` 是明確管理者例外。
- gateway 在工具執行前強制 role limit 與 Support single-customer scope。
- 工具結果依角色移除 denied fields；trace store 在最終持久化邊界遞迴遮罩，錯誤 trace 只保存
  exception type，不保存錯誤文字。
- Agent 成功 response trace 只保存 `answer_length`，不保存可能含敏感資料的回答全文。

## 最終 deterministic gate

- Ruff：通過。
- Schema contract：45 張表、490,720 列、0 issue。
- Pytest：80 tests passed。
- Coverage：93.10%；task store 96%、gateway 95%、trace 100%，符合核心模組門檻。
- Sprint 0 的 ops marts 重建與金額對帳持續通過。

## Sprint 4 前置條件

- RAG ingestion 必須保留文件版本、metadata、角色標籤與可重建性。
- Retrieval 必須在檢索前套用角色過濾，且引用可定位到來源。
- 未找到證據時明確說明，不以模型補寫政策或定義。
