# Design: update-financial-freshness-and-valuation

## Approach

四个工作流，共享一个原则：**不动现有年报口径的指标计算**（ROE/杜邦/增长率/健康度全部基于年报序列，爆炸半径大），新鲜度以「增量数据段」方式注入。

### 1. 最新报告期快照（latest_period_snapshot）

- 数据源复用 `_sina_report` 原始 DataFrame（`_filter_annual` 之前的数据）：全报告期里取 `报告日` 最新的一行；年报序列逻辑不变。
- 快照字段：报告日、营业总收入（累计）、归母净利润（累计）、毛利率（(收入−营业成本)/收入）、资产负债率（负债合计/资产总计）、存货、合同负债、营收/归母净利同比（同期行存在于原始 df 时计算，否则 None）。
- 利润表科目为**累计口径**（中报=半年累计），段头标注「累计口径」；资产负债表科目为期末时点值。
- 抓取失败/字段缺失：部分快照 + 缺失标注；全失败 → 空 dict + ERROR 日志，管线继续（与公告/研报降级同语义）。
- 注入 `analysts.py` 基本面 context，作为独立数据段（固定单期尺寸，不违反 analyst-context-budget 的裁剪精神）。

### 2. 季度利润表字段扩展

- `fetch_quarterly_income` 在 `PARENT_NETPROFIT` 之外提取单季营收与单季营业成本列（东财 `stock_profit_sheet_by_quarterly_em` 提供对应列；列缺失或值为 NaN 时该季字段置 None）。
- `_calc_quarterly_trend` 增加：`revenue`（单季）、`revenue_yoy`（去年同期可得时）、`gross_margin`（(营收−成本)/营收）。沿用现有「最新在前 + 序列语义头」契约。

### 3. 估值链路完整性

- **PE_ttm 推导**（compute，纯规则）：`quote.PE` 缺失且 `market_cap` 可得时推导
  `TTM 归母净利 = 最新年报归母净利 − 该年内与最新累计报告期同期的归母净利 + 最新累计报告期归母净利`（最新报告期即年报时直取年报值）
  `PE_ttm = market_cap / TTM 归母净利`
  输入缺失或 TTM ≤ 0 → None + 原因（TTM 为负时注明「PE 无意义」）；不产出 0/无穷/NaN；口径标注 `derived_ttm`，与主源静态 PE 并存不覆盖。
- **GARP 诚实文案**：`calc_garp` 的 PE 分支拆为三桶——有值且比较失败（「PE >= 行业平均」）/ 有值且通过 / **缺失（「PE 数据缺失（未参与比较）」+ details 标注 missing）**。负债率等其他维度同理推广。
- **上下文注入**：基本面 context 新增估值段：PE（口径标注）、PE_ttm、PB、market_cap、相对估值结论；`relative_valuation` 在 PE 缺失但 PE_ttm 可用时用 PE_ttm 计算；估值维度整体缺失时输出「估值数据缺失」显式声明段。
- 拓荆算例（验收基准）：market_cap 1910.23 亿，TTM = 9.27 − 0.94 + 13.43 = 21.76 亿 → PE_ttm ≈ 87.8。

### 4. 半导体设备行业阈值覆盖

校准集（FY2025 年报口径，akshare `stock_financial_analysis_indicator` + 新浪报表复算，5 家代表公司）：

| 指标 | 样本分布 | 中位数 | 通用阈值 | 覆盖阈值 (green, yellow) |
|---|---|---|---|---|
| 存货周转率(次) | 0.56–1.06 | 0.75 | (5, 2) | **(1.2, 0.5)** |
| 速动比率 | 0.74–1.90 | 1.17 | (1.5, 0.8) | **(1.5, 0.6)** |
| 应付账款周转率(次) | 2.08–4.26 | 2.48 | (6, 3) | **(4.5, 1.5)** |

取值逻辑：green ≈ 样本最优水平（跑赢全部代表公司才算绿）、yellow 下限容忍验收周期/预收款模式的结构性偏慢、red 留给显著脱离行业分布的异常。拓荆 0.56/0.74/2.45 在覆盖口径下全部从红灯降为黄灯（存货周转按新浪复算 0.56，与指标接口 0.5638 一致）。

- `INDUSTRY_OVERRIDES` 增加键 `半导体设备`（行业名称子串匹配，cninfo/东财行业名均含该串）。
- 红黄绿灯与健康度输出增加 `industry_override` 标注（行业名 + 命中指标清单），报告健康度章节渲染该口径。

## Alternatives Considered

- **三大报表全报告期替换年报序列**：直接让毛利率/负债率序列含中报/季报点。否决——现有增长率/杜邦/红黄绿灯/健康度全部假设年报等间隔序列，改动会波及全部指标与既有评估基线（metrics.md 口径全部失锚）；快照增量方案零破坏。
- **百度回退源直接补抓「市盈率(TTM)」指标**：`stock_zh_valuation_baidu` 支持 PE-TTM，能覆盖本次故障模式且代码更少。作为 compute 推导的补充可选，但推导方案不依赖单一行情源（东财 PE 字段缺失、百度单指标失败等场景均覆盖），且口径自控（归母/TTM 明确），故本变更以推导为权威路径；补抓列为后续可选优化，不在本变更内（避免一次动两个变量）。
- **仅修 GARP 文案不推导 PE**：最小改动，但「估值分析缺席」的根因（LLM 看不到任何估值数字）仍在，报告依旧无法讨论贵贱。否决。

## Risks

- **快照与年报序列口径混用引发 LLM 误引**：中报累计 vs 年报全年数值直接对比会得出错误结论。对策：快照段头强制「累计口径」标注 + prompt 明确「论断以最新报告期校验趋势，同比只对同期」；citation 校验器对新键（`latest_period_snapshot.*`、`quarterly_trend.gross_margin`）的 claim 解析需抽验，必要时补 assertion-golden-set 样例。
- **阈值覆盖改变健康度评分，影响评估基线可比性**：按 metrics.md 纪律，口径变更先在 §1 登记再动代码；健康度时序对比需在报告中标注口径切换点（industry_override 披露即为此设计）。
- **PE_ttm 推导的归母口径混用**：业绩快报/利润表存在「净利润」与「归母净利润」两列，推导 MUST 统一归母列（与 GARP/相对估值的 growth 口径对齐），单测覆盖混列样本。
- **prompt 变更走 deploy_prompts 门禁**：改 `fundamental_analyst.md` 后必须执行 `uv run python scripts/deploy_prompts.py`，否则 eval 门禁拒绝运行（prompt-deploy-consistency）。
