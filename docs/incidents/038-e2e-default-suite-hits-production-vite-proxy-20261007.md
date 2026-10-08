# 038: E2E 默认套件打穿到生产——vite 代理默认 8000 + reuseExistingServer 复用生产后端（2026-10-07）

## 症状

2026-10-07 晚，worktree 内以改端口副本（后端 8005/前端 5178）跑 E2E 默认套件，
门禁大面积红（12 failed，含 smoke 的 `/api/test/seed` 57ms 内 404）。
排查发现**全部请求经 vite 代理打进了生产容器（宿主 8000）**：

- 生产 `data/sessions.db` 当晚新增 33 个 E2E fixture 会话（`测试问题A/B-<epoch>-<rand>`、
  `AGUI通道对话流测试`、`深度分析600519`、`分析一下宁德时代` 等命名特征），
  含真实 LLM 消耗的 quick chat 与深度分析（均 failed/interrupted/clarifying，无 completed）；
- Langfuse 生产项目新增对应 trace；
- `predictions` 表零污染（E2E 流量全为 chat/analysis 会话，未触发观点落库挂点）。

回溯证据：**10-03 深夜 22:25–22:53 已有同型五波垃圾会话**（同 fixture 命名、同形态）——
本 footgun 至少已发生两次以上，非首次。09-14 另有一例 completed 的 `深度分析600519`。

## 根因（四层叠加，复现与污染各需其中若干层）

1. **vite 代理默认 `http://127.0.0.1:8000`**（`frontend/vite.config.ts:14`
   `process.env.VITE_API_TARGET || 'http://127.0.0.1:8000'`）。默认 E2E config
   （`tests/e2e/playwright/playwright.config.ts`）的 webServer 不设 `VITE_API_TARGET`，
   靠「后端恰好在 8000」这一端口巧合成立——track-record/timeline 专属 config 均显式
   设置 `VITE_API_TARGET`（:55/:82/:102），唯独默认 config 缺失。
2. **`reuseExistingServer: !process.env.CI` + 健康检查只探活性**：本地跑默认套件时，
   生产容器占 8000 → `GET /api/health` 200 → playwright 认为「服务已在」直接复用
   ——**复用的是生产后端**，且前端代理也指向它。于是整套 E2E 以真实 LLM
   对生产执行：建会话、发消息、触发深度分析。
3. **部分 spec 硬编码 `API_BASE = http://localhost:8000`**（smoke.spec.ts:15,23、
   agui-chat.spec.ts:21、session-switch-resumption.spec.ts:19 直写；
   concurrent-streaming-integrity.spec.ts:33 留了 `E2E_API_BASE` env 覆盖但默认仍是
   8000）——这些 spec 的 `request` 直连不经 vite 代理，**无论 config 端口怎么改，
   直连流量永远打 8000**。端口改移（8005/5178）跑隔离栈时，
   浏览器流量走隔离后端而 `request` 流量打生产，产生「同一用例两套数据」的
   隐性错乱（smoke seed 404、agui 详情读错库、并发流式 A/B 深度分析建在生产）。
4. **`.env` 沿目录树向上泄漏**：`api.py:29 load_dotenv()` 的 dotenv 查找会从
   `src/finance_agent/` 向上走父目录——worktree 自身无 .env，但 `.worktrees/<x>/`
   的上一层即主检出的 `.env`（生产配置，含 `COHORT_ENABLED=1` 与真实 LLM key）。
   启动钩子 `bootstrap_cohort_from_env`（ops/model.py:204）把 `COHORT_ENABLED=1`
   一次性种进 E2E 新库 → eval-ops 用例「默认未开启」前置必崩
   （本次以 `COHORT_ENABLED=0` 显式覆盖验证：eval-ops 5/5 转绿，机制实锤）。

当晚诱因：worktree 内为避开生产端口改了后端端口（8000→8005），后端侧隔离成功，
但 vite 代理默认与 spec 硬编码两个 8000 通道仍在——「浏览器流量隔离 + 直连流量
打生产」的混合态比全打生产更隐蔽（smoke seed 404 是唯一显性破绽）。

## 影响面

- 生产会话列表污染（本次 33 个，已删除；10-03 批次约 60+ 个待清理）；
- 真实 LLM token 消耗（quick chat + 深度分析启动，后者均止步 clarifying/interrupted）；
- Langfuse 生产 trace 污染（无法按会话批量清除）；
- `predictions`/`equity_curve`/`agent_metrics_daily` 零污染（已核验当晚 0 新增）；
- E2E 门禁读数不可信（对生产跑出的通过率无意义）。

### 为什么长期未被发现

- 失败模式是「部分测试红」而非「全红」：流式/会话类测试对生产也能跑通大半
  （生产是真后端），只有依赖 TESTING 路由的用例（seed/eval-ops）必红；
- 本机开发流程常驻生产容器（docker compose），8000 恒被占用 →
  本地跑默认套件**必然**走复用分支（「整套对生产跑」自洽且大概率绿——
  10-07 #249 验证报告的「默认套件 27 passed 全绿」即为此态，
  门禁读数对被测分支零效力）；
- 改端口隔离时混合态的红（seed 404 等）易归因为 flaky；
- E2E 与生产共用 localhost，无任何「当前打的是哪个后端」的显式标识。

## 处置

- 当晚：删除窗口内 33 个垃圾会话（21:15–22:10 + fixture 特征双过滤，保留用户真实会话）；
  杀掉 8005/5178 孤儿 webServer；worktree 临时 config 补
  `VITE_API_TARGET: 'http://127.0.0.1:8005'` 后重跑门禁（隔离恢复）。
- 最终门禁改在「停生产前后端容器（确认 0 running）→ 默认端口原生跑 → 立即恢复」
  下完成：默认套件 24 passed / 9 skipped（@live 按设计）/ 2 failed；
  2 失败为根因 ④（.env 泄漏种入 cohort 开关），以 `COHORT_ENABLED=0`
  显式覆盖复验 eval-ops 5/5 全绿 → 等效 26 passed / 0 failed。
- 10-03 批次垃圾会话（约 60+，同 fixture 特征）留待 owner 决断后批量清理
  （同款 DELETE /api/sessions/{id} 脚本，时间窗 2026-10-03T22:25–22:55）。

## 预防（待办 → issue）

1. **默认 config webServer 显式设置 `VITE_API_TARGET`**（对齐 track-record/timeline 先例）；
2. **spec 硬编码 API_BASE 收编**：smoke/agui-chat/session-switch-resumption 改用
   `process.env.E2E_API_BASE ?? <默认>`（concurrent-streaming 已是该形态），
   或统一走相对路径经 vite 代理；
3. **reuseExistingServer 加模式核验**：复用前检查 `/api/health` 返回体中的 TESTING
   标识（health 端点返回 `{status, mode}`），非 testing 后端拒绝复用并显式报错——
   防止任何形式的「E2E 静默打生产」；
4. **.env 隔离**：E2E 后端启动显式禁用 dotenv 父目录查找（或 worktree 放置空 .env
   截断 find_dotenv 上行），防主检出生产配置泄漏进测试进程；
5. 考虑 E2E 前端注入显式标识（页面角标「E2E 测试环境」），人工核对层面兜底。

## 关联

- incident 031（pytest 侧测试泄漏生产库，同一「默认不安全」主题的 E2E 侧变体）；
- incident 013（DB 环境变量隔离原则）。
