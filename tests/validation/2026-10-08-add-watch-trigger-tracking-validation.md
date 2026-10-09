# 人工验证报告: add-watch-trigger-tracking

**日期**: 2026-10-08
**验证人**: controller (agent) · 待 owner 签字确认
**关联 delta**: openspec/changes/add-watch-trigger-tracking/（随 PR #262 合并入 main，squash commit b0233f45）
**E2E 门禁**: §5.6 Playwright 基建未建设（P1-P4 pending）——以 CI stub 套件 + 前端 vitest 契约（653/653）+ 本次真实管线端到端验证替代，delta tasks.md 已如实注记

## 验证环境

- 部署链：PR #262 squash 合并 → 主检出 pull（b0233f45）→ backend restart（src mount 生效）→ prompts 定向发布
- prompts：trader/risk_judge **v31**（预检拦截 → 指纹取证：production v30 == pre-#262 仓库版，仅陈旧非 UI 编辑 → `create_prompt` 定向覆盖，**勿 sync 收编** 处置律；发布后指纹 EXACT PASS）
- 验证标的：601066 中信建投，标准深度研究管线，真实 LLM（bigmodel glm-5.3）
- 会话：`b434aedf-83c`（2026-10-08 17:17，25 阶段，耗时 2:56）；报告 `reports/中信建投_601066_20261008_172046_report.md`

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| watch 终稿触发位齐备直通（agent-node-contracts） | vitest/单测 | LLM 首报即申报，无打回 | SSE 全程 0 次「打回」，final_trigger_check 无残留 note | ✅ |
| watch 决策渲染触发位行（report-decision-rendering） | 否（渲染质量人工看） | 「上破触发位: 23.57」「下破触发位: 22.63」结构化行，非文本回填 | 报告 ：126-127 两行数值与决策 JSON 一致；无「未申报」；reedal 文本与字段数值一致（23.57/22.63） | ✅ |
| 入池跟踪声明行 | 否 | FM approve 后渲染「已入池跟踪，按 20 交易日窗口结算」 | 报告 ：128 渲染正确 | ✅ |
| 数据真空提示行 | 否 | 间隔 ≤3 自然日不渲染 | 行情截止 10-08（当日），提示行未出现（符合预期） | ✅ |
| K 线前端触发位参考线（report-kline-chart） | vitest（markLine 正反用例） | 双向点线 + 「上破触发/下破触发」标签，与入场/止损/目标虚线可区分 | 浏览器截图 `2026-10-08-watch-trigger-tracking-kline.png`：橙/紫两条点线 + 右侧标签清晰可见，蜡烛位于两线之间（现价 22.75） | ✅ |
| predictions 触发位落库 + session_id（track-record） | 单测 | watch 行携带 trigger 值与 session_id；冻结 | `p_2f2d5230155c`: trigger_high=23.57 / trigger_low=22.63 / session_id=b434aedf-83c / direction=neutral / horizon=20——**三处数值完全一致** | ✅ |
| chart_data 采集携带（report-kline-chart） | 单测 | decision_levels 含 trigger 键 | `GET /api/sessions/b434aedf-83c` → price.decision_levels = {trigger_high: 23.57, trigger_low: 22.63} | ✅ |
| PNG 越界触发位 y 轴拉伸（Task 4 遗留观察点） | 否 | 越界时 y 轴撑大（与 entry/target 既有表现一致） | 本次触发位在 K 线范围内，未触发该形态；**留待后续越界场景抽查**，不阻塞 | ⚠️ 观察 |

## 附带收获

- 本次截图同时构成 **update-price-chart-kline（PR #247）的 K 线升级人工验证证据**：蜡烛图 + MA5/20/60 叠加 + 财报窗口标注渲染正常（该 delta 的对应验证项可引用本报告）。
- 引用校验系统在报告尾部正常渲染（claim 逐条「已验证」徽章，[55]-[59] 抽样可见）。

## 异常记录

- 无阻断异常。过程记录：部署预检按预期拦截（Langfuse production 陈旧），指纹取证后定向覆盖，全程未使用 sync 收编。

## 结论

- [x] 全部通过，可 archive（待 owner 在本报告签字 + delta tasks.md 剩余 E2E 注记项随 §5.6 基建落地后回填）
- [ ] 存在失败项，需修复后重新验证
