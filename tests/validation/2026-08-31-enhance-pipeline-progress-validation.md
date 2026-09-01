# 人工验证报告: enhance-pipeline-progress

**日期**: 2026-08-31
**验证人**: ZCode agent（GUI 自动化实测 + 组件测试）
**关联 delta**: openspec/changes/enhance-pipeline-progress/
**E2E 门禁**: 不适用（e2e/ 基建 P1–P4 未落地）

## 验证环境

- 组件测试：vitest + jsdom（src/test/pipelineSummary.test.tsx，7 例）
- 浏览器：真实 Chromium（1440×900）+ TESTING=1 stub 后端（STUB_SCENARIO=pipeline）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 四态节点渲染 + 呼吸动画 | 既有 PipelineTimeline.test | 等待/运行（ping 动画）/完成（勾）/失败（红） | 沿用既有实现，四态图标组件级覆盖 | ✅ |
| SSE 事件实时推进 | 既有 reduce/store 单测 | node_complete 到达 → 节点完成、下一节点运行 | 沿用既有实现（applyNodeEvent 状态机） | ✅ |
| 完成折叠摘要条 | 组件测试 | 完成后折叠为「阶段数 + 总用时」单行，点击展开 | 实测「分析完成 · 24 个阶段 · 总耗时 0:05」，默认折叠，点击展开/收起（aria-expanded） | ✅ |
| 摘要阶段数回退 | 组件测试 | 重建会话 completedNodes 为空 → layerTree 统计 | 实测重建会话正确统计 24；组件测试覆盖回退分支 | ✅ |
| 总用时数据源 | 组件测试 | durationMs（重建）优先，completedAt-startedAt（live）回退 | 组件测试断言 1:05 / 1:04 两分支 | ✅ |
| 当前节点已用时/计时源 | 组件测试 | 计时源 = 快照 pipeline_start_ts，刷新不归零 | 组件测试：rebuildSession 存快照起点 → resume 回放 analysis_start（Date.now() 重置）→ startedAt 被校正回快照值；updatePipelineSnapshot 同契约 | ✅ |
| 刷新重建时间线 | 既有 selectSession.test | 刷新后从快照/落库重建 | 既有 13 例全绿（入口适配见异常 1） | ✅ |
| 失败节点展示 | 组件级 | 失败红标，不阻塞其余节点 | StatusIcon failed 态沿用既有实现（stub 无失败场景，实测未覆盖红标） | ⏭ 组件级 |

## 异常记录

1. **既有测试入口适配（非断言语义修改）**：6 个 completed 会话恢复用例原直接断言 pipeline-timeline 可见；新 spec 要求完成后折叠为摘要条，故在各用例选中会话后先点击 pipeline-summary 展开再执行原断言（断言本体零修改）。涉及 selectSession.test.tsx 的已完成会话/结构化管线/旧版管线/锚点定位 3 例。
2. 完成态节点级 failed 红标为沿用既有实现，本轮 stub 流程无失败节点，未做浏览器实测。

## 结论

[x] 完成折叠/计时源/实时推进全部通过（415/415 测试全绿）
[ ] E2E 门禁待基建落地后补充执行（Task 4.1 中 E2E 项未勾选）
