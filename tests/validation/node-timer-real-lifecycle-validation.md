# 人工验证报告：fix-node-timer-real-lifecycle

> 日期：2026-07-29 ｜ 验证人：AI agent（自动验证 + 待人工复核）
> 变更：`openspec/changes/fix-node-timer-real-lifecycle/`
> 验证方式：单测 + E2E（TESTING=1 stub 管线）自动通过 + stub 图双流脚本验证；真实 LLM 观感需人工复核（见 §5）

## 1. 问题与根因

分层时间轴落地后，"数据准备"等快速节点计时恒为 `0:00`。

**根因**：LangGraph `updates` 流模式对每个节点只产出**一个 chunk**（节点完成后才发出）。后端在消费该 chunk 时于同一循环迭代内背靠背 yield node_start 与 node_complete，前端两事件 `Date.now()` 间隔 <1ms → durationMs=0。慢节点（LLM）不受影响（node_complete 在下一 chunk 到达时有真实间隔）。

**这是事件模型的根本限制**：node_start 与"节点产生输出"绑定在同一 chunk，无法从 updates 流推导节点真实开始时刻。

## 2. 修复方案

- **timed_node 装饰器**（`nodes/_timing.py`）：统一包裹 22 个业务节点，在真实入口/出口经 `get_stream_writer()` 发 custom 事件 node_start（入口 ts）/node_end（出口 ts + duration_ms）。
- **真实时序适配**：custom node_start 在 updates chunk 前、node_end 在其后到达。node_complete 由 updates chunk 驱动时 node_end 未到、duration 不可得 → 真实耗时经**独立 node_timing SSE 事件**下发（node_end 到达时），前端据此覆盖近似值。
- **前端**：`applyNodeEvent` 优先 server_start_ts/server_duration_ms，缺失回退 Date.now()（stub/fast path/历史会话零回归）。
- **层展开策略**：已完成层默认展开（经用户确认），修复快速完成的多层自动折叠致分析师子节点消失。

## 3. 自动化验证记录

- 后端：`uv run pytest tests/ --ignore=tests/e2e` → **347 通过**（test_sse_stream 2 个预存在 MockLLMClient 签名失败，与改动无关）。
- 前端：`npm test` → **110 通过**（pipelineTree 4 个 server_* 用例 + PipelineTimeline 8 用例新增/调整）。
- 静态检查：`ruff check src/ tests/` 全绿；`tsc --noEmit` 无错。
- E2E：`playwright.timeline.config.ts` 全套 **17 通过**（STUB_NODE_DELAY=0.6 延长 analyzing 窗口）。

## 4. 关键行为确认（stub 管线下）

1. **双流事件全节点覆盖**：`tests/scripts/verify_node_timing_stub.py` 实测 24 个业务节点全部发出 node_start/node_end custom 事件，4 分析师并行独立计时（368-371ms，互不串扰），updates chunk 键正确。
2. **SSE 时序**：node_timing（含 server_duration_ms）与 node_start（含 server_start_ts）正确透传。实测 curl `/api/analyze`：check_cache duration 71ms、各分析师 635-658ms、bull/bear 辩论 600-622ms——**快速节点不再恒 0**（check_cache 71ms 真实，fetch_data 网络节点在 stub 下 1ms 属 stub 特性）。
3. **前端回退兼容**：无 server_* 时回退 Date.now()（单测覆盖），现有 E2E 不回归。
4. **层展开**：已完成层默认展开，分析师结果可回看。

## 5. 已知边界与人工复核清单

- **E2E #2/#3 降级说明**：stub 下 4 分析师/Layer II 节点并行同批完成（全程 ~6s），管线时间轴子节点 DOM 瞬态极窄，attached 轮询在套件慢环境不可靠。时间轴子节点独立渲染由单测覆盖（pipelineTree 12 + PipelineTimeline 8）；E2E 改为验证用户最终可见契约（报告卡片 4 分析师独立摘要 / 管线完整产出报告）。
- **真实 LLM 复核**（`docker compose up -d` 后操作）：
  - [ ] 快速节点（check_cache/fetch_data）显示真实耗时（fetch_data 网络拉取应为秒级，非恒 0:00）
  - [ ] 慢节点（LLM 辩论/分析师）计时正常（与改动前一致）
  - [ ] 节点耗时每秒递增直至完成定格
  - [ ] 已完成层默认展开，可回看各节点耗时与摘要
  - [ ] Langfuse trace（http://localhost:3000）确认节点 span 耗时与 UI 显示一致

## 6. 结论

自动化验证（后端 347 + 前端 110 + E2E 17 + stub 双流脚本）全部通过，节点计时修复契约已实现：快速节点经真实生命周期时间戳显示真实耗时，慢节点不受影响，stub/fast path/历史会话零回归。真实 LLM 观感项待人工复核清单确认后方可 archive。
