# 人工验证报告：fix-pipeline-banner-and-eta

> 日期：2026-07-28 ｜ 验证人：AI agent（自动验证 + 待人工复核）
> 变更：`openspec/changes/fix-pipeline-banner-and-eta/`
> 验证方式：单测 + E2E（TESTING=1 stub 管线）已自动通过；真实 LLM 全链路观感项需人工复核（见 §5 清单）

## 1. 验证范围

| 项 | 契约来源 | 验证方法 | 结果 |
|----|----------|----------|------|
| agent 路径补发 node_start | frontend spec `Pipeline Progress Display` / "agent 路径发送 node_start" | `tests/test_deep_analysis_tool.py` 2 新用例 | ✅ 通过 |
| 快速模式思考横幅显式折叠 | frontend spec `Conversation Stream Common Events` 新增场景 | `agentTimeline.test.ts` 6 新用例 | ✅ 通过 |
| 管线模式 node_complete 收口思考横幅 | frontend spec `Pipeline Thinking Display` / "节点完成时思考横幅显式折叠" | `agentTimeline.test.ts` 4 新用例 + E2E #3 | ✅ 通过 |
| 动态 ETA 替换静态 ~90s | frontend spec 新增 `Pipeline ETA Display` | `eta.test.ts` 16 用例 + E2E #1/#4 | ✅ 通过 |
| Layer II 子节点进展可见 | frontend spec "Layer II 子节点进展可见" | E2E #2（running 态文案可见） | ✅ 通过（stub 粒度） |

## 2. 自动化验证记录

- 后端：`uv run pytest tests/ --ignore=tests/e2e` → **339 通过**。`test_sse_stream.py` 2 个失败为预存在问题（MockLLMClient 缺 `tool_choice` 参数），`git stash` 后复现确认与本改动无关。
- 前端：`npm test` → **84 通过**（含 timeline 33、eta 16）。
- 静态检查：`ruff check` 全绿；`mypy` 无新增告警（agent_factory 2 个预存在）；`tsc --noEmit` 无错。
- E2E：`playwright.timeline.config.ts` 全套 **13 通过**（含新增 `pipeline-eta-banner.spec.ts` 4 用例与既有 thinking-timeline 回归）。

## 3. 关键行为确认（stub 管线下）

1. **ETA 动态递增**：进度区显示"已用时 M:SS · 预计剩余 ~M:SS"，采样两次已用时长单调不减（E2E #1）。无历史时初始预估 240s（单测）。
2. **node_start 驱动 running 态**：管线卡在节点开始即显示"{layer}: {desc}..."进行中文案（E2E #2），不再只有完成态跳变。
3. **思考横幅显式折叠**：管线越过 Layer I 后，技术面分析师的思考横幅显示"思考已完成"而非停留"思考中"（E2E #3）。
4. **ETA 历史写入**：report_ready 后 localStorage `financeAgent.pipelineDurations` 写入本次耗时（E2E #4）。

## 4. 已知边界

- stub 管线节点延迟仅 0.25s，Layer II "长时间运行中计时"的真实观感（60s+ 单节点）在 stub 下无法完整复现，仅验证了计时 UI 存在与递增。
- 节点级计时显示在阶段圆点下方（`nodeElapsedFor`），取值为管线总已用时长（`currentNode` 定位），非节点独立起止——精确节点级耗时留待 Delta 2（分层时间轴）实现。
- ETA 进度收敛在 stub 快速管线中跳动极小；真实管线（LLM 延迟不均）下的收敛平滑性需人工观察。

## 5. 人工复核清单（真实 LLM 全链路，需 `docker compose up -d` 后操作）

- [ ] 快速模式提问：思考完成后、回答开始前，思考横幅自动折叠为"思考已完成"
- [ ] 深度分析全程：Layer II 期间管线卡逐节点更新（看多 R1 → 看空 R1 → 看多 R2 → 看空 R2 → 研究结论），不再"卡在 Layer II 无反馈"
- [ ] 深度分析：当前运行节点所在阶段圆点下方显示计时（如 `1:23`），每秒递增
- [ ] ETA：首次运行（无历史）显示约 4 分钟量级预估；第二次运行后预估基于历史中位数
- [ ] 各 agent 思考横幅在其节点完成后折叠，无"全程思考中"残留
- [ ] Langfuse trace（http://localhost:3000）确认 agent 路径事件流无异常

## 6. 结论

自动化验证（单测 84 + 后端 339 + E2E 13）全部通过，契约行为已实现。真实 LLM 观感项待人工复核清单确认后方可 archive。
