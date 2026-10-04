# 人工验证报告: add-event-delivery-resilience

**日期**: 2026-10-05
**验证人**: ZCode agent（程序化验证 + 逐项核对；报告内容主观质量待 owner 核读）
**关联 delta**: openspec/changes/add-event-delivery-resilience/
**E2E 门禁**: 不适用（纯后端逻辑变更，非交互类）；CI stub 套件绿（PR #224 checks：stub 13m16s + lint-and-test 7m28s）
**部署验证**: PR #224 squash 合并（main `007816f9`）→ `docker compose up -d --build` 重建（2026-10-05 01:47 前，backend healthy，重建前确认无 running 会话）

## 验证环境

生产会话 `8c24c967-15b`：**ReAct 路径**（`/api/analyze` 不带 stock_code → react 解析 → run_deep_analysis 工具）深度分析拓荆科技（688072）——与 2026-10-04 20:39 误判超时事故完全同路径。2026-10-05 01:47 发起，**304 秒 completed**，报告 8649 字，`拓荆科技_688072_20261005_015314_report.md/pdf` 落盘。本次运行思考量中等（1,299 条 thinking_token，未复现 7 万洪峰）。

## 验证结果

| Scenario | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| 三界面说法归一（incident 037 主诉） | 管线完成后 journal 终态、会话状态、聊天回复一致指向「完成」 | journal：`report_ready` 01:53:22/23 + `done` 01:53:37（与 duration_ms=304s 精确吻合，实时无积压）；`sessions.status=completed` + report_markdown 8649 字落库；聊天回复为正确结构化摘要（「综合评级中性…维持观望」），**未出现**「未返回有效报告内容」类歧义文案 | ✅ |
| 看门狗不误判（20:39 事故回归） | ReAct 路径完整跑完不触发 2400s 预算误判 | 304s 完成，无 `pipeline_timeout`，会话未被置 failed | ✅ |
| 终态事件经 publish_terminal | done/report_ready 走重试发布通道、seq 单调 | journal 终态 seq 连续（1055/1057/1645），先落库后 fan-out 语义保持 | ✅ |
| 空 output 守卫 | react 摘要 LLM 不拿空输入自由发挥 | 最终 TOOL_RESULT 非空、摘要基于结论材料 | ✅ |

## 故障注入覆盖的说明

tasks.md 第 6 项的「故障注入核对终态可见性」由**测试层证据**承担，不在生产环境注入故障（风险不对称：可能再造一个 interrupted 会话）：

- 图真未完成 → 判超时：`test_pipeline_watchdog_graph_done.py` 场景 B（回归锚，旧代码即绿）
- 图已完成+排空滞后 → 不判超时：同文件场景 A（**旧代码红=事故精确复现**，final review 独立复现过 RED）
- journal 瞬断 → `_get_db` 6 次重试自愈：`test_session_store_retry.py`（含精确退避序列断言）
- journal 持续故障 → publish_terminal 5×1s 耗尽 raise → **CAS 释放保 `_run_task` 兜底**：`test_stream_registry_terminal_priority.py::test_publish_terminal_exhaustion_releases_cas`
- 队列满分类处置（明细可丢+计数、边界/终态不丢）：watchdog 场景 C
- CI stub e2e 套件（PR #224 checks）全绿

极端洪峰（7 万 token）下的真实复现依赖下次生产洪峰观察；本次 1,299 条属常规量级。

## 异常记录

无失败项。

附注（非本变更范围，挂账）：
1. 本机 Langfuse production label 的 bear_debater prompt（v29）落后权威源（缺「最新披露/并列呈现」段）——`scripts/deploy_prompts.py` 发布会变更共享 dev 服务器，待 owner 决策（见 PR #224 描述挂账）
2. 遗留记账 7 项（`_drop_counts` 清理、满队列终态专测、backlog_stats ops 出口等）见 `.superpowers/sdd/progress.md`，均不阻塞

## 结论

- [x] 全部通过，可 archive（待 owner 核读聊天摘要与报告主观质量后执行 sync + archive）
