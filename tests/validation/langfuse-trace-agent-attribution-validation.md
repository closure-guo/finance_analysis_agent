# 人工验证报告: langfuse-trace-agent-attribution

**日期**: 2026-08-13
**关联 delta**: openspec/changes/langfuse-trace-agent-attribution/
**E2E 门禁**: 不适用（纯后端 trace 埋点，非交互类变更，§2 判别）

## 验证范围

本 delta 覆盖 trace-observability 规范的 5 项新增 Requirement：
1. LLM generation 按子 agent 归因（agent 命名）
2. agent 名缺省时向后兼容（缺省退化 `litellm:{model}`）
3. generation 携带过滤 metadata（agent / session_id / stock_code）
4. 观测改动对业务透明（Langfuse 未配置零影响、不改 LLM 内容）
5. trace 记录会话内容（根 span output）——根 span 退出前写 agent 产出，trace/session 级可见

## 单元测试结果

全量后端回归：`uv run pytest tests/ --ignore=tests/e2e -m "not live" -q`
- 结果：**734 passed, 3 deselected, 0 failed**（基线 content-fidelity 为 725 项，本 delta 新增 9 项——agent 命名/metadata 7 项 + 根 span output 2 项（tests/test_trace_output.py），全部通过）
- 2 个 @live 用例（`tests/test_trace_content_live.py`）被 `-m "not live"` 排除（离线环境需真实 LLM，预期跳过）；全量含 @live 时基线为 735 passed + 2 @live 失败，二者为已知离线离线失败，非本 delta 引入
- Lint：`uv run ruff check src/ tests/` → 0 错误；`uv run ruff format --check src/ tests/` → 202 文件 clean
- 类型：`uv run mypy src/` → 75 errors in 19 files，与基线 commit（70bbe19，Task 7 改动前）去行号后逐条对比 **完全一致，无新增错误**（对比方法：两侧输出均 `sed 's/:[0-9]*: error:/: error:/'` 去行号后 `diff`，结果 identical）

## 验证结果

| Requirement | 预期行为 | 单测锁定 | 实跑对账（Langfuse UI） |
|---|---|---|---|
| agent 命名 | 管线节点 LLM 调用经 `call_llm_streaming(node_name=...)` 触发时，generation name 为该 agent 名而非 `litellm:{model}` | ✅ `tests/test_llm_utils_metadata.py::test_call_llm_streaming_forwards_agent_and_stock`（node_name→agent+stock_code 透传）；`tests/test_llm.py::test_call_llm_named_by_agent`（call_llm 入口 name=="technical_analyst"）、`test_call_llm_stream_named_by_agent`（name=="trader"）、`test_call_llm_with_tools_named_by_agent`（name=="bull_debater"）；`tests/test_litellm_client.py::test_chat_stream_generation_named_by_agent`（harness name=="react_agent"） | ⬜ 待人工：`deep_analysis:{股票}` trace 下 generation `name` 显示 `technical_analyst`/`bull_debater`/`risk_judge`/`trader`/`fund_manager` 等子 agent 名，而非 `litellm:{model}`；`react_loop` trace 的 generation 显示 `react_agent` |
| 缺省退化 | 未传 agent（或空串）时 generation name 退化为 `litellm:{model}`，行为不回归 | ✅ `tests/test_llm.py::test_call_llm_default_name_without_agent`（未传 agent 时 name 以 `litellm:` 开头、metadata 无 agent 键）；三个 LLM 入口新参数均为可选默认 `""`，现有调用点零改动（由全量 734 项回归覆盖） | ⬜ 待人工：未接入 agent 归因的调用点（若有）在 Langfuse 仍显示 `litellm:{model}`，与改动前一致 |
| metadata | generation metadata 记录 `agent`/`session_id`/`stock_code`，可按维度过滤 | ✅ `tests/test_llm.py::test_call_llm_metadata_omits_missing_fields`（提供时 metadata 恰为 `{agent, session_id, stock_code}`；缺失时省略且不报错）；`tests/test_litellm_client.py::test_chat_stream_generation_named_by_agent`（metadata["agent"]=="react_agent"） | ⬜ 待人工：Langfuse 中 generation metadata 可见 `agent` 字段；管线节点 generation 可见 `stock_code`，且可按 agent / stock 过滤。注意：`session_id` 仅当调用方显式传入时才出现在 metadata；当前无任何调用方传入（管线 state 无 `session_id` 键），故管线 generation 上预期**不出现** `session_id`，对账时不得据此判失败 |
| 业务透明 | 观测埋点为纯观测层操作，不改 SSE 事件流 / API 响应 / LLM prompt 与输出；Langfuse 未配置或异常时不创建观测、不阻断业务 | ✅ 复用 content-fidelity 基线：`tests/test_span_business_invariant.py::test_span_transparent_to_sse_events`、`test_search_result_invariant_with_span_exception`；`tests/test_langfuse_tracing.py::test_span_creation_exception_degrades`、`test_update_current_span_swallows_exception`、`test_update_current_span_noop_when_unconfigured`；`tests/test_llm.py::test_call_llm_with_tools_degraded_noop_without_error`；本 delta 的 `test_call_llm_streaming_forwards_agent_and_stock` 亦断言 LLM 返回内容不变（result=="a"） | ⬜ 待人工：实跑期间 SSE 事件流与最终报告内容与埋点前一致，未出现 Langfuse 相关报错 |
| trace 记录会话内容（根 span output） | 管线根 span（`deep_analysis:{股票}`）与 ReAct `react_loop` span 退出前将 agent 产出写入 span output，使 Langfuse trace/session 层级直接可见 agent 输出而非仅有 user input | ✅ `tests/test_trace_output.py::test_build_trace_output_summarizes_agent_outputs`（`_build_trace_output` 从 accumulated 构建摘要：stock/最终报告摘要截断≤600 字符/analyst 摘要/决策字段）、`test_stream_graph_exposes_root_obs_via_sink`（`_stream_graph` 经 `root_obs_sink` 透传根 obs 句柄供事件循环侧写 output）；`tests/test_deep_trace_root.py`（root span 建立/session 传播/无 Langfuse 不崩——根 span 生命周期）；`tests/test_react_loop.py`（ReAct 循环事件流回归：ANSWER 追踪路径在 `stream_agent_to_sse` 的退出写 output 逻辑所在流程） | ⬜ 待人工（post-merge Langfuse UI）：`deep_analysis:{股票}` 根 span 的 **output 非 null**，含管线产出摘要（stock_code/stock_name/final_report_summary/analyst_reports/决策字段）；`react_loop` span 的 **output 含 `answer`**（agent 最终回复）。对账步骤见下方「实跑对账说明」第 5 项 |

## 实跑对账说明（待人工项）

上表「实跑对账」列均为 **⬜ 待人工**，须在 **本分支合并至 main 之后** 人工执行（不可在本 worktree 完成）：

- 后端 docker 容器读取的是 main 工作区代码，本分支改动未合入 main 前，docker 后端不会加载 agent 命名逻辑，对账结果无意义。
- 步骤：`vite dev` + docker 后端启动后跑一次深度分析（如 `300308`），打开 Langfuse `localhost:3000`，核对：
  1. `deep_analysis:{股票}` trace 下 generation `name` 显示子 agent 名（`technical_analyst`/`bull_debater`/`risk_judge`/`trader`/`fund_manager`）而非 `litellm:{model}`；
  2. `react_loop` trace 的 generation 显示 `react_agent`；
  3. generation metadata 含 `agent`，管线节点 generation 含 `stock_code`；`session_id` 仅当调用方显式传入时才出现——当前无调用方传入，管线 generation 预期无 `session_id`，不视为失败；
  4. 报表/SSE 输出与埋点前一致（业务透明）。
  5. `deep_analysis:{股票}` trace 详情页根 span 的 **output 非 null**：应含 `stock_code`/`stock_name`/`final_report_summary`（最终报告摘要）/`analyst_reports`（各分析师摘要）/决策字段（`trader_plan`/`final_trade_decision`/`fund_manager_decision`）；`react_loop` span 的 **output 含 `answer`**（agent 最终回复）——trace/session 列表不再只有 user input。

## 结论

[x] 单测层全部锁定（734 passed；ruff 0 错误；mypy 与基线一致无新增）
[ ] 全部通过，可 archive —— 待实跑对账 5 项人工确认后勾选

后端观测埋点逻辑（agent 命名、缺省退化、metadata 挂载、Langfuse 故障不阻断、业务透明、根 span output 写 agent 产出）已由 734 项单测全绿 + ruff + mypy 无新增错误锁定。剩余 5 项实跑对账为「真实 Docker 后端 + Langfuse UI」的人工确认，依赖本分支合并至 main 后执行；完成后更新本报告并勾选上方结论方可 archive。
