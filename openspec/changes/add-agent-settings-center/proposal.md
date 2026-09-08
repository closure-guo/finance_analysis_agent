# Proposal: add-agent-settings-center

## Why

系统现有的"设置"是一个 LLM 配置弹窗（`SettingsModal`），LLM 编辑能力已完整实现但入口零散（header 按钮 / 侧栏 gear / 无 profile 强制弹出），且缓存、会话、运行状态等运维信息完全没有 UI 可查。需要一个统一的设置中心页，把 LLM 配置升级为页面分区，并聚合缓存管理、会话管理、运行信息、数据源监控、战绩展示偏好等能力，形成单一、可扩展的设置入口。

## What Changes

- **设置中心页（/settings）**：新增独立路由页，采用左侧垂直导航 + 右侧内容区布局，聚合六大模块分区；header/侧栏「设置」入口由弹窗改为跳转 `/settings`，删除 `SettingsModal` 弹窗形态。
- **LLM 配置迁入页面**（`llm-config` 语义迁移，非新能力）：设置面板由弹窗改为页内「LLM 配置」分区，字段/预设/模型发现/连通性测试/多 profile 能力原样保留；无 profile 强制配置流程由弹窗改为跳转设置页并定位到该分区。
- **LLM 选择下拉框新增「LLM 配置…」项**：以分隔线与 profile 列表隔开，点击跳转设置页（增强可达性）。
- **缓存管理**（新能力）：数据缓存 `cache.db` 与能力探测缓存（内存）的统计与清理——统计（总条目/占用/已过期待清/最近命中）、按类别清空、按股票代码清空、全部清空（高危，需输入「清空」二字确认）、能力探测缓存一键清除；后端新增统计/清理端点。
- **会话历史管理**（`session-persistence` 扩展）：新增"清空全部会话"能力（现有仅单会话删除），后端补批量删除端点；设置页设「会话管理」分区。
- **运行环境与关于**：只读展示后端默认 LLM 配置（model/base_url/thinking，apiKey 不回显）、健康状态、Langfuse 地址、git 版本/commit；新增只读运行信息端点。
- **数据拉取/数据源监控**（新能力，非侵入 v1）：后端对数据缓存命中/失败计数、暴露数据新鲜度（过期时间）与最近失败；设置页「数据监控」分区展示；不改动 fetch 重试/降级逻辑。
- **战绩展示偏好**：设置页「战绩展示偏好」分区，提供默认时间跨度、对比基准指数、回撤警示阈值、净值图默认形态四项偏好，存浏览器 localStorage，战绩页（/track-record、校准页、详情页）消费生效。
- **BREAKING（前端 UI 层）**：`SettingsModal` 弹窗移除、三处弹窗入口（header / 侧栏 gear / 强制配置）改为跳转/定位设置页。

## Capabilities

### New Capabilities
- `settings-center`: 设置中心页（/settings 路由、左侧垂直导航、模块聚合）、设置入口由弹窗迁移为跳转页面、运行环境与关于分区（含只读 run-info 端点）、会话管理分区（新增"清空全部会话"及后端批量删除端点；单会话删除语义不变）、战绩展示偏好分区（localStorage 存储与消费）。
- `cache-management`: 数据缓存（cache.db）与能力探测缓存（内存）的统计与清理——统计端点、按类别/按代码/全部清空（全清输入「清空」确认）、能力探测缓存一键清除、前端缓存管理分区。
- `data-source-monitoring`: 数据源拉取命中/新鲜度/最近失败监控——后端计数器与查询端点、前端数据监控分区（非侵入 v1，不改 fetch 重试/降级）。

### Modified Capabilities
- `llm-config`: 设置面板由弹窗迁移为设置中心页内「LLM 配置」分区；无 profile 强制配置流程由弹窗改为跳转设置页并定位该分区（字段/预设/发现/测试/多 profile 行为语义不变）；LLM 切换下拉框新增「LLM 配置…」分隔项（跳转设置页）。

## Impact

- **后端**：`src/finance_agent/api.py`（新增缓存统计/清理、会话批量清空、run-info、数据监控端点）；`data/cache.py`（统计/按前缀删除/全清/过期 GC 辅助，构建在 2026-09-08 已统一的共享单例 `get_shared_cache` 之上）；`nodes/cache.py` 与 `nodes/fetch.py`（命中/失败计数，注意工作树已有未提交改动，需在其上增量）；`llm/probe_cache.py`（暴露 clear/统计）；`session_store.py`（批量删除）。
- **前端**：`frontend/src/App.tsx`（路由分支加 `/settings`、侧栏/header 入口迁移、删除 SettingsModal、强制配置流程改造）；新增 `pages/settings/*`；`llmConfig.ts`（LLM 下拉分隔项）；`route.ts`（无需改，沿用 pathname 模式）；trackRecord 三页（消费战绩展示偏好）。
- **契约**：新增/修改 OpenSpec 能力 spec（settings-center / cache-management / data-source-monitoring / llm-config / session-persistence）。
- **交互类变更**：涉及前端 UI、状态流转 → 走 project-workflow §3 完整管线（含 E2E 门禁，若 e2e/ 基础设施已就绪则适用，否则按 §4.5 生效状态豁免并落人工验证报告）。
- **无鉴权**：系统无登录鉴权，设置页/缓存/会话操作无需权限层；apiKey 仍绝不在服务端存储或回读。
