# Tasks: add-pipeline-graph-view

- [x] 1. 失败测试先行：graphModel 纯函数（LayerNode[] → nodes/edges 映射、dagre 布局坐标、迭代计数、回边生成、空树、窄屏视图偏好规则）
- [x] 2. graphModel 实现（dagre 布局 + 迭代统计 + FM→Trader 回边），测试转绿
- [x] 3. PipelineGraph 组件（@xyflow/react 自定义节点：状态色/耗时/徽标；悬浮卡片；「查看详情」回调）+ 组件测试
- [x] 4. 宿主接线：管线区「图/列表」toggle、localStorage 持久化（fa_pipeline_view）、窄屏降级、查看详情切列表并展开 + 组件测试
- [x] 5. 依赖：@xyflow/react / dagre / @types/dagre；npm run build 通过；vitest 全绿（574/574）
- [x] 6. E2E spec 覆盖核心交互场景（切换持久化、运行中状态、点击卡片）；若 e2e 基础设施不可用则按 §3 Step 4.5 豁免并记入人工验证报告——e2e/ 未落地（2026-09-12 确认），豁免记录见验证报告
- [x] 7. 人工验证报告落 tests/validation/（截图证据）——tests/validation/2026-09-12-pipeline-graph-view-validation.md
