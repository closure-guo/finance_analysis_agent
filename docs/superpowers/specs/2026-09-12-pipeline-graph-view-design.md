# 深度分析管线 Graph 视图设计（P1）

日期：2026-09-12｜状态：已与 owner 对齐（并存切换 / 悬浮卡片 / 回边+徽标 / React Flow）

## 背景与目标

现有管线进度 UI 是层级时间轴（`PipelineTimeline.tsx`，数据来自 `pipelineTree.ts` 纯函数状态树）。本设计为 deep 分析管线增加 Langfuse 风格的节点图（DAG）视图：实时状态着色、耗时、FM 退回循环的回边+迭代徽标。

明确不做：拖拽编排（行为真相源分裂，见 2026-09-12 可行性评估）、报告章节锚点跳转、历史 trace 复盘图（P2，走 Langfuse observations）、quick/follow-up 适配（ReAct 循环无六层拓扑）。

## 架构与数据流（后端零改动）

```
SSE node_start/node_complete 事件（现有）
  → streamStore（现有）
  → pipelineTree.ts 状态树（现有纯函数，单调状态机，不动）
  → graphModel.ts（新增：树 → React Flow nodes/edges）
      · dagre 自上而下自动布局
      · 条件回边 FM→Trader（静态拓扑补充，虚线常驻）
      · 迭代计数 = 同 nodeId 的 node_start 出现次数（独立统计，不改单调状态语义）
  → PipelineGraph.tsx（新增：@xyflow/react 渲染）
```

关键约束：节点状态沿用 pipelineTree 单调流转（pending → running → completed，无回退）；迭代次数独立于状态机统计，保证 graph 与列表两个视图数据永远一致。

## 交互行为

- **切换**：管线区头部「图 / 列表」segmented toggle；选择持久化 localStorage（键 `fa_pipeline_view`，模式同 `fa_track_prefs`）；窄屏 <768px 隐藏图选项（仅列表）。
- **节点**：状态色 pending 灰 / running 蓝脉冲 / completed 绿 / failed 红；显示耗时；迭代徽标 ×N（N≥2）。
- **回边**：FM→Trader 虚线低透明常驻；迭代发生时实线动画化，Trader/FM 节点戴 ×N 徽标。
- **点击节点**：侧边悬浮卡片——状态/耗时/一句话摘要（`output.summary`）；卡片「查看详情」= 切到列表视图并展开对应节点（复用 TimelineRenderer 现有展开，不新造跳转）。
- **空态/恢复**：无事件占位提示；历史会话恢复走既有事件回放，graph 自动还原（零额外工作）。

## 组件与文件

| 文件 | 动作 | 职责 |
|---|---|---|
| `frontend/src/graphModel.ts` | 新增 | 纯函数：LayerNode[] → { nodes, edges }；布局与迭代计数 |
| `frontend/src/PipelineGraph.tsx` | 新增 | React Flow 渲染 + 自定义节点 + 悬浮卡片 |
| `frontend/src/PipelineTimeline.tsx`（宿主区） | 修改 | 图/列表 toggle、localStorage 读写、窄屏降级 |
| `frontend/src/test/graphModel.test.ts` 等 | 新增 | 单测 + 组件测试 |

依赖新增：`@xyflow/react`、`dagre`、`@types/dagre`。

## 测试策略

- 单测（TDD 先行）：graphModel 纯函数——树→nodes/edges 映射、dagre 布局产出坐标、迭代计数、回边生成、空树。
- 组件测试：状态着色、徽标、toggle 持久化与窄屏降级、点击节点出卡片、查看详情切列表。
- E2E（stub 套件，交互类红线）：切换持久化、运行中状态流转、点击卡片。若 e2e 基础设施不可用则按 §3 Step 4.5 豁免并记入人工验证报告。
- 人工验证报告落 `tests/validation/`。

## 工作量

2–4 天（人工口径）。交互类变更：OpenSpec delta → §3 完整管线（含 E2E 门禁）。
