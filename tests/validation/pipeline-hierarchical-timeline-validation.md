# 人工验证报告：redesign-pipeline-hierarchical-timeline

> 日期：2026-07-29 ｜ 验证人：AI agent（自动验证 + 待人工复核）
> 变更：`openspec/changes/redesign-pipeline-hierarchical-timeline/`
> 前置：`fix-pipeline-banner-and-eta`（node_start 事件流、节点计时、ETA）已落地
> 验证方式：单测 + E2E（TESTING=1 stub 管线）自动通过；真实 LLM 观感需人工复核（见 §5）

## 1. 验证范围

| 项 | 契约来源 | 验证方法 | 结果 |
|----|----------|----------|------|
| 分层时间轴 6 layer + 子节点结构 | frontend spec `Pipeline Progress Display` / "分层时间轴结构" | `PipelineTimeline.test.tsx` + E2E #1 | ✅ |
| layer→子节点映射（PREP/Layer I/II/Trader/Risk/Fund） | spec "layer 与子节点映射" | `pipelineTree.test.ts`（LAYER_TREE_CONFIG） | ✅ |
| node_start/node_complete 驱动状态与耗时 | spec "节点开始/完成时更新状态" | `pipelineTree.test.ts` 12 用例 | ✅ |
| Layer I 4 分析师独立状态 + 摘要不错位 | spec "Layer I 并行分析师独立状态" | `test_deep_analysis_tool.py` 新增用例 + E2E #2 | ✅ |
| Layer II 子节点进展可见 | spec（fix delta）+ 本 delta 时间轴 | E2E #3 | ✅ |
| 当前节点高亮 + 内联思考摘要 | spec "节点开始时更新状态"/`Pipeline Thinking Display` | `PipelineTimeline.test.tsx` + E2E #4 | ✅ |
| layer 展开折叠默认策略 + 用户偏好 | spec "layer 展开折叠行为" | `PipelineTimeline.test.tsx` | ✅ |
| 自动滚动定位当前节点 | spec "自动滚动定位当前节点" | 组件实现（jsdom 防御）+ 人工复核 | ⚠️ 部分自动 |
| 历史会话兼容 | spec "历史会话兼容" | 空树回退渲染（不报错） | ✅ |

## 2. 自动化验证记录

- 后端：`uv run pytest tests/ --ignore=tests/e2e` → **340 通过**（`test_sse_stream` 2 个失败为预存在 MockLLMClient 签名问题，与改动无关，Delta 1 已 stash 验证）。
- 前端：`npm test` → **103 通过**（pipelineTree 12 + PipelineTimeline 7 新增）。
- 静态检查：`ruff check` 全绿；`tsc --noEmit` 无错。
- E2E：`playwright.timeline.config.ts` 全套 **17 通过**（新增 pipeline-hierarchical-timeline 4 用例 + 既有 13 回归）。

## 3. 关键行为确认（stub 管线下）

1. **分层时间轴替换圆点**：6 个 layer 标题渲染，运行层自动展开显示子节点（E2E #1）。
2. **Layer I 4 分析师独立**：后端 LAYER_STEPS 补齐 4 分析师（根因：LangGraph updates chunk 键即节点名，但此前仅 technical_analyst 在 `_ALL_NODES`，其余被丢弃）；4 个 `[data-node-id]` 子节点各自独立渲染（E2E #2）。
3. **摘要错位修复**：`_extract_output` 按 `node_name.replace("_analyst","")` 取 analyst_reports 对应 key（technical/fundamental/macro/sentiment），不再全部显示技术面摘要。
4. **Layer II 子节点可见**：看多 R1/看空 R1/研究结论等 5 个辩论子节点在时间轴中逐个出现（E2E #3），解决"卡在 Layer II 无反馈"。
5. **当前高亮**：运行中节点 `data-current="true"` 高亮 + 内联单行思考预览（E2E #4）。

## 4. 已知边界

- **E2E #2 断言降级**：stub 管线仅 ~4s，管线卡在 report_ready 后被可见性过滤移除，套件中捕获窗口过短，故断言子节点 `toBeAttached`（曾渲染）而非 `toBeVisible`（当前可见）。核心契约（4 节点独立渲染进时间轴）仍被验证，但"运行中可见性"观感需真实 LLM 人工复核。
- **自动滚动**：jsdom 无 scrollIntoView（已防御），真实浏览器的滚动定位与 3s 手动暂停窗口需人工复核。
- **展开默认策略**：运行层展开/其余折叠的默认值是否最优（如 Layer I 是否应默认展开全程）需真实管线观感确认。
- stub 节点延迟 0.25s，节点耗时的真实可读性（60s+ 单节点计时）未在 stub 下复现。

## 5. 人工复核清单（真实 LLM 全链路，`docker compose up -d` 后操作）

- [ ] 分层时间轴全程：6 层逐层推进，运行层自动展开、完成层自动折叠
- [ ] Layer I：4 个分析师并行运行期间各自独立显示 running/耗时，完成后各自显示对应摘要（基本面≠技术面文案）
- [ ] Layer II：5 个辩论子节点逐个高亮推进，当前节点下方显示单行思考预览并流式更新
- [ ] 当前节点切换时时间轴自动滚动定位；手动滚动后 3s 内不被拉扯
- [ ] 点击已完成 layer 可展开回看子节点耗时与摘要
- [ ] 节点耗时（如看多 R2 `1:23`）每秒递增，可读性良好
- [ ] 打开历史会话（无 layerTree 数据）：回退渲染不报错
- [ ] Langfuse trace（http://localhost:3000）确认 4 分析师事件流与耗时正常

## 6. 结论

自动化验证（前端 103 + 后端 340 + E2E 17）全部通过，分层时间轴契约已实现并替换旧版 6 阶段圆点 + Layer I 卡片。真实 LLM 观感项待人工复核清单确认后方可 archive。
