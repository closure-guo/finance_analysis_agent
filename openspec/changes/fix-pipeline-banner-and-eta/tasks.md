# Tasks: fix-pipeline-banner-and-eta

## 1. 后端：agent 路径补发 node_start

- [x] 1.1 编写失败测试：`tests/` 中新增测试，断言 agent 路径流式工具对每个图节点先产出 node_start（携带 node/layer/desc）再产出 node_complete，且同节点不重复 start
- [x] 1.2 修改 `src/finance_agent/agent_factory.py`：`_make_run_deep_analysis` 的 graph.stream 迭代中，节点 updates chunk 首次出现时先 yield node_start（用 started_nodes 集合去重）
- [x] 1.3 确认 `stream_agent_to_sse` 将 node_start 正确序列化为 SSE 事件（复用 fast path 已有序列化格式）
- [x] 1.4 回归测试 fast path 事件序列不变（node_start/node_complete 成对、顺序一致）—— `test_sse_stream.py` 等 339 用例通过，仅 2 个预存在失败（MockLLMClient 签名，与本改动无关，已 stash 验证）

## 2. 前端：思考横幅显式完成态

- [x] 2.1 编写失败测试：`frontend/src/test/agentTimeline.test.ts` 断言对话流中 tool_call/首个 chat_token/thinking_to_answer/chat_done/error 将末尾 thinking item 置 done=true（6 用例）+ 管线 node_complete/跨节点收口（4 用例）
- [x] 2.2 `frontend/src/types.ts`：thinking 类型 TimelineItem 增加 `done?: boolean` 字段
- [x] 2.3 `frontend/src/timeline.ts`：`applyChatStreamEvent` 在 tool_call、chat_token、thinking_to_answer、chat_done、error 分支将末尾未完成 thinking item 置 done=true（closeLastThinking/closeAllThinking）
- [x] 2.4 `frontend/src/timeline.ts`：`applyPipelineThinkingToken` 在收到新节点 thinking_token 时，将其他节点未完成 thinking item 置 done=true；新增 `applyPipelineNodeComplete` 将对应节点末尾 thinking item 置 done=true，App.tsx node_complete 分支接入
- [x] 2.5 `frontend/src/TimelineRenderer.tsx`：活动态判定改为 done=true 优先（`item.done === true ? false : streaming && isLast`）
- [x] 2.6 验证工具调用横幅在管线模式下仍由 tool_result 正确置 done（agentTimeline.test.ts tool_call 生命周期用例回归通过）

## 3. 前端：动态 ETA

- [x] 3.1 编写失败测试：`frontend/src/test/eta.test.ts`（16 用例：中位数初始预估、无历史默认 240s、线性收敛重估、max(0,...) 下限、localStorage 读写/淘汰/损坏回退、格式化）
- [x] 3.2 新增 `frontend/src/eta.ts`：历史中位数、进度收敛、耗时记录读写 localStorage（键 `financeAgent.pipelineDurations`，最多 10 条）
- [x] 3.3 `frontend/src/App.tsx`：PipelineCard 移除硬编码 `~90s`，接入 ETA 显示"已用时 M:SS · 预计剩余 ~M:SS"，每秒刷新；管线启动记录 startedAt，report_ready 时 recordDuration
- [x] 3.4 当前 running 节点所在阶段圆点下方显示已运行时长（由 currentNode 定位，每秒刷新）

## 4. 验证

- [x] 4.1 `uv run pytest` 后端测试全绿（339 通过；test_sse_stream 2 个失败为预存在问题，stash 验证与本改动无关）
- [x] 4.2 `cd frontend && npm test` 前端测试全绿（84 通过）
- [x] 4.3 `uv run ruff check` 全绿 / `uv run mypy` 无新增告警（2 个 agent_factory 告警为预存在，stash 验证）/ `npx tsc --noEmit` 无错
- [x] 4.4 E2E：新增 `tests/e2e/playwright/tests/pipeline-eta-banner.spec.ts`（4 用例：ETA 动态递增、node_start 驱动 running 态、思考横幅显式折叠、ETA 历史写入），timeline config 全套 13 用例通过（含既有回归）
- [x] 4.5 人工验证报告落 `tests/validation/pipeline-banner-eta-validation.md`：覆盖快速模式横幅关闭、深度分析全程横幅行为、Layer II 子节点进展可见、ETA 随进度变化
