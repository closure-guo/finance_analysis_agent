# Tasks: langfuse-trace-agent-attribution

## 1. 失败测试（先行，先红）

- [ ] 1.1 `tests/` 新增测试：mock Langfuse 客户端，断言 `call_llm_stream` 传 `agent="technical_analyst"` 时 observation `name == "technical_analyst"`；不传 agent 时 `name == "litellm:{model}"`（向后兼容）
- [ ] 1.2 同样命名断言覆盖 `call_llm` 与 `call_llm_with_tools` 两入口
- [ ] 1.3 harness `litellm_client` 的 generation 以 agent 标签命名
- [ ] 1.4 metadata 测试：上下文提供 session_id/stock_code 时，generation metadata 含 `agent`/`session_id`/`stock_code`；字段缺失时省略且不报错
- [ ] 1.5 降级测试：`get_langfuse()` 返回 None 时不创建 observation、业务正常

## 2. 实现

- [ ] 2.1 `call_llm_stream` / `call_llm` / `call_llm_with_tools` 增加可选 `agent: str = ""` 参数；observation 命名 `agent or f"litellm:{model}"`（复用 content-fidelity 已并入的 observation 封装模式）
- [ ] 2.2 `nodes/_llm_utils.py` 的 `call_llm_streaming` 把 `node_name` 透传为 `call_llm_stream(..., agent=node_name)`
- [ ] 2.3 其余 `call_llm` / `call_llm_with_tools` 调用点（`nodes/*`，约 6 处）按所在节点补 agent 名
- [ ] 2.4 harness `litellm_client` generation 命名支持 agent 标签（缺省退化 `litellm:{model}`）
- [ ] 2.5 generation metadata 写入 `agent`/`session_id`/`stock_code`（从节点 `state` 读取，缺失省略）

## 3. 验证与收尾

- [ ] 3.1 `uv run pytest`、`uv run ruff check`、`uv run mypy` 全绿；现有 `call_llm*` 测试不回归
- [ ] 3.2 实跑一次深度分析，Langfuse 对账：generation 以子 agent 命名、可按 agent/session/stock 过滤；人工验证报告落 `tests/validation/`
