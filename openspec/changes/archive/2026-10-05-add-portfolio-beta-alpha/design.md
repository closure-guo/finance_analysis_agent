# Design: add-portfolio-beta-alpha

## Context

`metrics.py` 的 `compute_metrics_from_marks` 已由 daily_marks 产出双净值序列(agent 与 benchmark 同日期、首日归一 1.0),并计算年化收益/波动/夏普/回撤,经 `persist_metrics_snapshot` 写 `agent_metrics_daily`(列固定,旧库靠 PRAGMA 探测的幂等 ALTER 迁移加列,见 `_migrate_stage_c_columns` 先例)。战绩页总览的 portfolio 指标块逐格渲染快照字段,null 显示 "—"。当前净值 17 个交易日、每日双收益序列已在库。

## Goals / Non-Goals

**Goals:**
- 组合 β 与年化 Jensen α 进指标引擎、快照、overview API、战绩页指标区
- 样本不足时字段为 null,不给出噪声读数

**Non-Goals:**
- 不做滚动 β 曲线/时间序列,只做全窗口单值
- 不做按观点分桶的 α(那是 T+20 判定链的 excess_return 口径,已存在,11 月初首批结算后自然出数)
- 不改夏普/回撤等既有指标口径;不动 equity_curve 与判定链

## Decisions

1. **β 用 OLS 斜率,输入为同日期日收益对**:由相邻 agent_nav 推导组合日收益、相邻 benchmark_nav 推导基准日收益,取两序列均非空的日期对;β = Σ((rb−μb)(ra−μa)) / Σ((rb−μb)²)。**首日不计**(首日收益是"相对入场日"的口径混合点,且基准首日收益恒 0)。
2. **α 用日频 CAPM 残差年化**:α_daily = μa − rf/252 − β×(μb − rf/252),年化 × 252;rf 沿用 `RISK_FREE_RATE`(env `TRACK_RISK_FREE_RATE`,默认 0.02),与夏普同源,不另设配置。
3. **样本门槛 20 个重叠日收益对**(< 20 → 两字段 null):与 T+20 判定窗口同数量级;门槛内也明确这是描述性读数,不做显著性声明(样本数小,β 噪声大,页面不渲染置信区间——YAGNI)。
4. **迁移沿 `_migrate_stage_c_columns` 模式**:`agent_metrics_daily` 加 `beta REAL`、`jensen_alpha REAL`,`INSERT OR REPLACE` 快照写入两列;`get_latest_metrics` 原样带出;overview portfolio 块加 `beta`/`jensen_alpha` 键。历史快照可通过既有手动重算(metrics_snapshot job)补齐。
5. **前端两格**:β 格显示两位小数(如 0.85,无百分号);α 格沿 `Delta` 组件(带符号百分比)。标题用用户语言:「β 市场敞口」「α 年化超额」,配一句副标题解释口径(敞口=1 满仓跟随大盘;α=剔除大盘后的独立判断收益),回应"跌市跑赢≠选股能力"的解读需求。
6. **E2E 归属**:交互类变更(前端 UI)→ 复用 PR #203 建立的 track-record 专属 E2E 套件(独立测试库),新增 spec 断言 seed 造数后两格渲染数值;不新增 config。

## Risks / Trade-offs

- **17 个样本当前读数为 null**:上线初期两格显示 "—",待净值积累过 20 个重叠日(约一周后)亮起——符合"不给噪声读数"的立场,但要有预期管理。
- **基准日收益序列来自 daily_marks.benchmark_price 传导**:若盯市基准拉取失败日增多,重叠对减少,可能长期 < 20 → 保持 null(正确行为)。
- **与 PR #203 的文件接触面**:双方都改 `TrackRecordPage.tsx` 与 `api.py`,但 hunk 不重叠(指标区 vs 卡片挂载/overview vs index-compare 端点);后合并方可能小冲突,手工可解。
- **β 为负(净空结构)属预期**:当前系统高回避+空头记分,β 可能显著为负——这正是该指标的教育意义,副标题文案需容納负 β 的展示。
