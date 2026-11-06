# Requirement-Test Traceability Matrix

| ID | Requirement | Test IDs / evidence |
|---|---|---|
| DATA-001 | schema、欄位、PK、型別 | `DC-SCHEMA-*`, `DC-PK-*`, `DC-TYPE-*` |
| DATA-002 | hashed-email canonical only | `SEC-CANONICAL-*` |
| DATA-003 | NULL / N/A 正規化 | `REPO-NULL-*` |
| DATA-004 | abandoned IDs 解析 | `REPO-LIST-*` |
| DATA-005 | cohort 0～1 | `DQ-COHORT-*` |
| DATA-006 | priority 不排除 Monitor | `DQ-PRIORITY-*` |
| DATA-007 | estimated value rounding | `DQ-ESTIMATE-*` |
| OPS-001 | completed-only daily KPI | `OPS-KPI-*` |
| OPS-002 | event purchase funnel | `OPS-FUNNEL-*` |
| OPS-003 | category sales | `OPS-CATEGORY-*` |
| SYN-001 | 固定 seed | `SYN-REPRO-*` |
| SEC-001 | Raw denied | `SEC-RAW-*` |
| ARCH-001 | Repository contract | `REPO-CONTRACT-*` |
| TOOL-001 | Sprint 1 query tools 正常/空值/排序/limit/metadata | `test_query_tools.py` |
| AUTH-001 | trusted dev identity 與 tool gateway | `test_gateway_agent.py`, `test_identity_tracing_llm.py` |
| TRACE-001 | request/auth/tool/response trace 與基本 PII 遮罩 | `test_gateway_agent.py`, `test_identity_tracing_llm.py` |
| CLI-001 | CLI 成功/timeout/非零退出/非 JSON | `test_identity_tracing_llm.py`, `test_cli.py` |
| AGENT-001 | FakeLLM 單表工具流程、identity 不可由訊息覆寫 | `test_gateway_agent.py` |
| MCP-001 | typed tool schemas、stdio tool call、環境身分 | `test_mcp_server.py` |
| PROMPT-001 | 估計值、NULL、資料邊界、特徵翻譯、間接注入 | `test_prompts.py` |
| EVAL-001 | 30 題 Golden Set 結構與唯一 ID | `test_evaluation.py` |
| EVAL-002 | pass/fail、禁止內容否定語境、同義事實群組 | `test_evaluation.py` |
| EVAL-003 | 真實 Codex CLI baseline 與逐題證據 | `reports/verification/golden_v0_*.json` |
| AUTH-002 | 五角色工具、Mart、limit allow/deny matrix | `test_rbac_matrix.py` |
| AUTH-003 | Support single-customer scope | `test_rbac_matrix.py::test_support_single_customer_scope_rejects_batch_identifiers` |
| MASK-001 | 角色化欄位遮罩與 trace persistence-boundary redaction | `test_gateway_agent.py`, `test_identity_tracing_llm.py` |
| TASK-001 | DuckDB `agent_task_log` schema、角色可見範圍 | `test_task_store.py` |
| TASK-002 | 合法／非法狀態轉換與禁止自批 | `test_task_store.py` |
| TASK-003 | idempotency key 唯一與安全重試 | `test_task_store.py` |
| RAG-001 | 文件版本、metadata、chunk 與可重建性 | `test_rag.py::test_rebuild_is_deterministic_and_preserves_metadata` |
| RAG-002 | top-k 已知答案命中率 ≥ 90% | `test_rag.py::test_known_answer_top_k_hit_rate` |
| RAG-003 | 檢索前角色過濾、最相近越權文件不可見 | `test_rag.py::test_role_filter_happens_before_similarity_ranking` |
| RAG-004 | 引用可定位來源版本與行號 | `test_rag.py::test_retrieval_returns_locatable_citation_and_version` |
| RAG-005 | 無證據回空，不提供可補寫內容 | `test_rag.py::test_no_evidence_and_input_validation` |
| GUARD-IN-001 | prompt injection、jailbreak、冒充角色、惡意 SQL | `test_guardrails.py::test_input_guardrail_blocks_red_team_cases` |
| GUARD-IN-002 | 超長與空輸入 | `test_guardrails.py::test_input_guardrail_rejects_empty_and_oversized` |
| GUARD-IN-003 | 正常業務問題誤擋率 ≤ 5% | `test_guardrails.py::test_input_guardrail_allows_normal_business_questions` |
| GUARD-OUT-001 | Email、姓名、電話、user ID、hash 遮罩 | `test_guardrails.py::test_output_guardrail_redacts_pii` |
| GUARD-OUT-002 | 未核准折扣、補償及成效保證 | `test_guardrails.py::test_output_guardrail_blocks_commitments` |
| GUARD-OUT-003 | 安全否定語境不誤擋 | `test_guardrails.py::test_output_guardrail_allows_safety_negations` |
| GUARD-INDIRECT-001 | RAG 資料不能觸發第二次工具呼叫 | `test_guardrails.py::test_indirect_injection_cannot_trigger_second_tool_call` |
| ACTION-001 | 所有公開 action 先建立不可執行 dry-run | `test_actions.py`, `test_action_gateway.py` |
| ACTION-002 | 未核准、錯誤核准者、自批與錯誤執行者 | `test_actions.py::test_dry_run_is_non_executable_and_requires_independent_approval`, `test_actions.py::test_wrong_approver_and_wrong_executor_cannot_cause_side_effect` |
| ACTION-003 | 核准期限與過期阻擋 | `test_actions.py::test_expired_approval_is_rejected_before_adapter` |
| ACTION-004 | 外部副作用冪等與 payload conflict | `test_actions.py::test_success_and_replay_have_one_persistent_side_effect`, `test_actions.py::test_action_payload_idempotency_conflict_is_rejected` |
| ACTION-005 | timeout、部分失敗與安全重試 | `test_actions.py::test_retryable_adapter_failures_succeed_without_duplicate_effect` |
| ACTION-006 | EDM 七天頻率限制 | `test_actions.py::test_send_frequency_limit_is_two_per_segment_in_seven_days` |
| ACTION-007 | task、attempt 與 trace 可還原稽核 | `test_actions.py::test_report_preview_execute_and_audit_are_reconstructable` |
| WORKFLOW-001 | 晨報固定快照數字、引用、延遲提示與 report task | `test_daily_workflow.py` |
| ROUTE-001 | query/diagnosis/strategy/action/report intent 與低信心升級 | `test_routing_cache.py::test_router_classifies_intents_model_tiers_and_cache_policy` |
| ROUTE-002 | small/large client 實際選擇 | `test_routing_cache.py::test_router_selects_distinct_small_and_large_clients` |
| CACHE-001 | exact 與 semantic hit | `test_routing_cache.py::test_exact_semantic_and_context_isolation` |
| CACHE-002 | role、data scope、prompt/data version 隔離 | `test_routing_cache.py::test_exact_semantic_and_context_isolation` |
| CACHE-003 | PII 不進 semantic cache | `test_routing_cache.py::test_pii_is_never_semantic_cache_eligible` |
| CACHE-004 | action/report intent bypass cache | `test_routing_cache.py::test_action_requests_always_bypass_cache` |
| DOC-001 | 規則與轉接文件 | `DOC-RULES-*` |
| CI-001 | frozen install、lint、type check、deterministic release gate | `.github/workflows/ci.yml`, `scripts/verify_all.sh` |
| RELEASE-001 | JUnit、coverage、data contract 與 release summary 可機器讀取 | `reports/verification/pytest-junit.xml`, `coverage.json`, `data_quality.json`, `release_gate.json` |
| REPRO-001 | gitignored demo Raw 可重建，乾淨 runtime 可啟動 | `test_bootstrap_demo_raw.py`, `scripts/verify_clean_runtime.py` |
| DEMO-001 | 晨報、行銷留存、商品問題三條 deterministic 流程 | `scripts/run_portfolio_demos.py`, `docs/demos.md` |
| DOC-002 | 安裝、操作、常見問題與已知限制 | `README.md`, `docs/troubleshooting.md`, `docs/verification/sprint_8.md` |
| BQ-OPTIONAL | BigQuery parity 未有 production 決策時不阻擋 release，但必須明示未執行 | `reports/verification/release_gate.json` |

