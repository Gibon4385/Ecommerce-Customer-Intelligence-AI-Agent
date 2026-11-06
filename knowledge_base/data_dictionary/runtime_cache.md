# Runtime Response Cache

`runtime/response_cache.duckdb` 是可刪除重建的 Agent 回答快取，不屬於業務 Mart，也不提交版本
控制。Cache key 包含正規化問題、role、data scope、System Prompt version 與 data version。

`response_cache` 欄位：

| Column | Meaning |
|---|---|
| cache_key | 上述隔離欄位的 SHA-256 |
| question | 原始問題；敏感問題只能 exact match |
| term_json | deterministic lexical terms，供 semantic lookup |
| answer | 已通過 output guard 的回答 |
| role | 可信角色 |
| data_scope | 可信資料範圍 |
| prompt_version | System Prompt 版本 |
| data_version | Mart pipeline version |
| semantic_eligible | 是否允許 semantic cache 使用 |

Email、電話、user ID、64 位 hash 或具姓名 label 的問題／回答會令 `semantic_eligible=false`。
Action 與 report intent 完全不讀寫 response cache。
