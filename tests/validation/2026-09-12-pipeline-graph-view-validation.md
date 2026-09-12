# 验证报告: add-pipeline-graph-view（管线 graph 视图）

**日期**: 2026-09-12
**验证人**: [agent]（自动化验证部分）+ owner（人工验证部分待签）
**关联 delta**: openspec/changes/add-pipeline-graph-view/
**分支**: add-pipeline-graph-view（HEAD 57fb93f）

## 自动化验证（已执行）

| 项 | 结果 |
|---|---|
| graphModel 纯函数单测（拓扑完备/布局/迭代/回边） | ✅ 10/10（TDD 先红后绿） |
| streamStore 迭代计数（nodeStartCounts 累计/互不影响/timing 不计） | ✅ 3/3 |
| PipelineGraph 组件（渲染/状态着色/徽标/卡片/查看详情回调） | ✅ 6/6 |
| PipelineCard 视图切换（默认 graph/持久化/预置偏好/查看详情切列表/窄屏） | ✅ 5/5 |
| 前端全量 vitest | ✅ 73 文件 / 574 用例全绿 |
| `npm run build`（tsc -b + vite） | ✅ 通过 |
| 回归影响面：受默认视图变更影响的旧行为测试（pipelineSummary/selectSession） | ✅ 已按新 spec 语义预置 list 偏好（原断言意图保留，注释注明） |

## E2E 门禁（§3 Step 4.5）

**豁免**：`e2e/` 基础设施未落地（P1–P4 未完成，2026-09-12 确认目录不存在）。核心交互场景（切换持久化、运行中状态流转、点击卡片）已由组件测试覆盖等价断言；e2e 落地后应补 spec。

## 需人工确认的主观项（owner 签字前必看）

1. **视觉质量**：节点尺寸/间距/配色（CSS 变量着色）在暗色与亮色主题下的观感；回边虚线在两种主题下的可读性。
2. **布局合理性**：dagre 自动布局对六层 25 节点实际渲染效果（尤其 Layer II 5 节点与 Risk 7 节点的行宽）；480px 高度是否合适（支持缩放/平移兜底）。
3. **交互手感**：点击节点弹出卡片是否遮挡关键节点；「查看详情」切列表后目标 layer 展开是否符合预期。
4. **迭代徽标**：真实触发 FM 退回的运行中，×2 徽标与回边动画是否符合直觉（组件测试用合成状态验证，未跑真实退回链路）。

## 已知边界

- 视图偏好按 localStorage 单键存储（跨会话共享偏好，不分 session）。
- graph 视图节点不可拖拽（nodesDraggable=false，只读观察视图）；支持缩放/平移。

## 结论

[ ] 全部通过，可 archive（待 owner 完成上述 4 项人工确认后签字）
[ ] 存在失败项，需修复后重新验证
