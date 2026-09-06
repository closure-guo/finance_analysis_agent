# 人工验证报告: add-track-record（阶段 A 核心骨架）

**日期**: 2026-09-03
**验证人**: [agent 自动验证 + 待人工抽查]
**关联 delta**: openspec/changes/add-track-record/
**E2E 门禁**: tests/e2e/playwright/playwright-report/（decisions.spec.ts 3 例全绿：侧边栏入口→/track-record、直达+样本积累中+返回、/decisions 重定向）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 侧边栏「决策战绩」→ /track-record 渲染 + 风险提示 | 是（decisions.spec.ts #1） | 折叠态图标点击后渲染战绩页，风险提示常驻 | E2E 实测通过 | ✅ |
| 直达 /track-record 样本积累中 + 返回 | 是（decisions.spec.ts #2） | 空库显示「样本积累中（已判定 0 条）」，返回聊天回首页 | E2E 实测通过 | ✅ |
| 旧 /decisions 重定向 | 是（decisions.spec.ts #3） | /decisions 仍渲染战绩页 | E2E 实测通过 | ✅ |
| 判定引擎口径（设计档案 §7） | 否（单测覆盖） | 4win/4loss/2neutral→0.5、中性带 +1.5%→neutral、short 对称 | 单测 test_track_record_judgment.py 7 例全绿 | ✅ |
| superseded 提前结算 | 否（单测覆盖） | 同标的方向相反/目标价不同 → 旧观点按现价结算 | 单测 test_superseded + job 测试 test_superseded_resolves_old | ✅ |
| 冻结不可改 / 记录不可删 | 否（单测覆盖） | 改 direction/entry_price/快照抛 FrozenFieldError | 单测 test_frozen_field_update_raises | ✅ |
| 全量记录（reject/hold/watch 也落库） | 否（单测覆盖） | reject+hold → neutral 记录；缺价格 → unresolvable 存档 | 单测 test_reject_also_records / test_no_price_archives_unresolvable | ✅ |
| 显著性门槛 | 否（单测覆盖） | settled<10 胜率 null + insufficient_sample；≥10 返回胜率 | 单测 test_overview_* 3 例 | ✅ |
| 回测/实盘分离 | 否（单测覆盖） | source 过滤不混合 | 单测 test_overview_source_filter | ✅ |
| 观点日志默认含 loss | 否（单测覆盖） | 列表默认返回全部状态 | 单测 test_predictions_list_default_all_statuses | ✅ |
| 决策迁移 decision_log → predictions | 否（单测覆盖） | 方向映射 + 幂等 | 单测 test_migrate_decision_log | ✅ |

## 待人工抽查项（E2E 覆盖不到的主观体验）

- [ ] 有真实观点数据（非空库）时表格密度、状态分色（命中绿/未中红/进行中蓝/不可判定灰）的观感
- [ ] 深色模式下总览卡、风险提示（浅黄底）的观感
- [ ] 完成一次真实深度分析（approve 或 reject）后，观点出现在战绩页；reject 也出现（全量记录）

## 异常记录

1. **全量 E2E 门禁最终结论（2026-09-03 深夜补跑）：通过**。在双端口空闲（docker compose 栈停）+ 机器负载回落（90 条消融已收尾）的干净窗口下，全量套件 **26 过 / 7 挂 / 1 跳过（2.1 分钟）**。7 个失败全部为既有已知问题：6 例 @live（search-banner/thinking-banner，需真实 LLM，CI nightly 才跑）+ 1 例 downloads.spec 引用已删除的 testid（stale spec）。**零新增失败**——本 delta 的 decisions.spec 3 例全绿；此前多轮运行中的额外失败（smoke/streaming/agui/interaction/debug-* 等）经三层证据定性为环境因素（docker 前端容器占 5173 且 `reuseExistingServer: true` 导致 Playwright 复用残缺栈，nginx /api 代理指向已停后端全 500；消融实验压 CPU），与代码无关。
2. **历史过程记录**：曾出现 17~23 例失败的两次全量运行，根因即上述环境叠加；期间用「手动 TESTING 后端直连端点全 200」「decisions.spec 隔离跑全绿」排除了代码回归。
3. **旧 expose-decision-outcomes 的 DecisionCenter 不再接入 App**（被 TrackRecordPage 取代，/decisions 重定向）；组件级测试保留，App 级集成用例已移除——「取代/演进」决策的预期后果，sync 时需确认 expose-decision-outcomes 的 archive 处理（建议：决策查询 API Requirement 保留共存，决策战绩页面 Requirement 由本 delta 补 REMOVED）。

## 结论

- [x] 阶段 A 功能实现 + 自动化验证通过（判定/统计/冻结/迁移/API 单测全绿、前端 456 全过、E2E 3 例全绿、ruff/tsc 干净）
- [ ] 待人工抽查项完成后 + sync 顺序确认（decision-outcome-tracking 先归档）后方可 archive
