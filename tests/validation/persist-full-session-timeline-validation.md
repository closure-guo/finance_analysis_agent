# 人工验证报告：persist-full-session-timeline

> 日期：2026-07-29 ｜ 验证人：____（待人工执行）
> 变更：`openspec/changes/persist-full-session-timeline/`
> 前置：`resume-pipeline-across-sessions` 已落地
> 验证方式：单测 + E2E（TESTING=1 stub）自动通过；真实 LLM 全链路需人工复核（见 §3）

## 1. 验证范围

| 项 | 契约来源 | 验证方法 | 结果 |
|----|----------|----------|------|
| session_store：pipeline_timelines 列 + append_chat agentTimeline | design §D3 / Task 1 | `test_session_store.py` | 自动通过 |
| _ChatCollector 构建结构化 agentTimeline（镜像前端语义） | design §D2 / Task 2 | `test_timeline_builder.py`（69 用例） | 自动通过 |
| 管线 thinking 按 node 持久化（fast path + ReAct） | design §D3 / Task 3 | `test_pipeline_runner.py` + `test_react_pipeline_snapshot.py` | 自动通过 |
| 管线 search/tool 按当前运行节点归属（fast path） | Task 3（用户决策） | `test_pipeline_runner.py` | 自动通过 |
| 前端 deserializeTimeline/deserializeNodeTimelines | design §D4 / Task 4 | `deserializeTimeline.test.ts` | 自动通过 |
| selectSession 结构化恢复（chat agentTimeline + 管线 nodeTimelines） | design §D4 / Task 5 | `selectSession.test.tsx` | 自动通过 |
| 切换会话后思考/搜索/工具/管线时序完整恢复（E2E stub） | Task 6.3 | `persist-full-session-timeline.spec.ts`（3 用例） | 自动通过 |
| 旧会话向后兼容（无新字段回退近似） | design §D4 / Task 5 | E2E 用例 3 + 单测 | 自动通过 |
| 真实 LLM 下切换/关闭后全部恢复 | Task 6.4 | 本报告 §3 人工复核 | 待人工执行 |

## 2. 自动化验证记录

> 以下由单测 + E2E 自动跑出，人工验证人可据此聚焦 §3。

- 后端 pytest（相关模块）：`test_session_store` / `test_timeline_builder` / `test_pipeline_runner` / `test_react_pipeline_snapshot` / `test_testing_mode` 全绿（125+ 用例）。
- 前端 vitest：133 全绿；`npx tsc --noEmit` 无错误；`ruff check src/ tests/` 全绿。
- E2E（`playwright.timeline.config.ts`，后端 8002 / 前端 5175，TESTING=1 stub）：
  - 用例 1「对话时序恢复：思考/搜索/工具调用横幅按交错顺序渲染」—— PASS
  - 用例 2「管线时序恢复：报告 + 分层时间轴 + 节点分组下思考/搜索/工具内容」—— PASS
  - 用例 3「向后兼容：仅 thinking + tool_calls 旧会话正常恢复」—— PASS
- 既有 E2E 不回归。

## 3. 人工复核清单（真实 LLM 全链路）

> 前置：`docker compose up -d` 启动全栈（FastAPI 8000 + Vite 5173 + Langfuse 3000）。
> 目标股票任选一只 A 股（如 600519）。操作期间保持后端日志与 Langfuse 面板可见。

### 3.1 对话时序完整恢复（思考/搜索/工具调用）

操作步骤：

- [ ] 1. 前端切「深度研究」模式，输入「深度分析600519」发送，等待澄清/分析阶段产生思考、网络搜索、工具调用（观察在线时的交错时序）。
- [ ] 2. 记录在线时的时序顺序（思考→搜索→再思考→工具调用）。
- [ ] 3. 点击侧边栏另一个会话切走，再切回本会话。

观察点：

- 切回后思考横幅、搜索横幅（query + 结果）、工具调用横幅**均可见且按原交错顺序**（非「思考在前、工具在后」拍平）。
- 搜索横幅独立于工具调用横幅（web_search 走 search item，不归入 tool_call）。
- 与在线时记录的顺序一致。

### 3.2 管线时序完整恢复（各节点思考/搜索/工具）

操作步骤：

- [ ] 1. 同 3.1 发起深度分析，等待管线运行（分层时间轴出现）。
- [ ] 2. 管线完成后（报告出现），点击侧边栏另一个会话切走，再切回。

观察点：

- 报告可见、分层时间轴可见。
- 各节点分组标题（如「Trader」「研究经理」「多头分析师」）下，该节点的思考/搜索/工具调用记录可见。
- 数据库（可选）：`SELECT pipeline_timelines FROM sessions WHERE session_id=...` 确认为 `{node: [...]}` 结构且非空。

### 3.3 关闭页面后恢复

操作步骤：

- [ ] 1. 完成 3.1/3.2 后，直接关闭浏览器标签页。
- [ ] 2. 重新打开前端，从侧边栏点击该会话。

观察点：

- 对话时序与管线时序均完整恢复（同 3.1/3.2 观察点）。

## 4. 已知限制

- **ReAct 路径管线 search/tool 归属不可达**：管线节点的 search/tool 事件不在 `run_deep_analysis` 工具的 custom/updates 流内（仅 thinking 可归属节点）。fast path（PipelineRunner）search/tool 按当前运行节点归属正常。真实深度分析走 fast path 时管线 search/tool 完整；ReAct 路径仅 thinking 按节点持久化。详见 `agent_factory.py` 局限注释与 tasks.md 3.2。
- **旧会话不回溯**：仅新会话（本 change 部署后产生）具备结构化时序；旧会话回退拍平近似恢复（不报错）。
