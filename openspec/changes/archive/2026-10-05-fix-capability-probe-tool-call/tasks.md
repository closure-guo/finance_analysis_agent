# Tasks: fix-capability-probe-tool-call

- [x] tool_call 两级探测（auto+明确指令 → forced 兜底）落地 `run_live_probes`，warnings 区分 `tool_call_probe_error`（端点拒绝）/`tool_auto_no_call_forced_ok`（强制级才通过），单元测试覆盖两级命中/两级全拒/第一级直接命中三条路径
- [x] `tool_followup` 复用命中级的 tool_calls 构造回传，`tool_call=false` 时不执行（现有级联语义回归测试覆盖）
- [x] `/api/llm-config/test` 对未知 provider 前缀返回结构化失败（`errorType=model_prefix_invalid`，无 500 裸栈），单元测试覆盖
- [x] 前端 `buildModelWithPrefix` 白名单回退（`kimi` 等未知前缀 → `openai/`，deepseek 等已知前缀不变），单元测试覆盖
- [x] 能力矩阵「未测」中性态（tool_call=false 时 tool_followup 显示未测而非不支持）+ warnings 机器码 → 人话映射（含未知码透传），单元测试覆盖
- [x] 后端 `ruff check`（全过）+ `mypy`（零新增错误，api.py 存量 5 错误与 main 同款、CI 容忍）+ 相关 pytest 全绿（tests/llm/ + tests/test_api_llm_config.py = 320 passed）；前端 `npm test` 全绿（643 passed，含 tsc 类型检查干净）
- [x] E2E 门禁通过（交互类变更）：非 @live 套件 23 passed；eval-ops-console 2 红经 main 基线对照确认为**本地环境存量态**（main 同 spec 挂 4 个，非本分支回归，CI 干净环境以 CI 为准）；@live 7 例属 nightly 职责（本地对 stub 后端按设计必挂）。本地门禁注意：docker 生产栈占用 8000/5173 时 playwright `reuseExistingServer` 会误测 docker 旧代码，须先停容器
- [x] 人工验证报告落 `tests/validation/`（含真实 provider 复测矩阵截图/记录）——复测记录落 tests/validation/2026-10-05-fix-capability-probe-tool-call-retest.md：真实 Kimi 端点五项能力 5/5 ✓（含 tool_call，无需强制回退）、模型发现 4 模型、非法前缀结构化错误；未测态 UI 由已合并前端三态单测覆盖（真实端点无 tool_call=false 样本可造）
