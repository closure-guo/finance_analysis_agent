# Design: add-agent-settings-center

## Context

系统目前的"设置"是 LLM 配置弹窗 `SettingsModal`（`frontend/src/App.tsx`），能力已完整（provider 预设、model/base_url/api_key/thinking/apiForm、模型发现、连通性测试 + capability probe、多 profile）。LLM 配置采用"前端 localStorage profile + 每次请求随 `llm_config` 下发覆盖 env 兜底"模型，后端无配置存储、无热加载（`llm/resolver.py` 每次实时解析；`.env` 仅 import 时 load_dotenv 一次）。

缓存为两级：`DataCache`（SQLite `cache.db`，WAL，`data/cache.py`，2026-09-08 已统一为共享单例 `get_shared_cache`）+ `llm/probe_cache.py`（能力探测内存缓存）。缓存仅提供 `keys()/delete()` 原语，无 stats/clear/HTTP 端点，TTL 惰性过期（`nodes/fetch.py:211-268` 字面量）。会话库在 `data/sessions.db`（`session_store.py`），仅单会话删除；前端无"清空全部"。

前端为轻量 pathname 路由（`route.ts` + `App.tsx:882-898` 分支），无 react-router。系统无鉴权。工作树对 `data/cache.py`、`nodes/cache.py`、`nodes/fetch.py` 已有未提交改动，本设计构建在其之上。

## Goals / Non-Goals

**Goals:**
- 提供 `/settings` 设置中心页（左侧垂直导航布局，已与用户可视化确认），聚合六大分区，成为设置唯一入口。
- 将 `SettingsModal` 弹窗整体迁移为页内「LLM 配置」分区，行为语义不变；三处弹窗入口改为跳转/定位设置页。
- 新增缓存管理、会话管理（清空全部）、运行环境与关于、数据源监控、战绩展示偏好五个分区。
- 后端新增最小、只读/显式清理的端点，不改变现有分析/聊天主链路语义。

**Non-Goals:**
- 不为 LLM 配置引入服务端持久化/全局热加载（维持"请求级覆盖 + env 兜底"现状；`llm-config` 语义迁移不改变该模型）。
- 不做缓存命中率等侵入式全量指标埋点（数据源监控为计数器级 v1，不改 fetch 重试/降级/回退逻辑）。
- 不改战绩/净值数据的计算与存储，仅消费展示偏好。
- 不引入登录鉴权/权限层。

## Decisions

### D1: 设置中心页采用独立 `/settings` 路由 + 左侧垂直导航
沿用现有 pathname 分支模式（`App.tsx:882-898` 加 `/settings` case，`route.ts` 无需改），侧栏/header 设置入口由 `setShowSettings(true)` 改为 `navigate('/settings')`。左侧固定模块列表（LLM 配置/缓存管理/会话管理/运行信息/数据监控/战绩展示偏好），右侧内容区按选中模块渲染。**理由**：扩展性最好（未来加模块只加一项），与 `/downloads`、`/track-record` 同模式，改造可控。**替代**：顶部页签（6 项过挤）、单页锚点（页面过长）——已用可视化草图排除。

### D2: SettingsModal → 页内「LLM 配置」分区（组件复用而非重写）
将 `SettingsModal` 的主体（表单字段、provider 预设、模型发现、连通性测试、多 profile）抽为可复用组件（如 `LlmConfigPane`），嵌入设置页分区；删除弹窗外壳与 `showSettings` 状态。无 profile 强制配置流程（`App.tsx:578/1404/2319`）改为 `navigate('/settings')` 并定位到「LLM 配置」分区（通过 query/hash 或初始 activeModule 状态）。**理由**：避免双份 UI 与逻辑漂移，符合"弹窗整体迁移"。**风险**：强制配置流程涉及多处调用点，需逐一迁移并 E2E 覆盖。

### D3: 缓存管理 = 后端新增统计/清理端点 + 前端分区
在 `DataCache` 上补充：`stats()`（按 data_type 聚合计数、最早过期、占用估算）、按类别/按代码前缀枚举删除、全清；`probe_cache` 暴露 `clear()/stats()`。后端新增：
- `GET /api/cache/stats`（数据缓存 + 能力探测缓存概览）
- `POST /api/cache/clear`（body：`{scope: 'type'|'code'|'all', type?, code?}`，全清需 `confirm: true` 令牌）
- `POST /api/cache/probe-cache/clear`
**理由**：`cache.db` 键为 `{code}:{type}` 前缀约定，按 code/type 删除可行；全清高危以显式确认令牌防护。**替代**：只读监控不清理（与用户"缓存管理"诉求不符，已排除）。

### D4: 数据源监控 = 计数器级 v1，非侵入
在 `DataCache` 内维护进程内命中/失败计数（HIT/MISS/错误），并暴露每条目 `expire_at`（新鲜度）与最近失败；新增 `GET /api/data-source/status` 返回聚合（命中/未命中/失败、各 code 数据新鲜度）。不改 `nodes/fetch.py` 的重试/降级/回退逻辑。**理由**：满足用户对数据监控的诉求，同时把对核心拉取链路的侵入降到最低。**替代**：全量埋点+持久化指标（侵入大，后置）。

### D5: 战绩展示偏好 = localStorage 存储 + 战绩页消费
偏好存 `localStorage`（key `fa_track_prefs`），字段：`timeSpan`、`benchmark`、`drawdownThreshold`、`navChartForm`。战绩页（`pages/trackRecord/*`）读该偏好并应用到默认区间、基准对比、回撤警示阈值、净值图形态。**理由**：与既有模式（`fa_theme`、`fa_llm_profiles`）一致，纯展示层，零后端改动，可独立 TDD 测试。**风险**：基准对比需确认 track-record 是否有可对比基准数据；若无，该偏好项降级为"待接入"或明确空实现并在 tasks 标注。

### D6: 清空全部会话 = 后端批量删除端点 + 设置页会话管理分区
后端新增 `POST /api/sessions/clear-all`（级联删除 sessions + session_events），前端「会话管理」分区提供"清空全部会话"按钮（二次确认），清空后回到首页空态。单会话删除语义不变。**理由**：与缓存全清同属"数据管理"直觉，且复用 `session_store.py` 既有级联删除逻辑。

### D7: 运行环境与关于 = 只读 run-info 端点 + 只读分区
后端新增 `GET /api/run-info`（只读：默认 model/base_url/thinking、健康状态、Langfuse 地址、git commit/版本；**绝不含 apiKey**，沿用 `GET /api/llm-config` 的不回显约束）。前端「运行信息」分区纯展示。**理由**：轻量、无副作用。

## Risks / Trade-offs

- **强制配置流程迁移遗漏** → 迁移时逐一核对三处强制弹出点（`App.tsx:578/1404/2319`）并加 E2E/人工验证覆盖"无 profile 时发送被引导到设置页"。
- **缓存清理并发/锁** → `DataCache` 已有 `RLock` 串行化；全清/统计复用同一把锁，避免与写线程竞态。多 worker 部署下单例语义需复核（现状约定单 uvicorn worker）。
- **数据源监控计数准确度** → 进程内计数器随进程重启清零，仅作近期视图；spec 明确为"近程/会话内聚合"，不做持久化承诺。
- **基准对比无数据** → D5 的 `benchmark` 项可能暂无基准序列；tasks 标注需先确认 track-record 是否有可对比基准，否则该项留空实现并披露。
- **API Key 安全** → 任何新增端点均不回显 apiKey；run-info 沿用现有约束。这是硬约束，写入 spec。
- **交互类变更范围大** → 涉及前端 UI/路由/状态流转，走 project-workflow §3 完整管线；若 e2e/ 基础设施已就绪则 E2E 门禁适用，否则按 §4.5 生效状态豁免并落人工验证报告。

## Migration Plan

1. 后端端点优先（可独立 TDD）：`DataCache.stats/clear`、probe_cache clear、`/api/cache/*`、`/api/sessions/clear-all`、`/api/run-info`、`/api/data-source/status`——全部新增，不破坏既有端点。
2. 前端：抽 `LlmConfigPane` 复用组件 → 建 `/settings` 页壳与左侧导航 → 迁入各分区 → 移除 `SettingsModal` 与三处弹窗入口 → 战绩偏好接入。
3. 无数据迁移；`cache.db`/`sessions.db` 结构不变（仅新增只读/清理方法）。
4. 回滚：新增端点与页面为增量，可单独回退前端 `/settings` 分支；若需退回弹窗，保留 `LlmConfigPane` 复用即可重建 `SettingsModal`。

## Open Questions

- track-record 是否已有可对比基准指数序列（影响 `benchmark` 偏好项的落地深度）——实现期核实，未核实前该项以"可配置、接入待确认"实现并在 tasks 标注。
- 数据源监控的"最近失败"来源（fetch 异常是否已有结构化记录）——实现期在 `nodes/fetch.py` 错误分支补计数（不改重试/降级逻辑）。
