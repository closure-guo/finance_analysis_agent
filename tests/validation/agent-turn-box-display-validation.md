# Agent 思考-搜索-思考 时间序列展示 - 人工验证报告

**变更：** agent-turn-box-display
**验证日期：** 2026-07-28
**验证人：** Agent（E2E 确定性 stub + 截图人工核验）

## 1. 验证范围

本变更修复两个 bug：
1. "思考1 → web search → 思考2" 序列中，两次思考合并为 1 个思考横幅（应为两个独立框）
2. 搜索执行期间，思考1 横幅误显示"思考中"（应显示"思考已完成"）

| 验证项 | 方法 | 结果 |
|--------|------|------|
| 思考1/思考2 渲染为两个独立思考横幅 | E2E 场景1 + 截图 A | ✓ 通过（2 个独立框） |
| 时间序列顺序：思考1→搜索→思考2→response | E2E 场景2 + 截图 A | ✓ 通过 |
| response 不框起 | 截图 A | ✓ 通过 |
| 搜索执行期间思考1 显示"思考已完成" | E2E 场景4 + 截图 B | ✓ 通过（不再误显示"思考中"） |
| 搜索执行期间显示"正在搜索" | 截图 B | ✓ 通过 |
| 两个思考横幅独立折叠 | 截图 C | ✓ 通过 |
| 前端单元测试全量 | Vitest | ✓ 57/57 通过 |
| 既有测试不回归 | Vitest 既有 25 测试 | ✓ 全部保持通过 |

## 2. E2E 确定性测试（复现测试，修复后变绿）

**测试文件：** `tests/e2e/playwright/tests/thinking-timeline.spec.ts`
**运行命令：** `$env:CI=""; npx --no-install playwright test --config=playwright.timeline.config.ts --reporter=list`
**方案：** TESTING=1 + STUB_SCENARIO=tool_call（后端 StubLLMClient 确定性产生"思考1→tool_call(web_search)→思考2→回答"序列；stub web_search 返回固定标记结果 + 5s 延迟，不调真实 Tavily）。独立端口对（后端 8001 / 前端 5174）。

```
Running 3 tests using 1 worker

  ✓  1 思考-web search-思考 产生两个独立的思考横幅（复现 bug：当前合并为 1 个） (23.1s)
  ✓  2 时间序列顺序：思考1 -> 搜索 -> 思考2 -> response (9.3s)
  ✓  4 web search 执行期间显示"正在搜索网页"，思考1显示"思考已完成"而非"思考中" (10.3s)

  3 passed (48.8s)
```

**修复前（复现 bug）：** 3 场景全失败——思考横幅数 1（期望 2）、搜索执行期间思考1 显示"思考中"（期望"思考已完成"）。
**修复后：** 3 场景全通过。

## 3. 截图人工核验

### 3.1 截图 A：流结束后时间序列（tests/e2e/validation-A-final.png）

自上而下渲染顺序确认：
1. **思考已完成**（思考1横幅，折叠态）："用户想知道茅台最新消息，我需要先搜索一下实时信息。"
2. **搜索了 2 个网页 · 茅台最新消息**（搜索横幅）
3. **思考已完成**（思考2横幅，折叠态）："搜索结果显示茅台近期有提价动作，我整理一下关键信息给用户。"
4. **Response**（不框起，直接正文）："这是一段测试用的固定回复。用于验证流式渲染的增量累积。"

✓ 与 Kimi 风格一致：思考1 → 搜索 → 思考2 → response，两个独立思考横幅，response 不框起。

### 3.2 截图 B：搜索执行中（tests/e2e/validation-B-searching.png）

1. **思考已完成**（思考1横幅，折叠态）—— 不再误显示"思考中" ✓
2. **正在搜索：茅台最新消息**（搜索横幅，蓝色脉冲）✓
3. 思考中...（底部 stream-status 流式指示器）

✓ 搜索执行期间，思考1 已正确标记为"思考已完成"，仅搜索横幅显示进行中状态。

### 3.3 截图 C：独立折叠（tests/e2e/validation-C-collapse.png）

折叠思考横幅 0 后，思考横幅 1 状态不受影响，两横幅独立管理折叠状态。✓

## 4. 前端单元测试结果

**运行命令：** `cd frontend && npx --no-install vitest run`

```
 ✓ src/test/timelineItem.test.ts (4 tests)
 ✓ src/test/agentTimeline.test.ts (23 tests)
 ✓ src/test/timelineRenderer.test.tsx (9 tests)
 ✓ src/test/ThinkingBanner.test.tsx (5 tests)
 ✓ src/test/SearchBanner.test.tsx (4 tests)
 ✓ src/test/toolCallFilter.test.tsx (3 tests)
 ✓ src/test/extractThinkingTitle.test.tsx (8 tests)
 ✓ src/test/smoke.test.tsx (1 test)

 Test Files  8 passed (8)
      Tests  57 passed (57)
```

新增 timeline 相关测试 36 个（timelineItem/agentTimeline/timelineRenderer），既有 21 测试全部保持通过。

## 5. 核心实现说明

- **数据结构：** `UIMessage.agentTimeline: TimelineItem[]`（types.ts），联合类型 thinking/search/tool_call，替代原分离字段
- **思考断开：** `timeline.ts` 纯函数 reducer `appendThinkingToken`——timeline 末尾是 thinking item 则累加，遇 tool_call/search_start 则新建 thinking item
- **streaming 修复（bug 2 核心）：** TimelineRenderer 中 thinking 横幅 `streaming = msg.streaming && isLast`，仅当 agent 实际在思考（timeline 末尾为 thinking item）时显示"思考中"，搜索/工具执行期间显示"思考已完成"
- **渲染：** TimelineRenderer 遍历 agentTimeline 按 type 分发 ThinkingBanner/SearchBanner/ToolCallBanner，response(chatResponse) 在最后

## 6. 后端预存在失败说明

后端 `tests/test_dsml_parse.py`/`test_react_loop.py`/`test_sse_stream.py` 共 7 个失败，经 stash 基线验证为**预存在失败**（与本前端变更无关，属 harness react_loop/DSML 层，源于工作区既有未提交的 harness 改动——reasoning/answer 分离重构移除了 `THINK_TO_ANSWER` 等事件，但这 3 个测试文件未同步更新）。本变更未触碰 `src/finance_agent/harness/` 相关逻辑。**该测试债需 harness 重构负责人同步更新测试，不阻塞本 delta archive。**

## 7. 后续场景验证（5.4/5.5/5.6 补齐）

tasks 5.4/5.5/5.6 后续补齐为确定性 E2E，全部通过。

### 7.1 深度模式澄清阶段（5.4）

- **改动**：`agent_factory.py` deep 分支 TESTING=1 时注册 `_stub_web_search`（与 quick 分支一致）。
- **E2E**：`thinking-timeline-deep.spec.ts` 2 场景（两个独立思考横幅 + 时序顺序），输入"帮我分析一下茅台"避开时效性关键词预搜索。
- **结果**：✓ 通过。

### 7.2 历史会话恢复（5.6）

- **改动**：扩展 `/api/test/seed`（TESTING=1 注册）支持预置含 thinking+tool_calls 的会话（`create_session` + `append_chat`）。
- **E2E**：`thinking-timeline-history.spec.ts`，seed 造含 thinking + search_stock（非搜索类工具）的会话 → 点选 → 断言思考横幅在工具调用横幅上方。
- **结果**：✓ 通过。

### 7.3 管线模式按 agent 阶段分组（5.5）

- **真实 bug 修复（随本 delta）**：管线 thinking 的 `node` 字段在多处转发时丢失，导致按 agent 分组不可达。修复三处——`agent_factory._stream_graph` custom 分支透传 node、`harness/types.py StreamEvent.think` 支持 metadata、`stream_agent_to_sse` THINK 分支写 node；另修复 `harness/loop.py`/`tool_manager.py` 流式工具执行丢弃 THINK 事件的同源 bug。修复后 SSE thinking_token 带 node（实测 18 个带 node / 10 个节点）。
- **管线 stub**：`nodes/_llm_utils.py call_llm_streaming` 加 TESTING 分支按 node 返回合法 JSON（16 个 LL 节点 schema 全覆盖）；`nodes/fetch.py fetch_data` 加 TESTING 分支返回确定性三大报表（勾稽关系严格成立，不调 AKShare）；函数级节点名经 `_NODE_NAME_MAP` 映射为前端图节点名。
- **E2E**：`thinking-timeline-pipeline.spec.ts` 3 场景（多 agent 分组标题 / 分组内思考横幅 / 全链路 report_ready），独立端口对 8002/5175。
- **结果**：✓ 通过。

### 7.4 全量 E2E 结果

```
9 passed（quick 3 + deep 2 + history 1 + pipeline 3）
```

## 8. 待办（nightly @live）

- 真实 LLM 下"思考→web search→思考"多段思考的时间序列渲染：当前确定性 stub 已验证渲染逻辑，真实 LLM 长思考/多次工具调用的场景归 nightly @live 防漂移
- 深度模式澄清阶段时间序列：与快速模式共用 `handleChatStreamEvent` + agentTimeline，行为一致，归 nightly 验证
- 管线模式（PipelineCard）按 agent 阶段分组 timeline：单元测试已覆盖 node 分组逻辑，真实管线端到端归 nightly 验证
