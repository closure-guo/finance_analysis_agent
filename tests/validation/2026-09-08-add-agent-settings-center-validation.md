# 人工验证报告: add-agent-settings-center

**日期**: 2026-09-09
**验证人**: [待用户签字]
**关联 delta**: openspec/changes/add-agent-settings-center/
**E2E 门禁**: 不适用（`e2e/` 基础设施未落地，P1–P4 未完成，按 project-workflow §3 Step 4.5 生效状态豁免）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 后端缓存统计/清理端点返回正确形状 | 否（未落地） | `/api/cache/stats`、`/api/cache/clear`（type/code/all+confirm）、`/api/cache/probe-cache/clear` 行为正确 | 6 个 API 用例 + 全部相关回归 84 通过；红线（apiKey 不回显、confirm 400）有专项测试 | ✅ |
| 会话清空（级联删事件）与 run-info | 否 | `/api/sessions/clear-all` 级联删除；`/api/run-info` 只读且不含 apiKey | session_store 10 用例 + API 用例通过；run-info 顶层无密钥字段断言 | ✅ |
| 数据源监控计数（非侵入） | 否 | check_cache/fetch 埋点不改重试/降级逻辑 | 15 节点用例通过，diff 纯增量零删除 | ✅ |
| 设置中心页路由与左导航 | 否 | `/settings` 可达、六分区切换、默认 LLM 分区 | settingsCenterPage 3 用例（含真实切换断言）通过 | ✅ |
| 设置入口迁移（弹窗→页面） | 否 | header/gear/EmptyState 跳转 `/settings`；无 profile 强制配置跳转定位 LLM 分区；SettingsModal 不再渲染 | 全仓无 `SettingsModal`/`showSettings` 残留（仅注释）；prop 改名 `onOpenSettings` 同步测试 | ✅ |
| LLM 配置迁页（LlmConfigPane） | 否 | 字段/预设/模型发现/连通性测试/多 profile 行为保真 | settingsProfileSwitch 仍绿；LlmConfigPane 逐字段对位搬迁 | ✅ |
| 缓存管理分区 | 否 | 统计条/类别表格/按代码/全清输入「清空」确认/探测缓存清除 | cachePane 10 用例（含错误态/重试/刷新保留旧数据） | ✅ |
| 会话管理分区 | 否 | 会话总数、清空全部二次确认、取消不删 | sessionsPane 4 用例；契约 `{sessions:[...]}` 已核 | ✅ |
| 运行信息分区 | 否 | 只读展示默认配置/健康/Langfuse/版本/commit；git_commit 可空兜底 | runInfoPane 5 用例（含 git_commit null 兜底） | ✅ |
| 数据监控分区 | 否 | 命中/未命中/失败计数卡 + 新鲜度列表（已过期标记） | dataMonitorPane 5 用例 | ✅ |
| 战绩展示偏好 | 否 | 四项偏好存 `fa_track_prefs`；时间跨度前端裁剪曲线；回撤阈值/基准/净值形态消费 | trackPrefsPane 7 + trackRecordPage 24 用例 | ✅ |
| LLM 下拉「LLM 配置…」分隔项 | 否 | 分隔线 + 项、点击跳设置页、不切 profile | dropdownOutsideClick 14 用例（含反向断言不调 onSwitchProfile） | ✅ |
| 全量回归 | 否 | 后端 + 前端全量绿 | 后端 `uv run pytest -m "not live"` → 2103 passed / 2 skipped / 12 deselected；前端 `npx vitest run` → 550/550；`npm run build` 成功；ruff 通过；mypy 本次引入 0 新错（session_store 1 处已修） | ✅ |

## 需人工确认的主观项（E2E/自动化覆盖不到）

1. **强制配置跳转丢失输入草稿**：无 profile 时用户输入查询被强制跳 `/settings`，返回后草稿丢失（计划导航式迁移的固有取舍）。需确认接受此语义，或后续任务用 App state/sessionStorage 保留草稿。
2. **战绩页默认行为变化**：默认基准由「总是显示沪深300线」改为 spec 默认「不对比基准」——需浏览器确认默认观感符合预期。
3. **基准对比仅沪深300**：zz500/zz1000 选项已存储并标注「（待接入）」，序列待后端补充。
4. **时间跨度覆盖范围**：对战绩曲线生效（前端裁剪）；观点日志列表不随 timeSpan（后端无区间参数，允许降级路径内）。
5. **校准页/详情页偏好适用面**：两页无净值/基准/回撤/跨度内容，未消费四项偏好（spec 解读裁切，archive 前记录）。

## 异常记录
无自动化失败项。`@live` 后端用例（12 条）需真实 LLM/Langfuse 密钥，CI 以 `-m "not live"` 排除，与本变更无关。

## 结论
[ ] 全部通过，可 archive（需人工确认上述 5 项主观项后签字）
[ ] 存在失败项，需修复后重新验证