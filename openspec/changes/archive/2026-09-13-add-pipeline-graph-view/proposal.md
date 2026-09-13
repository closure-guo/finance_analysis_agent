# Proposal: add-pipeline-graph-view

## Why

深度分析管线的进度呈现目前只有层级时间轴一种形态。多智能体并行/循环结构（四分析师并行、FM 退回 trader 重跑）在列表里不直观，owner 需要 Langfuse 式节点图一眼看清「谁在跑、跑了几轮、退回发生在哪」。

## What Changes

- 新增管线 graph 视图：React Flow DAG 渲染，节点实时状态着色 + 耗时 + 迭代徽标，FM→Trader 条件回边在退回发生时高亮动画
- 管线区头部新增「图 / 列表」切换，偏好持久化 localStorage；窄屏 <768px 仅列表
- 点击节点弹悬浮卡片（状态/耗时/摘要），「查看详情」切回列表视图并展开对应节点
- 后端零改动：消费现有 SSE node_start/node_complete 事件与 pipelineTree 状态树

## Capabilities

- **New Capabilities**: pipeline-graph-view
- **Modified Capabilities**: 无（时间轴行为不变，纯增量视图）

## Impact

- 前端：`frontend/src/graphModel.ts`、`frontend/src/PipelineGraph.tsx`（新增）；管线区宿主组件（修改）；依赖 @xyflow/react + dagre
- 后端：无
- 交互类变更：走 §3 完整管线（E2E 门禁 + 人工验证）
