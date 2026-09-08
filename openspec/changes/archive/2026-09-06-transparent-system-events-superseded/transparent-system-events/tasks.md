## 1. rules/ 模块基础设施

- [ ] 1.1 编写 `rules/base.py` 的失败单元测试：验证 RuleEvent 数据结构（to_sse 转换、字段映射）覆盖 rule_triggered / rule_pre_search_start / rule_pre_search_complete / system_note 四类
- [ ] 1.2 实现 `src/finance_agent/rules/base.py`：定义 RuleEvent 数据类与 `to_sse()` 方法；若 `trace-observability` delta 已 archive 则 import `open_span`，否则内联 `start_as_current_observation` + nullcontext 降级（变量 camelCase、注释中文）

## 2. ① 时效性预搜索迁移（chat 流）

- [ ] 2.1 编写 `rules/temporal_search_rule.py` 的失败单元测试：覆盖「命中规则发三个事件」「不命中不发事件」「不再发伪 thinking_token/tool_call」三个场景（对应 spec 的 Rule-Triggered Event requirement）
- [ ] 2.2 实现 `rules/temporal_search_rule.py` 的 `maybe_presearch(query) -> AsyncIterator[RuleEvent]`：规则判断 + 发 rule_triggered + 开 rule_preprocessing span + 发 rule_pre_search_start + 开 pre_search span + 调用 web_search 公共函数 + 发 rule_pre_search_complete
- [ ] 2.3 将 [api.py:1208-1260](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L1208-L1260) 的 ① 冒充逻辑替换为调用 `temporal_search_rule.maybe_presearch()`，api.py 只转发 RuleEvent 为 SSE；若 `_web_search` 是 agent_factory 内部函数，提取为 [web_search.py](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/web_search.py) 公共函数供规则层 import

## 3. ②③ 系统提示迁移（analyze 流）

- [ ] 3.1 编写 `rules/system_notes.py` 的失败单元测试：覆盖「node_start 后发 system_note(kind=node_progress)」「node_complete 后发 system_note(kind=node_summary)」「不再发伪 thinking_token」三个场景（对应 spec 的 System Note Event requirement）
- [ ] 3.2 实现 `rules/system_notes.py` 的 `build_node_progress(node, desc)` 与 `build_node_summary(node, summary)`：返回 SystemNoteEvent（含 type/kind/node/text 字段）
- [ ] 3.3 将 [api.py:780-784](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L780-L784)（②）与 [api.py:822-826](file:///d:/WorkSpace/finance_analysis_agent/src/finance_agent/api.py#L822-L826)（③）的伪 thinking_token 替换为调用 `system_notes.build_node_progress` / `build_node_summary`，api.py 转发为 SSE

## 4. 规则层 Langfuse span

- [ ] 4.1 编写规则层 span 的失败单元测试：mock Langfuse，验证规则命中时创建 rule_preprocessing span + pre_search 子 span、input 含 rule/reason/query、未命中时不创建 span（对应 spec 的 Rule Layer Langfuse Span requirement）
- [ ] 4.2 在 `rules/temporal_search_rule.py` 用 `open_span`（或内联）包裹规则判断与预搜索，创建 `rule_preprocessing` 与 `pre_search` span，记录 input/output

## 5. 前端事件类型与 UI 处理

- [ ] 5.1 在 [frontend/src/types.ts](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/types.ts) 新增 `RuleTriggeredEvent` / `RulePreSearchStartEvent` / `RulePreSearchCompleteEvent` / `SystemNoteEvent` 类型，加入 SSEEvent 联合类型
- [ ] 5.2 编写前端失败测试：验证收到 rule_triggered/rule_pre_search_* 时显示系统预处理指示、不写入 thinking/tool_call item（对应 spec 的 Rule-Triggered Event Handling requirement）
- [ ] 5.3 编写前端失败测试：验证收到 system_note 时渲染系统提示、不写入 thinking item、与真实 thinking_token 分层展示（对应 spec 的 System Note Event Handling requirement）
- [ ] 5.4 在 [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) 的 `handleChatStreamEvent` 新增 `rule_triggered` / `rule_pre_search_*` / `system_note` 处理分支：规则事件显示系统预处理指示，system_note 渲染为系统提示（区别于 ThinkingBanner）

## 6. 回归测试（移除冒充后行为不变）

- [ ] 6.1 编写回归测试：验证 chat 流不再收到伪 thinking_token/tool_call（原 ① 冒充点），真实 LLM thinking_token/chat_token 流不受影响
- [ ] 6.2 编写回归测试：验证 analyze 流管线 UI 的 ThinkingBanner 只展示真实 LLM 思考，系统提示由 system_note 承载，`extractThinkingTitle` 不再处理冒充 token
- [ ] 6.3 编写回归测试：验证 ②delta（enable-deepseek-thinking-mode）的 thinking_token 净化逻辑与本 delta 的「不再发伪 thinking_token」方向一致，两者互补不矛盾

## 7. 质量门禁与人工验证

- [ ] 7.1 `uv run pytest` 全过，`uv run ruff check` 无错误，`uv run mypy` 无错误；前端 `cd frontend && npm test` 全过
- [ ] 7.2 E2E 测试（tests/e2e/）：通过前端模拟用户输入触发含时效关键词的 chat + 触发深度分析，验证前端正确渲染 rule_triggered/system_note 事件，且 ThinkingBanner 只展示真实思考（E2E 禁止 mock 被测系统，LLM 可用 TESTING=1 stub）
- [ ] 7.3 在 tests/scripts/ 编写手动验证脚本：触发 chat（含时效关键词）+ analyze，拉取 Langfuse trace，断言 trace 含 rule_preprocessing/pre_search span
- [ ] 7.4 在 tests/validation/ 落人工验证报告：记录前端 UI 截图（系统预处理指示 / 系统提示 与 ThinkingBanner 分层展示）+ Langfuse trace 截图（规则层 span），确认「规则归规则、LLM 归 LLM」
