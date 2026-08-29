# Tasks: migrate-off-legacy-llm-shim

参考：`specs/llm-provider-gateway/spec.md`（行为契约）。测试按 TDD「先红后绿」。

## 1. 迁移非核心调用方（call_llm → complete_text）

- [x] 1.1 `src/finance_agent/nlp.py:77`（intent 解析）：改调 `gateway.complete_text`，复刻空文本回退 reasoning（读 metadata raw_reasoning）；TDD：失败测试（mock complete_text 断言调用参数含 purpose/max_tokens/trace.name）→ 实现 → 通过
- [x] 1.2 `src/finance_agent/react_agent.py:369,432`（stock 解析，quick=True → purpose="quick"）：同上模式；TDD 覆盖 quick 档位
- [x] 1.3 `src/finance_agent/events/web_fetcher.py:135`（事件提取，temperature=0.1）：同上；TDD 覆盖 temperature 透传
- [x] 1.4 `src/finance_agent/nodes/report.py:144`（focus 摘要，quick=True）：同上

## 2. 迁移核心流式入口（call_llm_stream → complete_stream）

- [x] 2.1 `src/finance_agent/nodes/_llm_utils.py:201` `call_llm_streaming`：改调 `gateway.complete_stream`；复刻 `(kind,text)` 迭代协议 + error → typed error 还原；**32768 翻倍重试逻辑行为不变**。TDD：既有 test_llm.py 流式用例迁移后先红，复刻协议后绿；新增断言 error 事件还原错误类型与 thinking/answer 分流

## 3. 删除 legacy + 清理 re-export

- [x] 3.1 删除 `src/finance_agent/llm/legacy.py`；`__init__.py` 去掉 call_llm/call_llm_stream/call_llm_with_tools re-export（`get_profile_preset`/`list_presets`/`resolve_profile`/类型 re-export 保留）
- [x] 3.2 `tests/test_llm.py` 约 40 处 `from finance_agent.llm import ...` 改调 gateway 对应入口/API；既有断言（thinking 流、错误类型、空文本回退）语义保留
- [x] 3.3 TDD：新增失败测试——`from finance_agent.llm import call_llm` 必须 ImportError（红），确认后删除该测试文件残留 import（或保留为「断言已移除」的编译期检查）

## 4. 验证收尾

- [x] 4.1 全量后端测试：`uv run pytest tests/ -m "not live"`（重点回归 tests/llm/、tests/test_llm.py、管线节点测试不回归）
- [x] 4.2 `uv run ruff check` / `uv run mypy` 通过（新增/改动零告警）
- [x] 4.3 `grep -rn "from finance_agent.llm import call_llm\|call_llm_stream\|call_llm_with_tools" src/` 零命中
- [x] 4.4 `openspec validate migrate-off-legacy-llm-shim` 通过；`openspec validate --strict` 无回归
- [x] 4.5 提交