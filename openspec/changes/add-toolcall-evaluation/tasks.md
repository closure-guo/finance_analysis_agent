# Tasks: add-toolcall-evaluation

## 1. 轨迹提取

- [x] 1.1 取证：工具执行未入 Langfuse → 配套生产埋点 _trace_tool（6 处工具注册包裹，
       span tool_call:<名> + 入参/耗时/metadata.tool_error，纯可观测性）
- [x] 1.2 失败测试先行：轨迹提取与合法集合断言（tests/evals/test_toolcall.py 15 例）
- [x] 1.3 从 Langfuse trace 提取工具调用序列（evals/toolcall/measure.extract_toolcalls，
       observation name=tool_call:* 前缀）

## 2. 评估维度

- [x] 2.1 工具选择（合法集合断言）/参数合法性（必填键，无 args 时跳过）/调用效率
       （连续重复）/失败恢复（error 后须换工具）四维评分
- [x] 2.2 金标样本集（fixtures 离线路径）：合法序列零违例、对抗样本四维违例全检出

## 3. 门禁

- [x] 3.1 金标 fixtures 为确定性门禁（回归阈值即零违例断言）；nightly @live 生产流量
       监控报告（tests/evals/test_toolcall_live.py，无 key 跳过）

## 4. 验证

- [x] 4.1 uv run pytest / ruff / mypy 全绿（埋点守卫测试 tests/nodes/test_trace_tool.py 4 例）
- [ ] 4.2 真实业务跑一次 quick 分析后核对 Langfuse 出现 tool_call:* span（人工，需真实 LLM）
