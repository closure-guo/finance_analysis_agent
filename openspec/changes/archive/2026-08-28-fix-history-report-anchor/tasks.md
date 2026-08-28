# Tasks: fix-history-report-anchor

## 1. 后端失败测试（TDD 先行）

- [x] 1.1 session_store 测试：`set_pipeline_anchor` 将锚点写为最后一条 role='user' 条目索引 + 1（[user1, assistant1, user2] → 3；仅 [user1] → 1）；chat_history 无 user 时不写
- [x] 1.2 session_store 测试：init_db 幂等迁移添加 pipeline_anchor 列，既有行保持 NULL
- [x] 1.3 api 测试：fast path（stock_code 且无 session_id）管线启动后 session 的 pipeline_anchor = 1
- [x] 1.4 api 测试：GET /api/sessions/{id} 响应包含 pipeline_anchor 字段

## 2. 后端实现

- [x] 2.1 session_store.init_db 迁移列表添加 pipeline_anchor 列（INTEGER，幂等 ALTER TABLE）
- [x] 2.2 session_store 新增 `set_pipeline_anchor(session_id)`：读 chat_history 定位最后一条 user，UPDATE pipeline_anchor；无 user 不写
- [x] 2.3 api.py fast path：`append_chat(user)` 之后、`PipelineRunner.start` 之前调用 set_pipeline_anchor
- [x] 2.4 agent_factory._make_run_deep_analysis：run_deep_analysis 工具实际启动管线时调用 set_pipeline_anchor（session_id 闭包可用时）

## 3. 前端失败测试（TDD 先行）

- [x] 3.1 selectSession.test.tsx 复现测试：多轮澄清历史 [user1, assistant1(含 agentTimeline), user2] + pipeline_anchor=3 + completed 快照 → 断言 DOM 顺序：用户提问 → 助手思考/工具横幅 → 用户确认 → pipeline-timeline → 报告（当前实现下失败，报告在 assistant1 前）
- [x] 3.2 selectSession.test.tsx 回归测试：追问历史 [user1, user2, assistant2] + pipeline_anchor=1 → 报告插在 user1 后、user2 前
- [x] 3.3 selectSession.test.tsx 兼容测试：pipeline_anchor 为 null 的旧会话保持「第一个 user 后插入」回退行为

## 4. 前端实现

- [x] 4.1 types.ts SessionDetail 增加 `pipeline_anchor?: number | null`
- [x] 4.2 App.tsx selectSession 重建逻辑：锚点非空时按「第 anchor 条 chat_history 之后」插入 pipelineDoneMsg + reportMsg；锚点为 null 时走现有第一个 user 回退

## 5. 验证

- [x] 5.1 `cd frontend && npm test` 全绿（13 文件 136 测试通过，含 3 个新锚点测试）
- [x] 5.2 `uv run pytest` 相关测试全绿（test_pipeline_anchor 8 + test_session_store 3 + test_api_pipeline_resume 9 = 20 通过）
- [x] 5.3 `uv run ruff check` 全绿；`uv run mypy` 仅预存在告警（session_store.py:298 append_session_event 的 Any 返回，stash 验证非本改动引入）
- [x] 5.4 人工验证：docker compose 启动后复现原始场景（分析热门股票 → 中际旭创 → 完成后切出切回会话），确认气泡顺序正确；验证报告落 tests/validation/
