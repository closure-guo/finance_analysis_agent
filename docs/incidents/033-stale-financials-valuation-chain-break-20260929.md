# Incident 033: 财报论据结构性过时 + 估值信号链路断裂 — 拓荆科技报告外部批评核实

**日期**: 2026-09-29
**状态**: 已修复——三个 delta（update-financial-freshness-and-valuation / clear-valuation-chain-debts / update-decision-integrity-gates）已实施、终审通过并 sync+archive 于 `openspec/changes/archive/`（2026-09-29/30），全量 2631 passed
**触发**: 外部对 2026-09-29 拓荆科技(688072)报告的批评，经逐条核实基本属实

## 现象

报告（reports/拓荆科技_688072_20260929_134934_report.md）同时出现三类问题：

1. **论据自相矛盾且过时**：一边引用 2026 中报净利 +1324.1%，一边用止于 FY2025 的年报序列断言「毛利率连续下滑（47.11%→34.95%）」「资产负债率 64.11% 偏高」。实际 2026 中报毛利率 ≈41.0%（同比 +9.0pct）、负债率已降至 47.85%（中报归母权益近乎翻倍）。报告自设的再评估触发条件「季报毛利率止跌回升」在中报披露（2026-08-21，早于报告 38 天）后已被满足，系统不知情。
2. **全文无估值分析**：市值 1910 亿、TTM PE ≈88 倍，报告对「当前价格是否透支业绩」零讨论，仅有一句「GARP 估值未通过（负债率≥60%，PE 不低于行业平均）」。
3. **行业模式误判**：存货周转率 0.56/速动比率 0.74 被通用制造业阈值判红灯，健康度 40 分；半导体设备「验收确认收入+合同负债预收」的商业模式在阈值表中无覆盖。

## 根因（三层，均有实证）

1. **数据层报告期策略**：`akshare_client.py` 三大报表与指标接口 `_filter_annual` 只保留年报（1231 报告日）；唯一季度接口 `fetch_quarterly_income` 只提取 `PARENT_NETPROFIT`。系统在结构上不可能知道中报毛利率回升与负债率下降——不是分析师幻觉（报告数字全部可溯源到输入，citation 纪律有效），是**数据管道失明**。Langfuse trace `a4f3459d…`：基本面分析师输入中毛利率序列最新为 2025 年；输入里的券商研报标题「公司毛利率呈逐步改善趋势」敌不过预计算年报序列。
2. **估值链路断裂 + 伪文案**：backend 日志 13:46「东财行情不可用」→ 百度回退只补市值/PB（设计如此），compute 只读 `quote.PE` 从不推导 → GARP 输入 `PE=null` 却渲染「PE >= 行业平均」（garp.py 缺数兜底分支把数据缺失伪装成比较失败）→ relative_valuation 整段跳过 → market_cap 只进图表 KPI，从未进入任何 LLM 上下文。data-source-resilience 规范曾写「PE 推导留给下游 compute」，实现从未兑现——规范开了空头支票。
3. **阈值表行业盲区**：traffic_light.py 通用阈值（存货周转绿≥5/黄≥2）+ 仅白酒行业覆盖，半导体设备必然满屏红灯，健康度 40 分是其直接产物。

## 反模式教训

- **兜底文案谎报**：「PE >= 行业平均」是评估 SOP 第 4 条点名的「兜底文案谎称数据缺失」在估值维度的实例。缺数据必须显式说缺数据。
- **数据切片未对齐即入上下文**：年报序列与季度净利并存但从未交叉校验趋势，LLM 忠实引用了两个过期/片面的事实并推出过期结论。新鲜度是数据装配的契约，不能指望 LLM 自行发现输入的时间结构。
- **规范承诺无实现兜底**：「留给下游处理」型条款若下游无对应实现与测试，等于规范层面掩盖缺口。

## 修复

openspec/changes/update-financial-freshness-and-valuation/（四个 capability：analyst-data-sources 最新报告期快照+季度字段扩展、data-source-resilience PE 推导责任、valuation-signal-integrity 新能力、industry-threshold-coverage 新能力含 5 家同业校准）。健康度口径变更需同步 docs/evals/metrics.md §1。

**实施收口（2026-09-30）**：主 delta 连同两个伴随 delta 一并落地——`clear-valuation-chain-debts`（诚实分桶全输入化、同业抓取 fetch_peer_data、季度出口 NaN 归一、披露节编号体系、图通道门禁扩展）、`update-decision-integrity-gates`（决策文本价位交叉校验 anomaly、非法仓位档位渲染归一、buy/sell 终稿 reeval_triggers 必填化打回、FM 审批可见性与置信度漂移标注）。三个 change 均已 sync+archive，人工验证报告见 `tests/validation/`（688072 四轮实跑 5/5 通过）。

## 关联

- 外部批评原文中的两处小误：解禁日期实为 2027-01-04（非 2026-01-04）；负债率在报告中被列为「偏高」（黄灯口径）而非红灯。不影响主论点。
- 数据取证：Langfuse trace `a4f3459d6c43a28f9490823ef5430531`（基本面 generation 输入 69954 字符）；backend 日志 2026-09-29 13:46 行情回退记录；新浪报表/东财业绩接口直连复核（H1 毛利率 41.0%、存货 88.33 亿、合同负债 51.31 亿、市值 1910.23 亿）。
