# GUI 端到端验证报告: add-agent-settings-center（浏览器自动化）

**日期**: 2026-09-09
**验证方式**: 浏览器自动化黑盒 GUI 测试（IAB 后端 + Playwright DOM 快照 + 截图）
**关联 delta**: openspec/changes/add-agent-settings-center/

## 环境准备（Phase Two，已与测试分离）

- 后端：`TESTING=1 SESSIONS_DB_PATH=tmp/guitest/sessions-guitest.db uvicorn :8000`（**会话库隔离**，避免「清空全部会话」触碰开发数据）；前端 `npm run dev :5173`。
- 测试数据：经 `/api/test/seed` 造 3 条会话（「GUI测试会话1-3」）用于会话总数/清空验证；随后新造 1 条「Header会话」用于 header 入口验证。
- `cache.db` 已备份（tmp/guitest/cache.db.bak），测试后恢复。
- 浏览器 profile 内 `fa_llm_profiles` 存有「我的配置」profile（继承自打开页面前端状态）。

## 测试结果

| # | 测试点 | 预期 | 结果 | DOM 证据 | 截图 |
|---|---|---|---|---|---|
| P0-1 | /settings 可达 + 左导航六分区 + 默认 LLM 配置分区 | 六模块齐全、LLM 配置字段渲染 | ✅ | 六导航按钮 + Provider 预设/API 形式/API Key/模型/刷新/测试连接/能力矩阵/配置管理全呈现 | ![t1](file:///D:/WorkSpace/finance_analysis_agent/gui-test-screenshots/t1_settings_default.png) |
| P0-2 | 设置入口迁移（弹窗→页面） | header 设置按钮、侧栏 gear 均跳转 `/settings`，无弹窗 | ✅ | 会话视图 header「设置」点击→URL `/settings`；收起态 gear 图标栏「设置」点击→URL `/settings` 且 [active] | —（DOM 证据充分） |
| P0-3 | LLM 下拉「LLM 配置…」分隔项 | 分隔线+项；点击跳 `/settings` 且不切 profile | ✅ | EmptyState 下拉显示 profile「✓ 我的配置」+ 其下「LLM 配置…」；点击后 URL `/settings`，LLM 配置分区 profile 仍「我的配置」 | — |
| P1-4 | 左导航分区切换 | 六分区内容切换、高亮同步 | ✅ | 逐个点击缓存/会话/运行/监控/战绩，右侧内容区正确切换，导航 [active] 同步 | ![t5](file:///D:/WorkSpace/finance_analysis_agent/gui-test-screenshots/t5_cache_pane.png) |
| P1-5 | 缓存管理分区 | 统计条+类别表；全清需输入「清空」确认；探测缓存清除 | ✅ | 汇总条（总条目/占用/待清/最近命中）；确认层初始「确认清空」disabled；输入「清空东」仍 disabled；输入「清空」→ enabled；确认后关闭并刷新；探测清除按钮执行 | ![t5](file:///D:/WorkSpace/finance_analysis_agent/gui-test-screenshots/t5_cache_pane.png) |
| P1-6 | 会话管理分区 + 清空全部（M1） | 会话总数=种子数；二次确认；清空后回空态首页无幽灵会话 | ✅ | 会话总数 3→二次确认「此操作不可恢复」→确认后 URL 回 `/`、侧栏「暂无历史会话」、首页空态（M1 修复生效）；后种子 1 条显示总数 1 | ![t6](file:///D:/WorkSpace/finance_analysis_agent/gui-test-screenshots/t6_sessions_pane.png) |
| P1-7 | 运行信息分区 | 只读展示后端默认配置/健康/Langfuse/版本/commit；无 apiKey | ✅ | 模型 openai/glm-5.3、API 地址 ark、健康「正常」、Langfuse 已启用、版本 0.1.0、Git Commit 67a74a27d58b（分支 HEAD）；无密钥字段 | — |
| P1-8 | 数据监控分区 | 命中/未命中/失败计数卡 + 新鲜度列表 | ✅ | 命中/未命中/失败 0/0/0；新鲜度表（类别/条目数/最早过期/状态，空态「暂无数据缓存条目」） | — |
| P1-9 | 战绩展示偏好分区 | 四项偏好；改动即时持久化 | ✅ | 默认时间跨度/对比基准/回撤阈值/净值形态四项渲染（中证500/1000 标「待接入」）；改阈值 10% 后 localStorage `fa_track_prefs={"timeSpan":"all","benchmark":"none","drawdownThreshold":0.1,"navChartForm":"cumulative"}` 即时写入 | — |
| P3 | 布局/渲染检查 | 无遮挡、错位、溢出 | ✅（DOM 几何） | 各分区元素可见且 topmost（elementFromPoint 校验）；未观察到遮挡/截断 | — |

## 失败与受限记录

1. **视觉核验受限**：当前会话模型不支持图像输入，截图无法由本模型直接视觉审阅——全部截图已保存至 `gui-test-screenshots/`（t1_settings_default.png / t5_cache_pane.png / t6_sessions_pane.png），**需人工看图复核**视觉质量维度（对齐/配色/间距）。DOM 几何与行为验证不受影响。
2. **Playwright 按钮 click 在 IAB 后端时序异常**：`getByRole/getByText(...).click()` 在已确认可见的元素上持续 3s 超时；采用 `tab.cua.click`（坐标路径，坐标来自同一会话内 `getBoundingClientRect` 实测 + `elementFromPoint` 确认 topmost）完成全部点击，属工具运行时兼容路径，非绕过校验。
3. **控制台日志无法收集**：IAB 后端不暴露 console 监听 API；测试全程未观察到可见错误表现（无错误 toast、无空白区域、无资源占位符破坏），如实记录。
4. 涉及真实数据删除的测试点（清空全部会话）仅在隔离测试库执行；`cache.db` 清空操作针对回归后可再生的缓存且已备份恢复。

## 结论

[ ] 全部测试点通过（DOM + 行为层面），截图证据待人工视觉复核后可归档
[ ] 存在失败项