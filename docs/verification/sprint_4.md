# Sprint 4 Verification Report

日期：2026-11-05

## 任務結果

| Task | 狀態 | 產物／證據 |
|---|---|---|
| S4-T01 來源 manifest 與角色 metadata | done | `configs/rag_sources.yaml` |
| S4-T02 Markdown ingestion 與 heading chunk | done | `rag/store.py` |
| S4-T03 DuckDB 可重建索引 | done | deterministic fingerprint/rebuild tests |
| S4-T04 角色過濾 retrieval | done | SQL pre-filter、越權相似文件測試 |
| S4-T05 top-k lexical ranking | done | 10-case known-answer suite |
| S4-T06 可定位引用 | done | path、版本、heading、line range |
| S4-T07 忠實度與空證據規則 | done | tool notice、answer prompt、empty-result tests |
| S4-T08 CLI/MCP 整合 | done | `search_knowledge` typed tool |
| S4-T09 文件與完整 gate | done | README、traceability、`verify_all.sh` |

## 架構與安全

- 索引只使用 `runtime/knowledge.duckdb`，不使用 SQLite，也不需要 embedding/LLM API。
- `rag_documents` 保存 source path、版本、標題、allowed roles 與 content hash；`rag_chunks` 保存
  deterministic chunk ID、heading、行號、內容與 lexical terms。
- 角色過濾在 DuckDB SQL 查詢階段完成，再進行相似度評分，因此未授權 chunk 不會進入候選集。
- 文件內容一律視為證據而非指令；工具 notice 與 Agent answer prompt 都要求逐項引用 supplied
  citation，空結果必須說明找不到授權證據。
- 索引重建會先讀取並驗證所有來源，再用 transaction 置換；來源遺失不會摧毀既有索引。

## 評測結果

- 已知答案 fixture：10/10 在 top-3 命中，100%，高於 90% 門檻。
- Support 對 Admin-only 高相似文件：0 筆；Admin 同查詢正確命中。
- Citation 包含 source version、heading context 與 `path#Lx-Ly`。
- 無證據 fixture 回傳空陣列與禁止補寫 notice。

## 最終 deterministic gate

- Ruff：通過。
- Schema contract：45 張表、490,720 列、0 issue。
- Pytest：97 tests passed。
- Coverage：94.00%；RAG store 97%、Query tools 96%、gateway 95%。

## Graphify 架構盤點

本次以 code-only AST 索引盤點 `src/`，AST 不使用 LLM API。實作前圖為 200 nodes、495 edges、
16 communities，更新後為 220 nodes、558 edges、18 communities。初始診斷發現 70 個 dangling
endpoints 與 6 個 self-loops，屬 graph extractor 對 import／參照節點的結構警告；本次只把圖作為
整合點輔助，不把它當安全或測試證據。自動 community 命名會呼叫外部 CLI，已主動中止。

## Sprint 5 前置條件

- 規則型輸入護欄需涵蓋 injection、jailbreak、冒充角色、惡意 SQL 與超長輸入。
- 輸出護欄需處理 Email、姓名、電話、user ID／hash 及未授權承諾。
- 間接注入 fixture 必須證明文件／評論內容不能改變授權或觸發動作。
