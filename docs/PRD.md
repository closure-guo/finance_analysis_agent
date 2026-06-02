# PRD: 金融AI分析报告系统 MVP

## Problem Statement

个人投资者在分析 A 股上市公司时，需要手动从多个数据源收集财务数据、计算指标、对比同业、撰写报告。这个过程耗时 3-5 小时，且容易因人为疏忽遗漏关键风险点。需要一个自动化系统，输入一个股票代码，在几分钟内生成结构化的专业级财务/投资分析报告。

## Solution

构建一个基于 LangGraph 的多 Agent 分析系统。用户通过 Gradio 表单输入股票代码和分析类型，系统自动完成数据拉取（AKShare）、指标计算（四维度 20 指标 + 杜邦 + 红黄绿灯 + 相对估值 + GARP）、LLM 分析解读、报告生成全流程，输出 Markdown 报告并可导出 Word/PPT。

## User Stories

### 输入与路由

1. 作为一个投资者，我能在搜索框输入股票名称或代码并从下拉列表选择目标股票，这样我不需要记住精确代码
2. 作为一个投资者，我能从下拉框选择分析类型（财务分析/投资分析/综合分析），这样系统能按需生成对应报告
3. 作为一个投资者，我能选择性地输入对标股票代码（如 `000858,000568`），这样报告中的同业对比使用我指定的公司而非自动选取
4. 作为一个投资者，如果我没有输入对标股票，系统能自动选取同行业市值 Top 5 的公司作为对比对象
5. 作为一个投资者，如果我输入的股票代码不存在，系统能给出明确的错误提示

### 数据准备

6. 作为一个投资者，我希望系统自动拉取目标公司最近 5 年（不足 5 年有多少用多少，最少 2 年）的三大财务报表
7. 作为一个投资者，我希望系统自动拉取目标公司的行情数据和行业归属信息
8. 作为一个投资者，我希望系统自动拉取同业公司的财务数据用于对比
9. 作为一个投资者，如果我已经分析过同一只股票且数据未过期，系统能跳过数据拉取直接使用缓存，在 1 秒内返回结果
10. 作为一个投资者，如果部分非必需数据（同业、搜索）拉取失败，系统能继续分析并在报告中标注数据缺失
11. 作为一个投资者，如果三大报表等必需数据拉取失败，系统能给出明确错误提示而非生成一份错误报告

### 数据校验

12. 作为一个投资者，系统在计算指标之前能自动校验三张报表的勾稽关系，而非直接基于可能不一致的数据生成报告
13. 作为一个投资者，如果资产负债表试算不平衡（资产 ≠ 负债 + 权益），系统能明确告知数据有问题并拒绝生成报告
14. 作为一个投资者，如果利润表/现金流表/留存收益勾稽存在偏差，系统在报告中标注数据偏差提示，而非静默忽略
15. 作为一个投资者，校验告警信息（如"利润表存在较大营业外收支"）能在 LLM 分析中被引用，帮助理解数据偏差的财务含义

### 财务分析

12. 作为一个投资者，我能在报告中看到偿债能力的 5 个指标（资产负债率、流动比率、速动比率、利息覆盖倍数、净债务/EBITDA）及其红黄绿灯评判
13. 作为一个投资者，我能在报告中看到盈利能力的 5 个指标（毛利率、净利率、ROE、ROA、ROIC）及其红黄绿灯评判
14. 作为一个投资者，我能在报告中看到运营效率的 4 个指标（存货周转率、应收账款周转率、总资产周转率、应付账款周转率）及其红黄绿灯评判
15. 作为一个投资者，我能在报告中看到现金流健康的 6 个指标（经营现金流/净利润、FCF、资本支出/折旧、现金流覆盖比率、FCF收益率、留存现金流比率）及其红黄绿灯评判
16. 作为一个投资者，我能在报告中看到每个指标的双重阈值评判结果：绝对值水平（优良/关注/警告）+ 同比变化率（稳定/<20%/波动/20-50%/异动/>50%）
17. 作为一个投资者，我能在报告中看到四维度健康度评分（各 25 分，总计 100 分）及整体评级（85-100 健康/60-84 关注/<60 警告）
18. 作为一个投资者，我能在报告中看到 3 层杜邦分解树，理解 ROE 变动的核心驱动因素
19. 作为一个投资者，我能在报告中看到与同业公司的四维度对比表，了解目标公司的相对位置
20. 作为一个投资者，我能在报告中看到所有红灯指标的汇总清单和 LLM 解读的风险提示

### 投资分析

21. 作为一个投资者，我能在报告中看到目标公司所属行业的基本概况和竞争格局（基于 LLM 知识）
22. 作为一个投资者，我能在报告中看到 PE/PB 同业对比表和相对估值结论（低估/合理/高估）
23. 作为一个投资者，我能在报告中看到 GARP 筛选结果（PE < 行业平均 ∧ 净利润增长率 > 15% ∧ ROE > 15% ∧ 负债率 < 60%）
24. 作为一个投资者，我能在报告中看到基于财务红灯指标的风险提示和 LLM 补充的风险分析
25. 作为一个投资者，我能在报告中看到明确的投资建议（积极/中性/谨慎）及核心逻辑

### 综合分析

26. 作为一个投资者，当选择综合分析时，我能同时获得财务分析报告和投资分析报告
27. 作为一个投资者，当选择综合分析时，报告开头有一段 300-500 字的综合摘要，提炼两份报告的关键发现

### 报告输出

28. 作为一个投资者，我能在报告中首先看到执行摘要（全文的 1 页总结），快速把握公司整体状况
29. 作为一个投资者，我能将分析报告导出为 Word 文档
30. 作为一个投资者，我能将分析报告导出为 PPT 演示文稿
31. 作为一个投资者，报告末尾有明确的免责声明（AI 生成、数据来源、不构成投资建议）
32. 作为一个投资者，报告中所有数据表格使用 Markdown 表格格式，在 Gradio 中可直接渲染

## Implementation Decisions

### Architecture: 4-Layer, 12 Nodes

系统采用 4 层架构，MVP 去掉 MCP 层：

- **L1 前端**：Gradio 5.x Blocks API，表单输入 + 报告展示 + 文件下载
- **L2 Agent**：LangGraph，12 个节点 + 2 个 Agent 子图 + 数据准备子图 + 条件路由
- **L3 数据**：pandas + SQLite，AKShare 数据拉取 + 全部计算 + 缓存
- **L4 LLM**：DeepSeek-V3.2（开发）/ GPT-4o（Demo），LiteLLM 路由

### Graph Topology

```
START(用户输入 stock_code + analysis_type)
  → check_cache
  → [HIT: validate_financials] / [MISS: fetch_data → validate_financials]
  → [PASS: compute_metrics] / [FAIL: END]
  → route(按 analysis_type)
  → financial: fa_analyze → fa_report
  → investment: ia_analyze → ia_report
  → comprehensive: (fa_analyze → fa_report) ∥ (ia_analyze → ia_report) → merge
  → generate_file(python-docx/pptx)
  → output(Gradio)
```

数据准备子图有三条路径：MISS（首次分析，拉取+持久化+校验+计算）、HIT（报表已有，校验+计算）和 FAIL（硬等式校验失败，终止）。PASS 路径都走 Route → Agent，因为分析报告不缓存，LLM 每次重新生成。

### State Definition (TypedDict)

LangGraph State 使用 TypedDict（非 Pydantic BaseModel），因为 LangGraph 原生支持 TypedDict、Reducer 注解零摩擦、Checkpoint 序列化无额外处理。

关键字段：

- 输入：stock_code, analysis_type, peer_codes（可选）
- Cache：cache_result（HIT | MISS）
- Layer 1 基础数据：三大报表（DataFrame）、行情、行业归属
- Layer 2 预计算指标：financial_indicators
- Validation：validation_result（PASS | FAIL）、validation_warnings（软规则告警）
- Layer 3 衍生计算：四维度 metrics dict、杜邦树、红黄绿灯、同业对比、相对估值、GARP 结果
- Agent 输出：financial_analysis, financial_report, investment_analysis, investment_report, final_report, file_path

### Agent Nodes Are Pure LLM Consumers

Agent 节点（fa_analyze, fa_report, ia_analyze, ia_report, merge）只读 State + 调 LLM，不拉数据、不做计算。所有数据拉取和计算集中在数据准备子图。

### Data Preparation: AKShare Only (MVP)

MVP 仅使用 AKShare 作为数据源，不接入 Tavily 搜索、巨潮 PDF 解析、Chroma RAG。

fetch_data 分两步：

- Step 1（并行）：三大报表 + 行情 + 行业归属 + 预计算指标（无依赖）
- Step 2（依赖 Step 1）：同业公司财务数据（需要行业归属结果）

数据降级策略：三大报表缺失 → 报错终止；同业/研报/搜索缺失 → 标记 N/A 继续。

### Metrics Computation: Pure pandas

compute_metrics 节点执行所有计算，纯 pandas 无 LLM：

- 四维度 20 指标（10 个 AKShare 预计算 + 11 个自算）
- 3 层杜邦分解
- 红黄绿灯矩阵（双重阈值：绝对值水平 + 同比变化率）
- 健康度评分（四维度各 25 分）
- 同业对比（市值 Top 5 或用户指定）
- 相对估值（PE/PB 同业对比）
- GARP 筛选

年份跨度：动态，尽量 5 年，最低 2 年，不足 2 年报错。

### Report Generation: Two-Pass

报告生成采用两步法解决"执行摘要需要总结全文"的问题：

1. 先生成正文章节（财务：3-7 章；投资：3-6 章）
2. 再将正文作为上下文，调用 LLM 生成执行摘要（第 2 章）
3. 最后拼接：封面 + 摘要 + 正文 + 免责声明

MVP 报告纯 Markdown + 表格，不引入图表库。

### Financial Report Structure (8 Chapters)

1. 封面（股票名称 + 代码 + 日期 + 数据范围）
2. 执行摘要（后生成）
3. 核心指标分析（四维度表格 + 红黄绿灯 + 评分 + LLM 解读）
4. 杜邦归因分析（3 层分解树 + ROE 变动归因 + LLM 解读）
5. 同业对比（Top 5 四维度对比表 + 排名 + LLM 解读，无数据则略）
6. 风险提示（红灯指标清单 + 异常值 + LLM 风险总结）
7. 结论与评级（健康度评分 + 核心指标摘要表 + 评级）
8. 免责声明

### Investment Report Structure (7 Chapters)

1. 封面
2. 执行摘要（后生成）
3. 行业概况（LLM 内部知识，非外部搜索）
4. 估值分析（PE/PB 同业对比表 + 相对估值结论 + GARP）
5. 风险提示（财务红灯指标继承 + LLM 补充）
6. 投资建议（综合评级 + 核心逻辑 + 关键假设）
7. 免责声明

### Scoring Model

每个指标通过双重阈值评判：

- 绝对值水平：优良/关注/警告（各指标阈值不同，运营效率用行业均值倍数）
- 同比变化率：<20% 稳定 / 20-50% 波动 / >50% 异动
- 最终灯色 = max(绝对值灯, 变化率灯)

四维度各 25 分 = 100 分。绿灯满分、黄灯半分、红灯零分。85-100 健康、60-84 关注、<60 警告。阈值硬编码在代码中。

### Persistence

- **LangGraph State**：内存，节点间数据传递
- **LangGraph Checkpoint**：SQLite（SqliteSaver），中断恢复
- **SQLite Cache**：跨会话数据复用，按 TTL 过期（三大报表到下个财报季，行情到当日收盘，行业归属 30 天）

### DCF Parameters (v2.0, Recorded for Future)

预测期 5 年，终端增长率 2%，市场风险溢价 7%（硬编码），无风险利率动态拉取（失败降级 1.8%），FCF 分阶段增长（前 3 年历史均值，后 2 年线性衰减至 g）。DCF 输出估值区间 + 敏感性分析。

### Module Structure

```
src/finance_agent/
├── graph.py              # 主图 + 条件路由
├── state.py              # AnalysisState TypedDict
├── nodes/
│   ├── cache.py          # check_cache 节点
│   ├── fetch.py          # fetch_data 节点（编排 AKShare 调用）
│   ├── validate.py       # validate_financials 节点（编排勾稽校验）
│   ├── compute.py        # compute_metrics 节点（编排 metrics/ 计算）
│   ├── fa.py             # FA 子图：fa_analyze + fa_report
│   ├── ia.py             # IA 子图：ia_analyze + ia_report
│   ├── merge.py          # merge 节点（拼接 + LLM 摘要）
│   └── output.py         # generate_file 节点（Word/PPT）
├── metrics/
│   ├── validate.py       # 勾稽校验 4 规则（纯函数）
│   ├── solvency.py       # 偿债 5 指标
│   ├── profitability.py  # 盈利 5 指标
│   ├── efficiency.py     # 运营 4 指标
│   ├── cashflow.py       # 现金流 6 指标
│   ├── dupont.py         # 杜邦 3 层分解
│   ├── traffic_light.py  # 红黄绿灯 + 评分
│   ├── relative.py       # 相对估值（PE/PB 同业对比）
│   └── garp.py           # GARP 筛选
├── data/
│   ├── akshare_client.py # AKShare API 封装
│   └── cache.py          # SQLite 缓存读写 + TTL
├── prompts/
│   ├── fa_analyze.md     # 财务分析 prompt（正文生成）
│   ├── fa_summary.md     # 财务执行摘要 prompt
│   ├── ia_analyze.md     # 投资分析 prompt（正文生成）
│   ├── ia_summary.md     # 投资执行摘要 prompt
│   └── synthesis.md      # 综合分析摘要 prompt
└── templates/
    ├── financial_report.md  # 财务报告 8 章模板
    └── investment_report.md # 投资报告 7 章模板
```

### Key Module Interfaces

- **metrics/validate.py**: 纯函数，`(df_balance, df_income, df_cashflow) → (result, warnings)`。4 条勾稽规则，硬等式失败返回 "FAIL"，软等式失败追加 warning。无 I/O、无 LLM。
- **metrics/\*.py**: 纯函数，`(df_balance, df_income, df_cashflow, ...) → dict`。无 I/O、无 LLM、无外部调用。
- **data/akshare_client.py**: `(stock_code, years) → dict of DataFrames`。封装所有 AKShare API 调用、重试、错误处理。
- **data/cache.py**: `get(key) → Optional[data]` + `set(key, data, ttl) → None`。封装 SQLite 读写和 TTL 过期。
- **nodes/fetch.py**: 读 cache + 调 akshare_client + 写 State。编排数据拉取的 Step 1 和 Step 2。
- **nodes/validate.py**: 读 State 原始报表 + 调 metrics/validate.py + 写 State（validation_result + warnings）。
- **nodes/compute.py**: 读 State 原始数据 + 调 metrics/ 所有函数 + 写 State。

## Testing Decisions

### What Makes a Good Test

- 只测试外部行为（给定输入，预期输出），不测试实现细节
- 财务计算的正确性通过硬编码的已知值验证（给定已知报表数据，验证计算结果）
- 使用真实数据结构（DataFrame），不用 mock 替换 pandas 操作

### Modules to Test

**metrics/ — 重点测试**（全部 9 个文件）：

每个指标计算函数用已知财报数据验证。原因：

- 纯函数、无 I/O、无 LLM — 天然可测，测试稳定不 flaky
- 财务计算正确性是系统地基，一个指标算错后面全错
- 阈值边界条件需要覆盖（红黄绿灯切换点）

测试覆盖范围：

- validate.py: 4 条勾稽规则 + 硬/软分级 + 阈值边界（试算平衡通过/失败、利润表勾稽偏差在阈值内/外）
- solvency.py: 5 个指标计算 + 阈值边界
- profitability.py: 5 个指标计算 + 阈值边界
- efficiency.py: 4 个指标计算 + 行业均值倍数阈值
- cashflow.py: 6 个指标计算 + FCF 正负值边界
- dupont.py: 3 层分解数值验证
- traffic_light.py: 双重阈值矩阵 + max 规则 + 评分计算
- relative.py: PE/PB 对比逻辑
- garp.py: 四条件筛选逻辑

### Modules NOT Tested (MVP)

- nodes/：依赖 State 和 LLM，用人工验证
- data/akshare_client.py：外部 API，用集成测试人工验证
- data/cache.py：薄封装层，逻辑简单

### No Prior Art

零代码项目，无已有测试先例。从零搭建测试框架。

## Out of Scope

以下功能明确不在 MVP 范围内，推迟到 v2.0：

- **DCF 定量计算**：WACC 估算、FCF 折现、估值区间、敏感性分析
- **Tavily 外部搜索**：行业新闻、政策趋势、实时信息
- **Chroma RAG**：研报 embedding、语义检索
- **巨潮资讯网 PDF 解析**：年报 MD&A、风险披露
- **图表渲染**：雷达图、趋势图、柱状图
- **港股/美股支持**：仅支持 A 股
- **MCP Server 封装**：MVP 直接用 Python 模块，后期可将整个 Agent 封装为 MCP Server
- **自由对话输入**：MVP 使用结构化表单，不支持自然语言输入
- **用户认证/多用户**：单用户本地使用

## Further Notes

### Implementation Phases

- **P0 骨架**：项目脚手架 + State 定义 + 空图 + 1 个端到端 happy path（stub 返回"你好"）+ Gradio 表单
- **P1 数据层**：AKShare 封装 + fetch_data + compute_metrics（全部 20 指标 + 杜邦 + 红黄绿灯 + 同业对比 + 相对估值 + GARP）+ SQLite 缓存 + metrics/ 单元测试
- **P2 分析层**：FA Agent + IA Agent + prompt 工程 + 报告模板 + 两步法执行摘要 + merge 节点
- **P3 输出层**：python-docx Word 生成 + python-pptx PPT 生成 + Gradio UI 打磨

每个阶段结束时跑通端到端验证。

### v2.0 Expansion Points

架构上预留以下扩展点：

- 数据层：DataFetcher 接口抽象，美股换 yfinance / Financial Modeling Prep
- 阈值：从硬编码抽到 `thresholds/{market}.yaml`
- MCP：整个 Agent 封装为 MCP Server
- 图表：引入 matplotlib/plotly，报告模板加入图表占位
- 市场：加 market 参数，适配港股/美股报表格式和阈值

### Existing ADRs

实现时遵循以下架构决策记录：

- ADR-0001: 数据准备子图（Strategy C，统一数据拉取）
- ADR-0002: Agent 节点纯 LLM 消费者
- ADR-0003: 双重阈值红黄绿灯评分模型
- ADR-0004: 四层持久化策略
- ADR-0005: 勾稽校验（compute 前置数据质量门卫）
