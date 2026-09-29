# Proposal: update-financial-freshness-and-valuation

## Why

2026-09-29 拓荆科技(688072)报告的外部批评核实属实：报告一边引用 2026 中报净利 +1324.1%，一边用止于 2025 年报的毛利率/负债率序列下「连续下滑/偏高」结论，其自设的再评估触发条件（毛利率止跌回升）在中报披露 38 天后已被满足而系统不知情；同时全文无估值分析——本次运行东财行情被封锁走百度回退（无 PE），compute 不从市值推导 PE，GARP 把 `PE=null` 渲染成「PE >= 行业平均」的伪比较结论，市值只进图表 KPI 从未进入任何 LLM 上下文（Langfuse trace `a4f3459d…` 与 backend 日志 13:46 实锤）。根因是三处结构性缺陷，非分析师幻觉（报告数字全部可溯源到输入）。系统性问题记录见 docs/incidents/（编号 033）。

## What Changes

- 三大报表/指标抓取在年报序列之外**新增「最新报告期快照」**（latest_period_snapshot）：取最新已披露中报/季报的关键科目（毛利率、资产负债率、存货、合同负债、营收/归母净利及同比），注入基本面分析师上下文，不改现有年报口径指标计算
- 季度利润表接口从只提取 `PARENT_NETPROFIT` 扩展为同时提取单季营收与营业成本，`quarterly_trend` 增加季度毛利率序列
- 估值链路修复：quote.PE 缺失时由 compute 从 `market_cap` + TTM 归母净利推导 `PE_ttm`；GARP/估值组件缺数据时如实输出「数据缺失」而非伪比较失败文案；PE/PB/市值注入基本面分析师上下文
- 红黄绿灯阈值表新增半导体设备行业覆盖（存货周转率/速动比率/应付账款周转率），健康度评分附行业口径披露

## Capabilities

### New Capabilities

- `valuation-signal-integrity`: 估值信号的完整性——PE 缺失时的确定性推导规则、缺数据时的诚实文案契约、估值数据进入分析师上下文的装配要求
- `industry-threshold-coverage`: 红黄绿灯/健康度评分的行业阈值覆盖——按行业子串匹配的阈值覆盖机制及半导体设备行业首批覆盖

### Modified Capabilities

- `analyst-data-sources`: 新增最新报告期快照的获取与消费要求；季度利润表字段扩展要求（现有公告/研报/解禁/大宗条目不变）
- `data-source-resilience`: 「PE 缺失时下游 `or` 守卫照常跳过估值维度」改为「PE 缺失时由下游 compute 按 TTM 口径确定性推导」（quote 内不推导的原则不变）

## Impact

- `src/finance_agent/data/akshare_client.py`：`fetch_quarterly_income` 扩展字段、新增快照抓取函数
- `src/finance_agent/nodes/compute.py`：PE_ttm 推导、快照/估值 state 键装配
- `src/finance_agent/metrics/garp.py`：缺数文案分桶
- `src/finance_agent/metrics/traffic_light.py`：INDUSTRY_OVERRIDES 增半导体设备
- `src/finance_agent/nodes/analysts.py`：基本面 context 新增快照/估值数据段
- `src/finance_agent/prompts/fundamental_analyst.md`：输入清单与估值分析要点更新（改后须跑 `scripts/deploy_prompts.py`，见 prompt-deploy-consistency）
- 非交互类变更（纯后端数据管道），不触发 E2E 门禁；citation-verification 的 claim 回声匹配需覆盖新数据段键名
