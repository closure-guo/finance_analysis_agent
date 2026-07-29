# Tasks: persist-full-session-timeline

> 约定：TDD 红线——先写失败测试再实现。每任务完成后跑对应测试验证。
> 涉及文件：
> - 后端：`src/finance_agent/session_store.py`、`src/finance_agent/api.py`、`src/finance_agent/pipeline_runner.py`、`src/finance_agent/agent_factory.py`
> - 前端：`frontend/src/timeline.ts`、`frontend/src/types.ts`、`frontend/src/App.tsx`
> - 测试：后端 `tests/`、前端 `frontend/src/test/`、E2E `tests/e2e/`

## 1. 后端：会话存储层（session_store）

- [x] 1.1 init_db 迁移追加 `pipeline_timelines TEXT` 列（幂等 ALTER TABLE）
- [x] 1.2 新增 `update_pipeline_timelines(session_id, timelines)`：JSON 序列化写入列
- [x] 1.3 `get_session` 返回包含 `pipeline_timelines`（反序列化为 dict，非法/空回退 None）
- [x] 1.4 `append_chat` 新增可选参数 `agent_timeline`，写入条目 `agentTimeline` 字段
- [x] 1.5 单测：列迁移幂等、update/get pipeline_timelines、append_chat agentTimeline 往返

## 2. 后端：对话时序构建（api.py _ChatCollector）

- [x] 2.1 _ChatCollector.feed 维护 `agentTimeline: list[dict]`，实现与前端 applyChatStreamEvent 等价语义（thinking 片段断开/closeLastThinking/search/tool_call 收口/chat_done）
- [x] 2.2 finalize 传入 agentTimeline，append_chat 一并写入
- [x] 2.3 单测：同一事件序列，后端构建的 agentTimeline 与前端 applyChatStreamEvent 产出一致（共享夹具防漂移）

## 3. 后端：管线时序维护（pipeline_runner + agent_factory）

- [x] 3.1 pipeline_runner._run：处理 thinking_token/search/tool 事件时按 node 分组维护 timelines，节点事件节奏写 update_pipeline_timelines（与 snapshot 同步）
- [x] 3.2 agent_factory.run_deep_analysis 工具：ReAct 路径维护 thinking 的 pipeline_timelines（search/tool 归属不可达——管线节点 search/tool 事件不在该工具 custom/updates 流内，已加局限注释）
- [x] 3.3 单测：管线事件序列 -> pipeline_timelines 按节点分组正确、节点完成收口 thinking

## 4. 前端：时序序列化 + 类型（timeline.ts + types.ts）

- [x] 4.1 timeline.ts 新增 `deserializeTimeline`/`deserializeNodeTimelines`（防御非法输入回退空）
- [x] 4.2 types.ts：ChatHistoryEntry 新增 `agentTimeline?: TimelineItem[]`；SessionDetail 新增 `pipeline_timelines`
- [x] 4.3 单测：反序列化往返、非法输入回退

## 5. 前端：selectSession 恢复（App.tsx）

- [x] 5.1 chat 消息恢复：`h.agentTimeline` 存在则直接反序列化使用，否则回退 buildTimelineFromHistory
- [x] 5.2 pipeline 消息恢复：`data.pipeline_timelines` 反序列化为 nodeTimelines（running 与 completed 两分支）
- [x] 5.3 单测：结构化恢复优先、旧数据回退近似、管线 nodeTimelines 恢复

## 6. 验证

- [x] 6.1 后端 pytest / 前端 vitest 全绿
- [x] 6.2 ruff / tsc 全绿
- [x] 6.3 E2E：stub 管线完成 -> 切换会话再切回 -> 思考/搜索/工具调用/管线节点时序均完整可见；不回归
- [ ] 6.4 人工验证报告落 `tests/validation/persist-full-session-timeline-validation.md`（真实 LLM 下切换/关闭后全部恢复）
