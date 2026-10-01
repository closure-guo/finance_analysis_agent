# 人工验证报告: add-pipeline-graph-zoom-controls

**日期**: 2026-09-29
**验证人**: ZCode（自动执行 + 真实浏览器目视抽查）
**关联 delta**: openspec/changes/add-pipeline-graph-zoom-controls/
**E2E 门禁**: tests/e2e/playwright（pipeline-graph-zoom.spec.ts 绿，timeline 套件 8002/5175）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 缩小/放大步进（×1.2 / 1÷1.2） | 是（pipeline-graph-zoom.spec.ts，viewport scale 逐帧 poll） | 放大后 scale=s0×1.2；缩小后回到 s0 | 符合（s1≈s0×1.2，toBeCloseTo 6 位） | ✅ |
| 重置回总览 | 是（点击重置后 scale 回 s0，1e-6 容差） | fitView 语义与初始 fitView 一致 | 符合 | ✅ |
| 缩放边界禁用 | 是（收敛循环至禁用 + 放大可用断言） | 到 0.4/1.5 边界对应按钮禁用 | 符合（真实宽 DAG 下 fitView 即在 0.4，缩小初始禁用被正确覆盖） | ✅ |
| 控件位置（右下角） | 是（bounding box 右缘/下缘逼近容器，容差 40px） | 画布右下角纵向三控件 | 符合 | ✅ |
| 节点可见（种子过渲染守卫） | 是（graph-node-fundamental_analyst 可见） | DAG 节点真实渲染，防空画布假通过 | 符合 | ✅ |
| 既有交互不回归（双击放大/滚动平移/视图切换） | 部分（pipeline-view-toggle.spec.ts 绿；双击缩放保留未动） | 既有行为不变 | 符合 | ✅ |
| 目视抽查（headless Chromium 截图，放大两步态） | 否 | 控件样式与主题一致、不遮挡节点、节点边正常 | 目视符合 | ✅ |
| 前端单测 + 类型 | 否 | vitest 全绿、tsc -b 无错 | 622 用例全过（含新增 2 条）；tsc 通过 | ✅ |

## 实现说明

- `PipelineGraph.tsx` 新增 `GraphZoomControls`（`<ReactFlow>` child，v12 Store Provider 内直接用 `useReactFlow`/`useViewport`），`<Panel position="bottom-right">` 承载；样式全部走 index.css 已定义令牌
- 边界常量与 fitView options 提为模块常量（ZOOM_MIN/ZOOM_MAX/FIT_VIEW_OPTIONS），ReactFlow props 与控件共用单一事实源
- E2E 采用 `/api/test/seed` 造完成态会话（与 persist-full-session-timeline.spec.ts 同方案），规避实时流式重渲染导致的元素重挂竞态；完成态管线卡需点击 `pipeline-summary` 展开后图视图才渲染

## 异常记录

- 首版 E2E 走「实时管线运行中交互」两度失败：①管线完成图卸载后点击目标脱离 DOM；②真实宽 DAG 下 fitView 初始即钳在 minZoom（0.4），「缩小」初始禁用。均按根因修正方案与交互序列（seed 完成态 + 先放大），非放宽断言
- 种子层树最初用空 children，图视图空画布（DAG 画的是层的 children）——已按 LAYER_TREE_CONFIG 真实结构修正并新增节点可见断言（#23 渲染守卫教训）

## 结论

[x] 全部通过，可 sync + archive
