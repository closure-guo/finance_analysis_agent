# Pipeline Graph View 实施计划

> **For agentic workers:** 按 TDD 顺序执行；graphModel 纯函数测试先红后绿。
> 设计依据：docs/superpowers/specs/2026-09-12-pipeline-graph-view-design.md
> Delta：openspec/changes/add-pipeline-graph-view/
> 执行方式：主会话直接实现（单组件前端变更、文件耦合紧，subagent 拆分无隔离收益）；TDD 五步纪律与 §3 门禁不变。

## Global Constraints

- 后端零改动；pipelineTree.ts 单调状态机不动
- 节点状态单调（completed 不回退）；迭代次数独立统计 node_start 重复次数
- 视图偏好键 `fa_pipeline_view`；窄屏 <768px 仅列表
- 样式沿用 CSS 变量（--bg-brand / --status-success-default 等），不做暗色/亮色硬编码
- selector 用 data-testid（E2E 与组件测试共用）

---

### Task 1: graphModel 纯函数（TDD）

**Files:**
- Test: `frontend/src/test/graphModel.test.ts`
- Create: `frontend/src/graphModel.ts`

接口：
```ts
buildGraphModel(tree: LayerNode[], startCounts: Record<string, number>): {
  nodes: GraphNode[]   // { id, label, layerId, status, durationMs, iterations, summary?, position:{x,y} }
  edges: GraphEdge[]   // { id, source, target, kind: 'flow' | 'return', animated?: boolean }
}
```
- 边拓扑为静态表 GRAPH_EDGES（与 LAYER_TREE_CONFIG 节点 id 对齐；r1→r2 同侧延续，四方→research_manager；FM→Trader 为 kind='return'）
- dagre TB 布局（ranksep/nodesep 常量），输出 position
- iterations = startCounts[nodeId] ?? 0；空树 → { nodes: [], edges: [] }
- Step 1 失败测试 → Step 3 实现 → Step 4 绿 → Step 5 commit

### Task 2: streamStore 迭代计数

**Files:**
- Modify: `frontend/src/stores/streamStore/reduce.ts`（node_start 分支累计）
- Modify: pipeline message 类型（`nodeStartCounts?: Record<string, number>`，可选字段向后兼容）
- Test: 既有 stream-event-routing/pipelineTree 测试不回归 + 新增断言

### Task 3: PipelineGraph 组件（TDD）

**Files:**
- Test: `frontend/src/test/PipelineGraph.test.tsx`
- Create: `frontend/src/PipelineGraph.tsx`

- 自定义节点：状态色（CSS 变量）/ 耗时 / 迭代徽标（×N，N≥2）/ data-testid=`graph-node-{nodeId}`
- 回边：kind='return' 虚线；iterations≥2 时 animated
- 点击节点 → 容器内侧边卡片（状态/耗时/摘要）+「查看详情」→ onViewDetails(layerId)
- 测试需 ResizeObserver stub（参照 src/test/chat/aguiTestSetup.ts）

### Task 4: 宿主接线（App.tsx 管线区）

**Files:**
- Modify: `frontend/src/App.tsx` 管线消息渲染区（~L1884）

- 「图 / 列表」segmented toggle（data-testid="pipeline-view-toggle"），偏好读写 localStorage `fa_pipeline_view`
- <768px 隐藏 toggle（resize 监听）；默认图视图（无偏好时）
- onViewDetails → 切列表 + PipelineTimeline 展开对应 layer（现有展开机制）

### Task 5: 验证

- `cd frontend && npm test` 全绿；`npm run build` 通过
- E2E：确认 e2e/ 基础设施状态；不可用则按 §3 Step 4.5 豁免记入人工验证报告
- 人工验证报告落 tests/validation/（待运行后）
