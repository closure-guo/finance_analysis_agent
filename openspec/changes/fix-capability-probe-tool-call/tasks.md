# Tasks: fix-capability-probe-tool-call

- [ ] tool_call 两级探测（auto+明确指令 → forced 兜底）落地 `run_live_probes`，warnings 区分 `tool_call_probe_error`（端点拒绝）/`tool_auto_no_call_forced_ok`（强制级才通过），单元测试覆盖两级命中/两级全拒/第一级直接命中三条路径
- [ ] `tool_followup` 复用命中级的 tool_calls 构造回传，`tool_call=false` 时不执行（现有级联语义回归测试覆盖）
- [ ] `/api/llm-config/test` 对未知 provider 前缀返回结构化失败（`errorType=model_prefix_invalid`，无 500 裸栈），单元测试覆盖
- [ ] 前端 `buildModelWithPrefix` 白名单回退（`kimi` 等未知前缀 → `openai/`，deepseek 等已知前缀不变），单元测试覆盖
- [ ] 能力矩阵「未测」中性态（tool_call=false 时 tool_followup 显示未测而非不支持）+ warnings 机器码 → 人话映射（含未知码透传），单元测试覆盖
- [ ] 后端 `ruff check` + `mypy` + 相关 pytest 全绿；前端 `npm test` 全绿
- [ ] E2E 门禁通过（交互类变更：`cd e2e && npx playwright test`）
- [ ] 人工验证报告落 `tests/validation/`（含真实 provider 复测矩阵截图/记录）
