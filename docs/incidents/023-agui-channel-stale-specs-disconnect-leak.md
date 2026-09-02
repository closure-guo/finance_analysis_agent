# Incident 023: quick 通道迁移遗留三大共振 — 旧 spec 确定性全红 + 断连状态泄漏 running + 「flaky」错误归因

**日期**: 2026-09-01
**环境**: GitHub Actions ubuntu-latest（2 worker）/ Windows 本地 / TESTING=1 stub 后端 + vite dev
**影响**: CI stub 套件自 #93（add-assistant-ui-thread，2026-08-30）合入起连续 10 次
运行全红；timeline 套件同被打破但被 stub 套件挡枪从未暴露；生产侧 quick 会话
流式中断连后会话永久 `running`，被「该会话正在生成中」守卫锁死。
**状态**: 已修复（[PR #101](https://github.com/closure-guo/finance_analysis_agent/pull/101)，
stub 套件转绿）；timeline 套件为遗留修复面，另行处理

## 现象

- 用户报「最近几个 PR CI 有 fail」，初步归因「stub flaky 聚类（~60% 失败率、
  spec 轮换超时）」并准备以 CI 串行化（workers:1）修复
- 实证推翻：失败集恒定（contract / streaming×4 / interaction / debug-cursor /
  downloads:42），单 spec 隔离运行同样确定性失败——**不是 flaky，是断裂**
- 修复 spec 后 E2E 进一步暴露：quick 会话流式中切换会话（触发 abortRun），
  会话状态永久停留 `running`（45s+ 轮询不收敛，数分钟后仍 running），
  第二轮追问不落库，该会话之后无法发送

## 根因（三层叠加）

**层 1（CI 全红的直接根因：通道迁移没带走旧 spec）**：#93 起 quick 模式对话
改走 assistant-ui Thread + `POST /api/agui/quick`（AG-UI RunAgentInput → SSE），
旧 `/api/chat` 通道仅服务深度模式。contract/streaming/interaction/debug-cursor
四个 quick 模式 spec 仍等待 `/api/chat` 请求与 `stream-output`/`stream-status`
断言，永不命中 → 确定性 30s 超时。downloads:42 断言的 `Finance Analysis Agent`
标题在 Kimi 风格改版后已不存在（现为「今天想研究什么？」）。两批 UI 变更
（#93 通道迁移 + Kimi 改版）均未同步更新既有 E2E，且带红合并。

**层 2（后端真 bug：GeneratorExit 断连路径绕过终态落库）**：
`src/finance_agent/agui/endpoint.py` 的 `_agui_run_stream` 只在
`except asyncio.CancelledError`（中断落库 + interrupted）与
`except Exception`（failed）两条路径更新会话状态。但生产中断连经
vite 代理 + uvicorn 传播表现为 StreamingResponse **aclose**（向生成器注入
GeneratorExit，属 BaseException，不经任何 except），终态落库被整体跳过 →
会话永久 `running`。既有单测 `test_client_disconnect_persists_interrupted`
只覆盖了 task.cancel() 路径，aclose 路径从未有测试。此外已取消任务里
await 可能立即重抛二次取消，原 CancelledError 处理器中的落库 await 本身
也不可靠。

**层 3（诊断层面的失败：「flaky」叙事掩盖确定性断裂）**：
- 「同 commit 一过一挂」实为 push/PR 双事件触发的不同 commit 相邻运行
- 「后端同步 graph.stream 阻塞事件循环」实为误判：`api.py` 的
  `_stream_from_sync` 早已把同步生成器桥到 executor 线程；实测流式期间
  （8 路并发 SSE 过 vite 代理）health/files 延迟稳定 ~0.2s
- timeline 套件（10 挂/19 过，管线时间轴与横幅 DOM 断言）同被 #93 + Kimi
  改版打破，但因 stub 套件先死、job 内顺序执行，**从未运行过**，直到 stub
  转绿才首次暴露——挡枪效应让第二个修复面隐形了两天

## 排查方法（可复用）

1. **先分 flaky 还是断裂**：把 CI 失败 spec 单 spec 隔离跑（`--workers=1` 单文件）。
   隔离必挂 = 确定性断裂，直接排除并发归因，不要再往 workers/超时上修
2. **历史 run 二分**：`gh run list` 按时间排，找最后一个 green 与第一个 red 之间的
   合入（本案：8-29 全绿、#93 于 8-30 合入后全红），直接锁定肇事变更
3. **读源码验证阻塞假设**：对「事件循环被阻塞」类假设，先查是否已有 executor/
   to_thread 桥接，再用 curl 实测流式期间旁路 API 延迟，不要凭印象下结论
4. **E2E 断言后端状态时轮询终态而非断言即时值**：abort 传播、落库收敛都是
   异步的，「立即等于某终态」的断言必然抖动

## 修复

1. E2E spec 迁移（PR #101，5 个测试文件）：contract 改断言 AG-UI
   RunAgentInput 契约（threadId / 末条 user 消息 / forwardedProps.apiKey）；
   streaming/interaction 迁移到 `agui-stream-status`/`agui-assistant-message`；
   debug-cursor 重写为 AGUI 会话切换语义（重挂载 Thread、切回快照、游标
   不常驻 + 后端终态收敛轮询）；downloads EmptyState 标题断言更新
2. 后端兜底（PR #101，TDD）：`_agui_run_stream` 外层 finally 在
   `terminal_persisted=False` 时调度中断落库（覆盖 GeneratorExit 等一切
   BaseException 退出路径）；CancelledError 与兜底路径统一走
   `_schedule_interrupted_persist` detach 执行；补
   `test_client_disconnect_via_aclose_persists_interrupted` 钉死 aclose 路径
3. 废弃错误归因的 workers:1 改动（未合入）

## 遗留与防范

- **timeline 套件修复面**（persist-full-session-timeline / thinking-timeline×3 /
  pipeline-hierarchical / resume-pipeline-across-sessions 共 10 例）：同为
  通道迁移 + 改版遗留，需同类迁移，另行 PR
- **流程红线重申**：带红合并使两个 UI 变更各自打破一批 E2E 而无人在意；
  CI 红必须当日定责（断裂 or flaky），「retry 能过就算 flaky」是诊断终点
  而非结论
- **断连路径设计约束**：凡是 SSE 生成器做状态机落库，必须把「aclose /
  GeneratorExit / 二次取消」当作与正常终态同等地位的一等路径，单测需
  同时覆盖 cancel 与 aclose 两条断连路径
