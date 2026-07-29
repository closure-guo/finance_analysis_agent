# 人工验证报告：resume-pipeline-across-sessions

> 日期：2026-07-29 ｜ 验证人：____（待人工执行）
> 变更：`openspec/changes/resume-pipeline-across-sessions/`
> 前置：`redesign-pipeline-hierarchical-timeline` + `fix-node-timer-real-lifecycle` 已落地
> 验证方式：单测 + E2E（TESTING=1 stub 管线）自动通过；真实 LLM 全链路需人工复核（见 §3）

## 1. 验证范围

| 项 | 契约来源 | 验证方法 | 结果 |
|----|----------|----------|------|
| 管线后台执行（SSE 断开不中断） | design §D1 / Task 1-2 | `test_pipeline_runner.py` + E2E #1 | 自动通过 |
| 节点完成写快照（layerTree 内嵌 JSON 字符串） | design §2 契约 / Task 2 | `test_api_pipeline_resume.py` + `test_react_pipeline_snapshot.py` | 自动通过 |
| ReAct 主链路接入快照（run_deep_analysis） | design §8 / Task 3.5 | `test_react_pipeline_snapshot.py` | 自动通过 |
| 前端 serialize/deserializeLayerTree 往返 | Task 3.1-3.2 | `pipelineTree.test.ts` | 自动通过 |
| running 会话切回：快照恢复时间轴 + 2s 轮询推进 | design §D2 / Task 3.3 / 4.3 | E2E #1（stub 管线） | 自动通过 |
| completed 会话切回：报告 + 静态时间轴 | Task 3.3 / 4.3 | E2E #2（stub 管线） | 自动通过 |
| 真实 LLM 下切换会话管线后台续跑 + 切回恢复 | Task 4.4 | 本报告 §3 人工复核 | 待人工执行 |

## 2. 自动化验证记录

> 以下由 Task 6 E2E + 门禁自动跑出，人工验证人可据此跳过重复劳动，聚焦 §3。

- 后端 pytest / 前端 vitest / ruff / tsc：见 Task 6 报告（全绿，无新增失败）。
- E2E（`playwright.timeline.config.ts`）：
  - 用例 1「运行中切走再切回：快照恢复时间轴且轮询驱动进度推进」—— PASS
  - 用例 2「管线完成后切回：报告可见 + 静态时间轴展示」—— PASS
  - 既有 `thinking-timeline-history` —— 不回归（PASS）

## 3. 人工复核清单（真实 LLM 全链路）

> 前置：`docker compose up -d` 启动全栈（FastAPI 8000 + Vite 5173 + Langfuse 3000）。
> 目标股票任选一只 A 股（如 600519）。操作期间保持后端日志与 Langfuse 面板可见。

### 3.1 运行中切走再切回（running 分支恢复 + 轮询推进）

操作步骤：

- [ ] 1. 前端切到「深度研究」模式，输入「深度分析600519」发送，等待分层时间轴出现首个 running 节点。
- [ ] 2. 记录当前进度（时间轴计数 / ETA），点击侧边栏另一个会话切走。
- [ ] 3. 等待 5-10s，期间观察后端日志：`graph.stream` / `run_deep_analysis` 是否继续推进（节点 node_complete 日志持续打印）。
- [ ] 4. 打开 Langfuse（http://localhost:3000）查看当前 trace：确认 LLM 调用链路未中断、节点耗时持续累加。
- [ ] 5. 切回原会话，观察时间轴是否立即从快照恢复（非空白/非「准备中」），且 2s 内计数较切走前有推进。

观察点：

- 后端日志：切走后是否仍有 `node_complete` / `update_pipeline_snapshot` 日志（证明管线后台续跑）。
- Langfuse trace：链路连续，无中断/取消标记。
- 前端：切回瞬间时间轴反映断开点快照（静态渲染），随后 2s 轮询刷新计数递增、ETA 递减。
- 数据库（可选）：`SELECT status, pipeline_snapshot FROM sessions WHERE session_id=...` 确认 status 仍为 running 且 snapshot.updatedAt 持续更新。

结论：____

### 3.2 完成后切回（completed 分支：报告 + 静态时间轴）

操作步骤：

- [ ] 1. 等待 §3.1 管线跑完（后端日志出现 `status=completed` / 前端出现「深度分析报告」）。
- [ ] 2. 切走到另一会话，再切回原会话。
- [ ] 3. 观察报告是否可见（Markdown 渲染 + 图表）。
- [ ] 4. 观察分层时间轴是否以静态完成态展示（6 层均渲染，各层显示完成计数）。

观察点：

- 报告：Markdown 正文 + ECharts 图表正常渲染，无空白/错位。
- 时间轴：6 层全部渲染（PREP / Layer I / Layer II / Trader / Risk / Fund），各层显示 `n/总数` 计数。
- 不应出现「分析中」running 态（progress 条/ETA 应消失或为完成态）。

结论：____

### 3.3 异常态（failed 分支，可选）

- [ ] 管线异常时切回，会话状态为 failed，不 crash、不卡 analyzing（MVP 仅停止轮询，不展示失败态 UI）。

结论：____

## 4. 已知限制

- **ReAct 路径部分节点快照可能恒 pending（不影响报告恢复）**：真实主链路经 ReAct `run_deep_analysis` 工具驱动，个别节点（如 `prep/fetch_data`）的快照状态可能恒为 `pending`，导致 `pipeline_snapshot.progress` 卡在 0.96 而非 1.0。此为既有事件捕获局限（Task 6 实测确认，非本 change 引入），不阻塞「完成后切回报告 + 静态时间轴」恢复链路——completed 分支以 `status==='completed'` 为准展示静态时间轴，layerTree 反映实际节点状态（允许个别 pending）。后续若需 progress===1，需排查 `run_deep_analysis` 循环对该节点事件流的捕获。详见 `.superpowers/sdd/task-6-report.md` 缺口 2。
- **ReAct 路径「断开后完整后台续跑到底」属后续 change**（design §8）：当前切走断开 SSE 后，后台 task 仍会推进一段（受 asyncio 取消时序影响），但「完整续跑到底」不在本 change 范围；本 change 以「快照恢复 + 2s 轮询刷新」闭环覆盖切回场景。

## 5. 结论

自动化验证（单测 + E2E）全绿，切换会话恢复管线链路（running 轮询恢复 / completed 静态恢复）已实现。真实 LLM 观感项待 §3 人工复核清单确认后方可 archive。
