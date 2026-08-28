# Tasks: agent-trace-content-fidelity

> 粗粒度验收 checklist。细粒度 TDD 步骤由 Step 2 writing-plans 产出至 `docs/superpowers/plans/`，不在此处。

## 验收项

- [x] LLM generation output 含 `reasoning` 字段（@live 验证：thinking 模式下 Langfuse trace 可读完整推理链）
- [x] LLM generation output 含 `tool_calls` 结构化字段（工具调用决策可读，非仅 answer 文本）
- [x] LLM generation metadata 含 `prompt_name` + `prompt_version`（兑现 ADR-0015 第 24 行；本地兜底标 `"local"`）
- [x] AKShare 取数有 `data_source:akshare` 子 span，失败标 `level=ERROR`（incident 008 类可定位到具体子调用）
- [x] 解析降级（`parse_degraded`/`_sanitize_claims`）、重试（empty/text_only）、DSML 防御性解析在 span metadata 可见并标 level
- [x] 所有新埋点经 `open_span`/`update_current_span` 优雅降级，Langfuse 异常不阻断业务（测试覆盖）
- [x] `uv run pytest` 全过、`uv run ruff check` 无错误、`uv run mypy`（基线对比）无新增错误
- [x] `openspec validate agent-trace-content-fidelity --strict` 通过
- [x] 人工验证报告落 `tests/validation/`（对照 incident 008 确认子 span 定位；对照 thinking mode 确认 reasoning 可读）
