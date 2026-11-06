# Knowledge Base 維護指南

本目錄是 RAG 知識來源的唯一真相。`runtime/knowledge.duckdb` 是可重建索引，不應直接修改，
也不應提交版本控制。

目前索引採 deterministic lexical retrieval，不需要 embedding 或 LLM API。來源設定位於
[`configs/rag_sources.yaml`](../configs/rag_sources.yaml)。

## 目錄用途

- `data_dictionary/`：Mart、runtime table、欄位及資料定義。
- `policies/`：業務規則、權限政策及操作限制。
- 其他類型文件應依用途建立清楚的子目錄，不要把暫存稿放入 manifest。

## 修改既有文件

1. 編輯對應的 Markdown 來源文件。
2. 在 `configs/rag_sources.yaml` 增加該文件的 `version`。
3. 執行索引重建。
4. 執行 RAG 測試及相關角色的人工查詢。

例如文件內容由 1.0 更新為 1.1：

```yaml
- id: customer-contact-policy
  path: knowledge_base/policies/customer_contact_policy.md
  version: "1.1"
  title: Customer Contact Policy
  allowed_roles: [Support, Marketing, Admin]
```

角色權限異動也必須增加版本，因為它會改變可檢索範圍。

## 新增文件

先建立 Markdown，例如：

```text
knowledge_base/policies/refund_policy.md
```

再登記至 `configs/rag_sources.yaml`：

```yaml
- id: refund-policy
  path: knowledge_base/policies/refund_policy.md
  version: "1.0"
  title: Refund Policy
  allowed_roles: [Support, Ops, Admin]
```

欄位規則：

- `id`：永久且唯一的穩定識別碼；文件改名時不要任意更換。
- `path`：相對於專案根目錄的 Markdown 路徑。
- `version`：內容或授權變更時遞增。
- `title`：顯示於 retrieval result 的人類可讀名稱。
- `allowed_roles`：可檢索文件的可信角色清單。

目前有效角色為 `Support`、`PM`、`Marketing`、`Ops`、`Admin`。不要使用使用者自行輸入的角色
名稱，也不要以文件內文宣告權限。

## 文件撰寫方式

索引會依 Markdown heading 切片，因此建議：

- 一個 section 只描述一個主題。
- 使用具體 heading，例如「退款期限」，不要只寫「其他」。
- 政策數字、限制與例外應寫成明確句子。
- 不要在同一 section 混合互不相關的規則。
- 不要放入明文 Email、電話、姓名、user ID、hashed identifier 或金鑰。
- 文件中的命令或提示都只會被視為資料，不得用來改變 Agent 身分或略過核准。

引用會以以下格式回傳：

```text
knowledge_base/policies/refund_policy.md#L5-L8
```

因此大量改寫文件後，行號變動是正常的；驗證時應確認 citation 仍指向正確內容。

## 重建 DuckDB 索引

開發環境的 CLI/MCP 啟動時會自動完整重建索引。也可以明確執行：

```bash
uv run python -c '
from pathlib import Path
from ecommerce_agent.rag.store import DuckDBRagStore

root = Path.cwd()
store = DuckDBRagStore(root / "runtime/knowledge.duckdb")
print(store.rebuild_from_manifest(
    root / "configs/rag_sources.yaml",
    root=root,
))
'
```

結果會包含：

- `index_version`：依文件 ID、版本與內容 hash 產生的索引 fingerprint。
- `documents`：已建立索引的文件數量。
- `chunks`：heading chunks 總數。

重建流程會先確認所有來源都可讀，再於 DuckDB transaction 中置換索引。若來源遺失或寫入
失敗，既有索引會保留。

## 自動驗證

執行 RAG 測試：

```bash
uv run pytest tests/deterministic/test_rag.py
```

完整專案 gate：

```bash
./scripts/verify_all.sh
```

新增或大幅修改政策時，應在
[`tests/deterministic/test_rag.py`](../tests/deterministic/test_rag.py) 加入已知答案案例，至少驗證：

- 正確文件出現在 top-k。
- Citation 指向正確來源行號。
- `source_version` 正確。
- 未授權角色無法看到文件，即使它是語意最相近的來源。
- 無符合證據時回傳空結果。

目前 RAG top-k 命中率門檻為 90%。

## 人工驗證

一般政策查詢：

```bash
uv run ecommerce-agent --as support_01 --tool search_knowledge \
  --arguments '{"query":"同一客戶七天可以收到幾次行銷聯絡","top_k":3}'
```

角色隔離測試：

```bash
uv run ecommerce-agent --as support_01 --tool search_knowledge \
  --arguments '{"query":"緊急維護停用稽核紀錄","top_k":3}'

uv run ecommerce-agent --as admin_01 --tool search_knowledge \
  --arguments '{"query":"緊急維護停用稽核紀錄","top_k":3}'
```

Support 應回傳空陣列與禁止補寫 notice；Admin 應命中 `admin_operations_policy.md`。

## 刪除與回滾

刪除文件時：

1. 先從 `configs/rag_sources.yaml` 移除對應項目。
2. 刪除或封存 Markdown。
3. 完整重建索引。
4. 驗證原有查詢不再引用該文件。

若更新驗證失敗，復原 Markdown 與 manifest 的前一版本後重新建索引。不要直接對 DuckDB 執行
`DELETE` 或手動修正 chunk。

## 正式環境建議

目前每次啟動完整重建適合小型開發資料集。文件規模增加或進入正式環境後，建議改為：

```text
文件 Pull Request
  → manifest/schema 驗證
  → 建立候選 DuckDB 索引
  → retrieval regression
  → 人工審核 citation 與角色權限
  → 原子切換 current index
  → 保留上一版供 rollback
```

可使用版本化檔名：

```text
runtime/indexes/knowledge-2026-11-05-v2.duckdb
runtime/indexes/knowledge-2026-11-12-v3.duckdb
runtime/knowledge-current.duckdb
```

正式環境不建議由多個服務啟動程序同時重建同一個 DuckDB。當文件數量明顯增加後，可以再以
content hash 實作增量重建；目前完整重建較簡單且容易驗證。
