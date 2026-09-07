# Tasks: langfuse-trace-agent-attribution

## 1. 失败测试（先行，先红）

- [x] 1.1 `tests/` 新增测试：mock Langfuse 客户端，断言 `call_llm_stream` 传 `agent="technical_analyst"` 时 observation `name == "technical_analyst"`；不传 agent 时 `name == "litellm:{model}"`（向后兼容）
- [x] 1.2 同样命名断言覆盖 `call_llm` 与 `call_llm_with_tools` 两入口
- [x] 1.3 harness `litellm_client` 的 generation 以 agent 标签命名
- [x] 1.4 metadata 测试：上下文提供 session_id/stock_code 时，generation metadata 含 `agent`/`session_id`/`stock_code`；字段缺失时省略且不报错
- [x] 1.5 降级测试：`get_langfuse()` 返回 None 时不创建 observation、业务正常

## 2. 实现

- [x] 2.1 `call_llm_stream` / `call_llm` / `call_llm_with_tools` 增加可选 `agent: str = ""` 参数；observation 命名 `agent or f"litellm:{model}"`（复用 content-fidelity 已并入的 observation 封装模式）
- [x] 2.2 `nodes/_llm_utils.py` 的 `call_llm_streaming` 把 `node_name` 透传为 `call_llm_stream(..., agent=node_name)`
- [x] 2.3 其余 `call_llm` / `call_llm_with_tools` 调用点（`nodes/*`，约 6 处）按所在节点补 agent 名
- [x] 2.4 harness `litellm_client` generation 命名支持 agent 标签（缺省退化 `litellm:{model}`）
- [x] 2.5 generation metadata 写入 `agent`/`session_id`/`stock_code`（从节点 `state` 读取，缺失省略）

## 3. 验证与收尾

- [x] 3.1 `uv run pytest`、`uv run ruff check`、`uv run mypy`（基线对比）无新增错误；现有 `call_llm*` 测试不回归
- [ ] 3.2 实跑一次深度分析，Langfuse 对账：generation 以子 agent 命名、可按 agent/session/stock 过滤；人工验证报告落 `tests/validation/`

## 4. trace 级输出（根 span output = agent 产出）

- [x] 4.1 task 0 验证：Langfuse v4 `obs.update` 在 span 退出后跨线程/异步是否生效、flush 时序；据结果定 D4 落地方式（共享 sink + id 更新 或 退出前 output_provider 同步写）并回填 design.md
- [x] 4.2 失败测试：mock Langfuse，`deep_analysis` 根 span 完成时 output 含管线产出摘要（各 agent 产出 + 报告摘要）
- [x] 4.3 失败测试：`react_loop` span 退出时 output 含 agent 最终回复/总结
- [x] 4.4 实现：`_stream_graph` 捕获 `_root_obs`；管线完成后按 4.1 结论写 output（数据源 `accumulated`，摘要级）
- [x] 4.5 实现：`react_loop` 捕获 `_react_obs`，循环中追踪最终回复（TEXT/ANSWER 事件），退出前 `update(output=...)`
- [ ] 4.6 验证：pytest/ruff/mypy 全绿 + 实跑 Langfuse 对账（session/trace 级可见 agent 输出，不再 output=null）
