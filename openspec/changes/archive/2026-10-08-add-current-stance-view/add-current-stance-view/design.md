# Design: add-current-stance-view

## Context

战绩页当前只有台账单视图：`GET /api/v1/track-record/predictions` 平铺全部行，同股跨日多条 open 并存（2026-10-07 实测 58 条 open / 13 只股票）。日主机制（add-prediction-pool-integrity）保证同股同日至多一条 open，但跨日不收敛。用户问题：「多个观点并存我不知道哪个算数」——立场语义（每股最新一条）在页面上不可见。

## Goals / Non-Goals

**Goals:**

- 新增立场视图：每股最新一条 open 观点，服务端收敛（单一真相，前端不做客户端去重）
- 纯展示分层：统计口径零改动（胜率/样本量/NAV/IC 分母不变）、台账零改动
- 行点击复用既有详情页，信息架构「总览 → 当前观点 → 台账」三层递进

**Non-Goals:**

- 不改 superseded 触发时机（「立即 vs 日批」是另一条 A 类候选，见审计报告）
- 不做同股 upsert / 活跃观点唯一化（会破坏 append-only 与样本量）
- 不做版本分段（agents 表当前为空，version 过滤随既有端点约定留待后续）
- 不修观点日志副标题「仍在 20 日判定窗口内」对 252 行不准确的问题（另行小改动处理）

## Decisions

**D1 独立端点而非列表参数。** `GET /api/v1/track-record/current` 作为独立资源，而不是给 `/predictions` 加 `latest_per_symbol=true`：语义不同（立场视图 vs 台账），列表端点参数面已经很大；独立端点可直接单测 SQL 语义。响应结构 `{current: PredictionRecord[], total, as_of, disclaimer}`，行结构复用 `list_predictions` 的行映射方式（同为 `SELECT *` → `dict(row)`，与台账行同构）。

**D2 「最新一条 open」的定义。** 立场 = 该标的 `status='open'` 中 `created_at` 最大者。不用「最新非 dup 行」：若最新行是 dup（日批关闭）或 superseded（被更新观点结算），它已不代表当前立场；`status='open'` 是唯一可靠的「仍在窗口内的活跃主张」判据。SQL 用 join 子查询（`GROUP BY symbol` 取 `MAX(created_at)`），`prediction_id` 作同秒并列的确定性 tiebreak。日主机制保证同股同日至多一条 open，跨日多条由 MAX 自然收敛。

**D3 252 旧口径行不特判。** 若某标的最新 open 是 252 行（当前数据不存在：7 条 legacy open 全部老于其 T+20 行），区块如实展示其自带窗口（T+252），不做口径过滤——台账全量语义一致，避免第二套隐藏规则。

**D4 回测/实盘分离的合规方式。** 沿用 `/predictions` 同款约定：行内携带 `source_type`，可选 `source` 查询参数过滤；缺省不合并展示无法区分的行（行级字段可区分，满足 track-record「回测实盘分离」Scenario）。

**D5 前端独立区块、独立加载。** `TrackRecordPage` 的 `load()` 在主 Promise.all 之外单独 fetch（不与总览/切片绑死成败）；区块自带 testid（`current-stance` / `current-stance-row-{id}` / `current-stance-empty`）；加载失败显示显式失败文案「当前观点加载失败」（IndexCompareCard 同款边界策略），SHALL NOT 静默降级为空态冒充「无观点」。列集：标的（名称+代码）/方向/建立日期/入场价/判定窗口/状态——不含结算价与收益列（open 行恒为空，展示「—」是噪声）。

## Risks / Trade-offs

- **同股同日两条 open 的过渡态**（新观点落库后、16:00 日批关闭 dup 前）：立场区显示最新一条，另一条要等日批关闭。可接受——立场=最新一条的语义本就如此；日主批是既有机制。
- **与「当前持有」tab 的口径差**：tab 是全部 open 平铺（65 条），立场区是每股一条（13 行）。区块副标题明示差异，避免「数字对不上」的二次困惑。
- **接口面扩大**：多一个只读端点的维护成本，换取语义清晰与可测试性。
