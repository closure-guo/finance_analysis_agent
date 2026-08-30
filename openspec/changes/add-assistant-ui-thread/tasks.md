# Tasks: add-assistant-ui-thread

## 1. 调研与依赖锁定
- [ ] 1.1 锁定版本：`ag-ui-protocol`（Python SDK + LangGraph 集成）、`@ag-ui/client`、assistant-ui（React 组件），记录版本与相互兼容矩阵到 design 附录
- [ ] 1.2 确认 quick 模式 graph 事件形态（messages/updates、是否含工具调用），产出事件映射表（graph 事件 → AG-UI 事件）

## 2. 后端 AG-UI 端点
- [ ] 2.1 新增 `POST /api/agui/quick`：RunAgentInput → SSE 标准 AG-UI 事件流（官方 LangGraph 适配层包装 quick graph）
- [ ] 2.2 事件序列契约测试：正常序列（RUN_STARTED → TEXT_MESSAGE_* → RUN_FINISHED）+ 分块拼接与落库一致
- [ ] 2.3 异常终止测试：LLM 失败 → RUN_ERROR 终止、不落库成功回复
- [ ] 2.4 双轨隔离测试：现有 `/api/stream` 事件契约测试零修改通过；停用 AG-UI 路由后深度模式不受影响
- [ ] 2.5 持久化一致测试：AG-UI 通道对话写入 session_store，历史快照可恢复

## 3. 前端 assistant-ui 渲染
- [ ] 3.1 quick 模式渲染分支替换为 assistant-ui Thread + `@ag-ui/client` runtime（含主题对齐 design-system 令牌）
- [ ] 3.2 历史快照初始化：session_store chat_history → Thread 初始消息（MessagesSnapshot 映射）
- [ ] 3.3 切换守卫：流式中切换会话中止 run + 快照恢复，补串流/重复回归测试
- [ ] 3.4 流式生命周期测试：增量呈现、RUN_FINISHED 后指示器消失、最终文本与落库一致
- [ ] 3.5 深度模式测试零修改通过验证；如 quick 渲染用例需等价迁移，记录清单

## 4. 验证
- [ ] 4.1 后端 + 前端全量测试通过；`uv run ruff check && uv run mypy` 无新增
- [ ] 4.2 E2E 门禁（含 quick 模式对话流新 spec：发送 → 流式 → 终止 → 刷新恢复）
- [ ] 4.3 人工验证（真实浏览器：流式体验、切换守卫、历史恢复、双轨回退），报告落 `tests/validation/`
- [ ] 4.4 PoC 结论评审：事件映射是否可推广到管线时间线，结论写入验证报告（供后续 change 决策）
