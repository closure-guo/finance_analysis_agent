# 人工验证报告: add-user-feedback

**日期**: 2026-09-04
**验证人**: [agent 自动验证 + 待人工抽查]
**关联 delta**: openspec/changes/add-user-feedback/
**E2E 门禁**: 不适用（反馈点击行为由单测覆盖；stub 无真实 Langfuse，端到端 trace 落库需真实运行验证）

## 验证结果

| Scenario | 覆盖方式 | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 点赞上报（value=1, trace 正确） | 单测（mock Langfuse） | `create_score(name="user_feedback", value=1, trace_id)` | test_api_feedback 7 例全绿 | ✅ |
| 点踩上报（value=0） | 单测 | value=0 | 同上 | ✅ |
| 非法 value / 缺 session_id → 422 | 单测 | Pydantic + 显式校验拒绝 | test_invalid_value_422 / test_missing_session_422 | ✅ |
| session 无关联 trace → 不上报不报错 | 单测 | submitted=False, create_score 不调用 | test_session_without_trace_noop | ✅ |
| Langfuse 未配置 / 上报异常 → 旁路 | 单测 | 不传播、响应成功 | test_langfuse_unconfigured_noop / test_langfuse_error_bypass | ✅ |
| trace 关联 session（quick） | 代码接线 | RUN_FINISHED 时 react_obs.trace_id → set_session_trace_id | agui/endpoint.py 终态分支 | ✅（代码审查） |
| trace 关联 session（deep） | 代码接线 | 工具完成分支 accumulated/get_current_trace_id → set_session_trace_id | agent_factory.py 完成分支 | ✅（代码审查） |
| 前端点赞/点踩触发上报 | 单测 | onFeedback('like'/'dislike')，再点取消不上报 | messageActions.test 11 例全绿 | ✅ |
| App 桥接 POST /api/feedback | 代码接线 | currentSessionId + value POST，失败静默 | App.tsx onFeedback | ✅（代码审查） |

## 待人工抽查项

- [ ] **真实 Langfuse 验证（关键）**：跑一次真实深度分析 → Langfuse UI 确认 session 的 langfuse_trace_id 已关联 → 点赞/点踩 → Langfuse trace 页出现 `user_feedback` score（value 1/0）。stub 环境无真实 Langfuse 写入，`get_current_trace_id()` 在 deep 工具完成上下文是否返回有效 id 需此步实证；若为空，按 design.md 退「session 级最近 trace」降级方案。
- [ ] quick 模式点赞/点踩同样验证（react_obs.trace_id 来源较可靠）。

## 异常记录

1. **设计修正**：原 spec 草案为「SSE 终态事件携带 trace_id + 前端存消息 + adapter 透传」，实施时发现 AG-UI 协议事件注入会破坏标准协议，且前端消息（quick 走 AG-UI runtime）与 streamStore 双轨使透传复杂。改为**后端解析**方案：run 完成时把 trace 关联到 session（持久化），反馈端点按 session 解析最近一次运行——spec 已同步修订（validate 通过），前端零协议侵入。
2. 既有 flaky（sidebar-transition-sync framer-motion）与本 delta 无关。

## 结论

- [x] 功能实现 + 自动化验证通过（后端端点 7 例、前端 11 例、后端相关 111 例、前端全量 470 过、ruff/mypy/tsc 干净）
- [ ] 待真实 Langfuse 验证（上方待人工抽查项）完成后方可 archive
