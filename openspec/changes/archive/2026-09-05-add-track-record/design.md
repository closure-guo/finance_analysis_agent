# Design: add-track-record（阶段 A：核心骨架）

## Context

用户提供的《历史战绩体系设计文档 v1.0》定义了完整的可验证战绩系统（6 条不可妥协原则、predictions/daily_marks/equity_curve/agent_metrics_daily 四表、指标计算引擎、REST API、4 个前端页面、3 个后台任务）。本设计只做**阶段 A 核心骨架**：predictions 数据模型 + 全量记录 + 判定规则 + 基础统计 + 只读 API + 战绩页单页。

现有体系（decision-outcome-tracking + expose-decision-outcomes）是 v0 简化版：`decision_log` 只记 approve、止损/目标/超期结算、普通可改写表、无回测实盘区分、无风险提示。本提案按用户决策**取代/演进**它：decision-outcome 演进为 track-record 的写入侧，现有记录一次性迁移进 predictions。

## Goals / Non-Goals

**Goals（阶段 A）：**
- `predictions` 数据模型：append-only、快照冻结、`source_type` 分离、`direction`/`confidence` 字段
- 全量记录（reject/hold/watch/neutral 也落库）
- 判定规则：horizon（默认 252/上限 1 年）+ ±2% 中性带 + superseded + unresolvable
- 基础统计：胜率（含显著性门槛）+ 平均超额
- `/api/v1/track-record` 只读 API（总览 + 观点日志）
- 前端战绩页（总览 + 观点日志合并单页）+ 固定风险提示

**Non-Goals（后续增量 delta）：**
- daily_marks / equity_curve / agent_metrics_daily 三表与净值曲线
- 组合指标（回撤/波动率/夏普/风险分）
- 校准分桶与 Brier Score
- 分行业/市值/市场环境/持有期切片
- 观点详情页、校准页（设计档案页面三/四）
- 版本分段（agents 表 + version_seq）、审计日志
- 跟单/复制策略、多 Agent 排行榜、实时盘中盯市、回测引擎本身

## Decisions

**决策 1：predictions 取代 decision_log，一次性迁移。**
新表与现有 SQLite 同库（WAL 短连接）。写迁移脚本把 `decision_log` 记录映射进 `predictions`（status open/hit_stop/hit_target/expired → open/resolved_win/resolved_loss 等映射，action→direction，补 rationale_snapshot 为最小快照）；迁移后 `decision_log` 改只读不再写入。备选「并行新建」会产生两套战绩口径长期并存，对外展示易混——拒绝。

**决策 2：判定引擎独立于现有 settle.py，新增 `track_record/` 子模块。**
`src/finance_agent/outcome/track_record/` 下设 `model.py`（predictions DDL + append-only 守卫）、`judgment.py`（horizon/中性带/superseded/unresolvable 判定纯函数，合成 DataFrame 可测）、`stats.py`（胜率/超额/显著性门槛）。结算与判定语义不同（止损/目标 vs horizon+中性带），不复用 settle.py。备选「扩展 settle.py」会把两套语义缠在一起——拒绝。

**决策 3：方向映射 buy→long、sell→short、hold/watch→neutral。**
neutral/hold 默认不进胜率统计（仅进校准统计，可配置）。这与 settle.py 的符号化取负语义**冲突**——旧体系把 sell/hold/watch 当反向建议记战绩，新体系 neutral 默认不计入胜率。采用设计文档口径，旧迁移记录的 sell/hold/watch 按 neutral 处理。

**决策 4：显著性门槛只做展示层语义，不做评级。**
n<10 不展示胜率/评级、10–29 标注「样本较少」、≥30 完整展示；评级（0-5 星）留给阶段 B。stage A 的总览只返回 win_rate/avg_excess/sample_size + as_of + disclaimer，门槛语义体现在「n<10 时 win_rate 返回 null 且带 insufficient_sample 标注」。

**决策 5：冻结与 append-only 用应用层守卫 + 数据库约束双层。**
SQLite 无 RULE 机制，在 `model.py` 提供显式 update 守卫（冻结字段变更抛异常 + 记审计日志行），并加 DB 级 CHECK/触发器尽量兜底。审计日志（integrity-check 每日校验快照哈希）属阶段 A 之外，列为 Non-Goal 但模型预留 rationale_hash 字段。

**决策 6：战绩页复用现有页面模式，接 track-record API。**
沿用 DownloadCenter/DecisionCenter 的 pathname 路由 + 侧边栏入口模式；`/decisions` 页重定向到 track-record 视图（或替换）。风险提示 `DisclaimerFooter` 做成固定组件。观点日志卡片含迷你走势图（观点发出日竖线 + 实际走势），阶段 A 用 ECharts 简版。

## Risks / Trade-offs

- [与未归档的 decision-outcome-tracking/expose-decision-outcomes 冲突] → sync 顺序：decision-outcome-tracking 须先归档（主规范库先有 decision-outcome），本 delta 的 MODIFIED 再应用；expose-decision-outcomes 的战绩页将被本 delta 的 track-record 视图取代/重定向，需在 archive 前确认其页面不被重复暴露。
- [历史 decision_log 数据稀疏，迁移后样本量 < 10 门槛] → 这是预期行为（样本积累中），不是缺陷；评估体系需接受初期胜率不可见。
- [superseded 提前结算与现有决策流冲突] → 需明确「同一标的反向/改价新观点」的识别口径（按 ticker 匹配 + 方向相反），设计档案未定义细节，列为 Open Question。
- [全量记录会显著增加观点量] → reject/neutral 也落库，数据量较只记 approve 大增；判定任务按日批扫描 open，量可控。

## Migration Plan

1. 新增 `predictions` 表（幂等 DDL）+ `track_record/` 子模块
2. 写一次性迁移脚本：`decision_log` → `predictions`
3. `_persist_decision_log` 改为写 `predictions`（全量记录），decision_log 停写
4. 判定任务替换为 track-record 判定引擎
5. 新增 `/api/v1/track-record/*` 只读端点
6. 前端战绩页接 track-record API
7. 回滚：新表与旧表并存，回滚即停写新表、恢复旧表读取

## Open Questions

- superseded 的「同标的方向相反或目标价不同」识别口径：方向如何严格判定「相反」？目标价差多少算「不同」？（设计档案未定义，实现前需明确）
- confidence 的 Brier/校准在阶段 A 只存字段不计算（进阶段 B），迁移时旧记录的 confidence 是否回填？
- neutral/hold「仅进校准统计」在阶段 A 是否可见于总览的样本量？（设计档案说计入样本量，UI 单独标识）
