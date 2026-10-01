# Proposal: add-pipeline-graph-zoom-controls

## Why

深度分析管线图视图目前仅靠双击放大（React Flow 默认行为），没有任何缩小或回到总览的手段：放大后想恢复只能整页刷新。用户报告（2026-09-29）要求在图右下角补齐放大、缩小、重置三个控件。

## What Changes

- 图视图右下角新增「放大 / 缩小 / 重置」三个按钮（垂直堆叠），样式沿用应用 CSS 变量主题
- 缩小 = 步进 1/1.2，放大 = 步进 ×1.2，重置 = fitView 回总览（与初始 fitViewOptions 一致：padding 0.15、maxZoom 1）
- 缩放到达既有边界（minZoom 0.4 / maxZoom 1.5）时对应按钮禁用
- 双击放大、滚轮平移等既有交互不变

## Capabilities

- **Modified Capabilities**: pipeline-graph-view

## Impact

- `frontend/src/PipelineGraph.tsx`：新增 `GraphZoomControls` 子组件（useReactFlow + useViewport + Panel）
- `frontend/src/test/PipelineGraph.test.tsx`：控件渲染与禁用语义单测
- `tests/e2e/playwright/tests/pipeline-graph-zoom.spec.ts`：真实浏览器缩放行为 E2E（timeline 套件）
- 两份 playwright config 的 testMatch/testIgnore 挂载
