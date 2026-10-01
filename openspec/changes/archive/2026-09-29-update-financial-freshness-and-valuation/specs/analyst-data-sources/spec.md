# Delta for analyst-data-sources

## ADDED Requirements

### Requirement: 最新报告期快照获取

系统 SHALL 在深度分析数据准备阶段获取「最新报告期快照」（latest_period_snapshot）：从三大报表数据源取最新已披露报告期（不限于年报，含中报/季报/三季报）的关键科目，写入 state 键 `latest_period_snapshot`。快照 SHALL 至少包含：报告日、营业总收入（累计）、归母净利润（累计）、毛利率、资产负债率、存货、合同负债，以及营收/归母净利相对上年同期的同比变化率（同期数据可得时）。快照各科目口径为该报告期累计值，SHALL 标注「累计口径」。快照抓取或字段缺失 SHALL 降级为携带缺失标注的部分快照且不阻断管线。

#### Scenario: 年报之后已有中报时快照取中报

- GIVEN 拓荆科技最新年报为 2025-12-31、最新中报为 2026-06-30（后者披露更晚）
- WHEN 深度分析数据准备阶段执行快照获取
- THEN `latest_period_snapshot.报告日` SHALL 为 2026-06-30
- AND 毛利率 SHALL 按中报累计口径计算（营业总收入 29.13 亿、营业成本 17.18 亿 → 约 41.0%）
- AND 资产负债率 SHALL 为中报期末值（约 47.9%，而非年报的 64.11%）
- AND 存货/合同负债 SHALL 为中报期末值

#### Scenario: 同期数据缺失时同比留空

- GIVEN 最新报告期为上市后首份报告，无上年同期数据
- WHEN 快照获取执行
- THEN 营收/归母净利同比 SHALL 为 None 并标注缺失
- AND 其余科目 SHALL 照常装配，管线不中断

#### Scenario: 快照数据源失败降级

- GIVEN 快照依赖的报表接口调用失败
- WHEN 数据准备阶段完成
- THEN `latest_period_snapshot` SHALL 为空 dict 并留 ERROR 日志
- AND 管线 SHALL 继续执行（与公告/研报降级同语义）

### Requirement: 季度利润表字段扩展

季度利润表获取（`fetch_quarterly_income`）SHALL 在现有单季归母净利润之外同时提取单季营业收入与单季营业成本；`quarterly_trend` SHALL 增加单季营收序列（含同比，去年同期可得时）与单季毛利率序列（(营收−营业成本)/营收）。字段缺失的季度 SHALL 置 None 且不产出伪值。

#### Scenario: 季度趋势含毛利率序列

- GIVEN 2026Q2 单季营收、营业成本与归母净利润均可得
- WHEN compute 节点装配 `quarterly_trend`
- THEN 该季度 SHALL 携带单季营收、单季毛利率与单季归母净利润
- AND 单季毛利率 SHALL 由 (营收−营业成本)/营收 直接运算得出

#### Scenario: 某季度成本缺失不产出伪毛利率

- GIVEN 2025Q3 单季营业成本缺失
- WHEN `quarterly_trend` 装配
- THEN 2025Q3 毛利率 SHALL 为 None
- AND MUST NOT 以 0 或邻期值填充

### Requirement: 分析师消费最新报告期快照

基本面分析师的上下文 SHALL 包含最新报告期快照数据段（state 键 `latest_period_snapshot`），段内 SHALL 标注报告日与「最新报告期」身份；prompt SHALL 指示：涉及盈利能力、负债水平、存货等存量/趋势论断时，最新报告期数据与年报序列趋势 SHALL 同时呈现，论断 SHALL 以最新报告期数据为准校验年报趋势是否已被打破，二者冲突时 MUST 显式说明（如年报序列下滑但最新中报回升）。

#### Scenario: 中报回升与年报下滑并陈

- GIVEN 年报毛利率序列 2023–2025 连续下滑（47.11%→34.95%）而快照显示 2026 中报毛利率约 41.0%（同比 +9pct）
- WHEN 基本面分析师构建上下文并生成报告
- THEN 上下文 SHALL 同时含年报序列与快照段
- AND 报告的盈利质量论断 SHALL 反映中报回升事实，MUST NOT 仅凭年报序列断言「毛利率连续下滑」

#### Scenario: 快照空缺时报告披露数据边界

- GIVEN `latest_period_snapshot` 为空 dict（数据源失败降级）
- WHEN 基本面分析师生成报告
- THEN 论断 SHALL 基于年报序列并显式标注「最新报告期快照缺失」
- AND MUST NOT 假设年报趋势仍然成立而不加限定
