# Tasks: redesign-pipeline-hierarchical-timeline

> 前置依赖：`fix-pipeline-banner-and-eta` 已落地（node_start 事件流、节点计时、ETA）。

## 1. 后端：Layer I 并行事件拆分

- [ ] 1.1 编写失败测试：agent 路径下 Layer I 4 个分析师各自产出独立 node_start/node_complete（节点 ID 为 fundamental/technical/macro/sentiment_analyst），无法拆分时回退整层 node_complete
- [ ] 1.2 修改 `src/finance_agent/agent_factory.py`（必要时 `graph.py`）：graph.stream 迭代中拆分 Layer I 并行 chunk 为独立节点事件
- [ ] 1.3 确认 `api.py` 的 LAYER_STEPS 覆盖全部 21 节点的 layer/desc 映射，与前端映射表对齐

## 2. 前端：状态树模型

- [ ] 2.1 编写失败测试：`pipelineTree` 纯函数测试（node_start/node_complete 驱动 layer 与子节点状态流转、耗时记录、状态单调性）
- [ ] 2.2 新增 `frontend/src/pipelineTree.ts`：LayerNode/NodeState 类型、layer→子节点静态映射表、applyNodeEvent 纯函数
- [ ] 2.3 `frontend/src/types.ts`：UIMessage 增加 layerTree 字段（或独立 state）

## 3. 前端：分层时间轴组件

- [ ] 3.1 编写组件测试：PipelineTimeline 渲染 6 layer、子节点状态图标、耗时显示、展开折叠、当前高亮
- [ ] 3.2 新增 `frontend/src/PipelineTimeline.tsx`：LayerRow/NodeRow/InlineThinking/EtaRow 组件树
- [ ] 3.3 接入 `App.tsx`：替换 PipelineCard 进度区为 PipelineTimeline，保留日志折叠区；handleSSEEvent 将 node_start/node_complete 路由到 pipelineTree
- [ ] 3.4 当前节点内联思考摘要（单行流式预览）+ 点击展开完整 TimelineRenderer
- [ ] 3.5 layer 展开折叠默认策略（运行层展开/完成层折叠）+ 用户偏好会话内记忆
- [ ] 3.6 自动滚动定位当前节点（3 秒手动滚动暂停窗口）
- [ ] 3.7 历史会话兼容回退渲染

## 4. 验证

- [ ] 4.1 `uv run pytest` / `cd frontend && npm test` 全绿
- [ ] 4.2 `uv run ruff check` / `uv run mypy` 无新增告警
- [ ] 4.3 E2E：真实前后端深度分析全流程，断言 Layer I 4 分析师独立状态流转、Layer II 子节点逐个可见、当前节点高亮与滚动（tests/e2e/）
- [ ] 4.4 人工验证报告落 `tests/validation/`：含新旧 UI 观感对比截图、Layer II 全程状态可见性确认、Layer I 摘要错位修复确认
