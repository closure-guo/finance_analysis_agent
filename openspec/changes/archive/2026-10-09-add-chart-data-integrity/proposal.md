# Proposal: add-chart-data-integrity

## Why

光大银行(601818)分析报告（2026-10-05）暴露图表与派生指标层系统性缺陷：银行模板下归母口径列按列位硬编码解析到错误列（ROE 画出 28.0%、归母权益画成未分配利润）、缺数据被填 0 渲染（热力图四行全 0、柱图缺序列静默画一半）、金额图轴标「亿元」实为原始元、营业成本缺失被虚构成 100% 毛利率。图表是报告的「第一眼证据」，这些伪值会经多空辩论被共识化加固，必须先于行业包等大改修掉。

## What Changes

- 报表归母口径列（归母净利润/归母所有者权益）解析改为**列名候选归一化匹配优先、既有列位映射降级为回退**——银行模板（列位 44/141）与制造业模板（列位 50/137）都解析到真实列
- 派生比率缺失输入不产出伪值：营业成本缺失/非正时毛利率为 None（MUST NOT 出现 100% 伪值），ROE 回退链输入缺失时为 None
- 年度维度图表横轴按时间**升序**呈现（数据层「index 0 = 最新」降序契约不变，仅呈现层反转）
- 图表缺数据禁止填 0：热力图单元格缺失渲染为缺失标注；柱图缺失值断开；整序列缺失时呈现占位说明或跳过（对齐既有 contract_liab/debt_ratio 语义）
- 图表金额单位统一：轴标「亿元」的序列实际数值同步 /1e8，数据标签同步

## Capabilities

### New Capabilities
- `chart-data-integrity`: 报告图表及其上游派生链的数据完整性契约——归母口径列解析、缺失语义（禁伪值/禁填 0）、时间轴方向、单位一致性

### Modified Capabilities
- （无——PE/GARP/健康度对解析结果的消费行为由既有 valuation-signal-integrity、industry-threshold-coverage 契约约束，本变更只修复其输入的正确性，不改变这些 requirement）

## Impact

- `src/finance_agent/data/akshare_client.py`（`_rename_parent_cols`）
- `src/finance_agent/metrics/profitability.py`（毛利率/ROE 缺失语义）
- `src/finance_agent/charts.py`（全部年度图表函数）
- `tests/fixtures/`（新增真实银行/制造业新浪报表固定装置）
- 下游连带（预期内、非破坏）：银行股 ROE/毛利率/归母权益/PE_ttm 数值修复后重算；健康度评分因毛利率维度转为「不计分」而变化；图表 PNG 视觉重排
