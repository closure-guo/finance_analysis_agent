# Tasks: redesign-pipeline-hierarchical-timeline

> 前置依赖：`fix-pipeline-banner-and-eta` 已落地（node_start 事件流、节点计时、ETA）。

## 1. 后端：Layer I 并行事件拆分

- [x] 1.1 编写失败测试：`test_deep_analysis_tool.py` 新增用例断言 Layer I 4 个分析师各自产出独立 node_complete
- [x] 1.2 `src/finance_agent/api.py`：LAYER_STEPS 补齐 fundamental/macro/sentiment_analyst（LangGraph updates chunk 键即节点名，天然可拆，无需改图）；`_extract_output` 支持 4 分析师各自的 analyst_reports key（修复摘要错位根因）
- [x] 1.3 确认 LAYER_STEPS 与前端 LAYER_TREE_CONFIG 映射对齐

## 2. 前端：状态树模型

- [x] 2.1 编写失败测试：`frontend/src/test/pipelineTree.test.ts`（12 用例：初始树、node_start/complete 状态流转、耗时记录、状态单调性、Layer I 并行独立状态）
- [x] 2.2 新增 `frontend/src/pipelineTree.ts`：LayerNode/ChildNodeState 类型、LAYER_TREE_CONFIG（6 层→22 子节点）、applyNodeEvent 纯函数、findRunningNode/treeProgress
- [x] 2.3 `frontend/src/types.ts`：UIMessage 增加 layerTree 字段

## 3. 前端：分层时间轴组件

- [x] 3.1 编写组件测试：`frontend/src/test/PipelineTimeline.test.tsx`（7 用例：6 layer 渲染、子节点状态/耗时、当前高亮、展开折叠默认策略与用户偏好覆盖）
- [x] 3.2 新增 `frontend/src/PipelineTimeline.tsx`：LayerRow/ChildRow/StatusIcon 组件树，状态图标 + 耗时 + 当前高亮 + 内联思考摘要
- [x] 3.3 接入 `App.tsx`：PipelineCard 用 PipelineTimeline 替换 6 阶段圆点与 Layer I 卡片区（删除 getStageStatus/analystCards/AnalystCard/PIPELINE_STEPS/STAGE_NODES 冗余）；handleSSEEvent 维护 layerTree
- [x] 3.4 当前节点内联思考摘要（thinkingPreviewFor：nodeTimelines 末尾 thinking 内容尾 80 字符单行预览）
- [x] 3.5 layer 展开折叠默认策略（运行层展开/其余折叠）+ 用户偏好会话内记忆（expandedOverride）
- [x] 3.6 自动滚动定位当前节点（scrollIntoView + 3s 手动滚动暂停窗口 + jsdom 防御）
- [x] 3.7 历史会话兼容回退（layerTree 为空时 buildLayerTree() 空树渲染，不报错）

## 4. 验证

- [x] 4.1 `uv run pytest` 后端 340 通过 / `npm test` 前端 103 通过
- [x] 4.2 `uv run ruff check` 全绿 / `npx tsc --noEmit` 无错
- [x] 4.3 E2E：新增 `tests/e2e/playwright/tests/pipeline-hierarchical-timeline.spec.ts`（4 用例：6 layer 渲染、Layer I 4 分析师独立、Layer II 子节点可见、当前高亮）；timeline config 全套 17 用例通过（含既有回归与 pipeline-eta-banner）
- [x] 4.4 人工验证报告落 `tests/validation/pipeline-hierarchical-timeline-validation.md`
