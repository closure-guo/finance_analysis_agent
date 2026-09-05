# Tasks: add-user-feedback

## 1. 后端

- [x] 1.1 `POST /api/feedback`：校验 trace_id/value（422）、`create_score(user_feedback, 1/0)`、旁路容错（WARN 不阻断）
- [x] 1.2 trace_id 注入：quick AG-UI run_finished + deep 工具终态事件携带 `langfuse_trace_id`（实证 get_current_trace_id 可用性）

## 2. 前端

- [x] 2.1 types.ts UIMessage 加 `langfuse_trace_id?`；reducer chat_done 存 trace_id；adapter metadata.custom 透传
- [x] 2.2 MessageActions 点赞/点踩调 `/api/feedback`（乐观选中 + 已提交标记）；无 trace_id 本地 toggle 降级

## 3. 验收

- [x] 3.1 后端单测：端点 200/422/容错（mock Langfuse）
- [x] 3.2 前端单测：reducer 存 trace_id、adapter 透传、MessageActions 调端点与降级
- [x] 3.3 `uv run pytest`（门禁 not live）与 `cd frontend && npm test` 全绿；ruff/mypy/tsc 干净
- [x] 3.4 端到端说明：stub 无真实 Langfuse，trace 落库用本地真实运行验证（写入验证报告）
- [x] 3.5 交互类 → E2E 门禁 + 人工验证报告落 tests/validation/
