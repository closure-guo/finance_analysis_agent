# Tasks: add-agent-settings-center

## 1. 后端：缓存统计与清理

- [x] 1.1 DataCache 补充 `stats()`（按类别聚合条目数/占用/最早过期/待清数）、按类别与按代码前缀删除、全清，复用既有 RLock 串行化
- [x] 1.2 probe_cache 暴露 `clear()` 与 `stats()`
- [x] 1.3 `GET /api/cache/stats` 返回数据缓存 + 能力探测缓存概览（含 per-type 明细）
- [x] 1.4 `POST /api/cache/clear` 支持 `scope=type|code|all`；`all` 需 `confirm` 令牌否则 4xx
- [x] 1.5 `POST /api/cache/probe-cache/clear` 清除能力探测缓存

## 2. 后端：会话 / 运行信息 / 数据监控端点

- [x] 2.1 session_store 补充清空全部会话（级联删 sessions + session_events），`POST /api/sessions/clear-all`
- [x] 2.2 `GET /api/run-info` 只读返回默认 model/base_url/thinking、健康状态、Langfuse 地址、git 版本/commit；响应不含 apiKey
- [x] 2.3 DataCache/fetch 补命中/未命中/失败计数（非侵入，不改重试/降级/回退逻辑）
- [x] 2.4 `GET /api/data-source/status` 返回计数 + 数据新鲜度列表（含已过期标记）

## 3. 前端：设置中心页骨架与入口迁移

- [x] 3.1 App.tsx 路由分支加 `/settings`；侧栏 gear / header 设置入口由弹窗改为 `navigate('/settings')`
- [x] 3.2 新建 `pages/settings` 设置中心页：左侧垂直导航 + 右侧内容区，默认激活「LLM 配置」分区
- [x] 3.3 抽 `LlmConfigPane` 复用组件并嵌入「LLM 配置」分区；移除 `SettingsModal` 及三处弹窗入口（含无 profile 强制配置改跳转 `/settings` 并定位 LLM 分区）

## 4. 前端：各分区

- [x] 4.1 缓存管理分区：汇总统计条 + 类别表格（每类可清空）+ 按代码清理 + 全部清空（输入「清空」确认）+ 能力探测缓存一键清除
- [x] 4.2 会话管理分区：展示会话总数 + 「清空全部会话」（二次确认）→ 调 `POST /api/sessions/clear-all`，清空后回空态
- [x] 4.3 运行信息分区：只读渲染 `GET /api/run-info`
- [x] 4.4 数据监控分区：命中/未命中/失败计数卡 + 新鲜度列表（含加载/错误态）
- [x] 4.5 战绩展示偏好分区：默认时间跨度 / 对比基准指数 / 回撤警示阈值 / 净值图形态存 `fa_track_prefs`，trackRecord 三页消费应用
- [x] 4.6 LLM 切换下拉框加「LLM 配置…」分隔项，点击跳转 `/settings` 定位 LLM 分区且不改变激活 profile

## 5. 验证

- [x] 5.1 后端单元/集成测试覆盖缓存统计与清理、`clear-all`、`run-info`、`data-source/status`
- [x] 5.2 前端测试覆盖设置页路由/导航、各分区交互、战绩偏好持久化与消费
- [x] 5.3 E2E spec 覆盖核心交互场景（设置页可达、导航切换、全清确认、强制配置引导）；若 e2e/ 基础设施未落地（P1–P4 未完成）则按 project-workflow §3 Step 4.5 豁免并记入人工验证报告
- [x] 5.4 人工验证报告落 `tests/validation/`（含设置页各分区与交互截图证据）
