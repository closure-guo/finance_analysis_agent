# 人工验证报告: adopt-assistant-ui-chat

**日期**: 2026-08-30
**验证人**: ZCode agent（GUI 自动化实测，STUB 确定性数据）
**关联 delta**: openspec/changes/adopt-assistant-ui-chat/
**E2E 门禁**: 不适用（e2e/ 基建 P1–P4 未落地，门禁尚未生效；见异常记录 2）

## 验证环境

- 后端：`TESTING=1 STUB_SCENARIO=pipeline SESSIONS_DB_PATH=data/e2e-sessions.db uvicorn`（stub LLM 确定性流式）
- 前端：vite dev server（5173），真实浏览器（Chromium 1440×900）GUI 实测

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 深度流式：user 气泡 + 思考折叠卡 + 工具卡 loading→完成 | 否 | token 渐进渲染，横幅按 agent 时序排列 | 「宁夏建材」→ 思考卡（思考中→思考已完成）→ [识别股票] 卡（执行中→↳ 已识别：贵州茅台） | ✅ |
| 管线时间线（data-pipeline 部件） | 否 | PipelineCard 分层时间轴/ETA/各 Agent 阶段时序 | pipeline-timeline 渲染完整，nodeTimelines 按角色分组（Trader/风控等） | ✅ |
| 报告卡（data-report 部件）+ 导出入口 | 否 | 报告 Markdown/图表区/免责声明/报告名+全部文件横幅 | 全部渲染；导出横幅位于视口尾部与原位置一致 | ✅ |
| 滚动跟随/上翻暂停 | 否 | 流式跟随底部；上翻后停在当前位置 | 模拟上翻后视口停在管线 nodeTimelines 区域 | ✅ |
| 刷新恢复（重建路径） | 否 | completed 会话经 rebuild 后消息完整经 Thread 渲染 | reload 后 user 气泡/工具卡/时间线/报告/导出横幅全部恢复 | ✅ |
| Composer：Enter 发送、模式切换开新会话 | 否 | 快速模式切换后回空态，发送走 AG-UI 通道 | 切换成功；quick 首条消息发送、run 结束指示器消失 | ✅ |
| 思考折叠卡展开 | 否 | 完成后收起、点击展开 | 展开后内容可见（opacity=1） | ✅ |
| 运行中停止按钮可见 | 否 | 流式中「停止生成」可用 | 深度流式中停止按钮出现（点击中断路径由 quickThreadGuards/streamStore 单测覆盖） | ✅ |
| 运行中拦截 toast / 发送键变停止 | 是（单测） | runtime 状态判定：Composer 运行中变 Cancel | composerRunning 对齐 isSessionRunning 语义（selectSession 恢复态回归由单测覆盖） | ✅（单测） |
| 消息 hover 操作（复制/重新生成） | 否 | hover 显示操作条；重新生成重发前驱 user 查询 | hover 出现「复制/重新生成」；点击重新生成 → 新 run 启动（POST /api/analyze） | ✅ |
| 中断保留已生成内容 | 否 | 停止后已生成内容不消失不回退 | 停止后旧报告/旧工具卡/追问气泡全部保留，停止按钮收口 | ✅ |
| LLM 报告内容质量 | 否 | — | STUB 数据无主观项可验证；真实 LLM 质量验证需真钥匙环境 | ⏭ 不适用 |

## 实施偏差说明

1. **Task 1.1（官方模板参考实现）**：未单独执行 `npx assistant-ui create -t langgraph`。基座由前一 change（add-assistant-ui-thread）已奠定：`@assistant-ui/react@0.15.17` 已入仓、QuickThread 已用官方原语建立实现范式。本 change 沿用同一策略（直接基于 ThreadPrimitive/ComposerPrimitive/useExternalStoreRuntime 自建，源码位于 `frontend/src/chat/`），组件搬运（Task 1.2）以 `AnalysisThread.tsx` + `adapter.ts` 承载。
2. **E2E 门禁（Task 5.3）**：`e2e/` Playwright 基建（P1–P4）尚未建设，门禁未生效。既有 399 项前端单测（含 App 级交互流）全绿作为本次回归证据。

## 异常记录

1. Playwright locator 点击在 IAB 环境对动画元素超时——验证工具兼容性问题，非产品缺陷（DOM evaluate 交互正常）。
2. STUB_SCENARIO=pipeline 下 quick 通道回复存在「STUB 深度分析完成」文本重复——复现于 add-assistant-ui-thread 既有行为（thinking_to_answer 与 chat_token 叠加），非本 change 引入；建议在 quick 通道专项排查。
3. 验证期间本机 docker compose 后端（0.0.0.0:8000）与验证 stub（127.0.0.1:8000）并存，stub 重启间隙出现请求路由到 docker 旧库导致侧边栏显示陈旧会话——环境污染，非产品缺陷；已用干净 stub 重跑受影响用例（hover 操作/重新生成/中断保留）。

## 结论

[x] 核心交互路径全部通过（stub 确定性数据 + 真实浏览器 GUI 实测）
[ ] E2E 门禁待基建落地后补充执行（Task 5.3 未勾选）
