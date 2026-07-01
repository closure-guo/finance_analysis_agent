# Finance Analysis Agent — 面试项目总结

## 一、项目概述

一个面向 A 股上市公司的多 Agent 交易决策分析系统。基于 TradingAgents 5 层架构，输入股票代码，系统自动完成宏观/基本面/技术面/舆情 4 维度并行分析，经 Bull/Bear 辩论和 Risk Management 压力测试后，输出含交易建议的综合分析报告。

**核心价值**：将专业分析师数小时的工作压缩到 3-5 分钟，5 层架构: 4 分析师并行 → Bull/Bear 辩论 → Trader 决策 → Risk Management 压力测试 → Fund Manager 批准。

**在线演示**：[Hugging Face Spaces](https://closure-guo-finance-analysis-agent.hf.space)

---

## 二、技术栈

| 层级 | 技术 | 职责 |
|------|------|------|
| 前端 | Gradio 5.x | 表单输入、报告展示、文件下载 |
| 编排 | LangGraph | 5 层多 Agent 架构 + Send 并行派发 + 辩论循环 |
| 数据 | pandas + SQLite | AKShare 数据拉取、20 指标计算、缓存持久化 |
| LLM | DeepSeek-V4-Pro（LiteLLM 路由） | 分析推理、报告撰写 |
| 导出 | python-docx / python-pptx | Word / PPT 报告生成 |
| 测试 | pytest + Playwright | 单元测试 + E2E 端到端验证 |
| 工程化 | uv + ruff + mypy + pre-commit | 包管理、lint、类型检查、Git hooks |

---

## 三、系统架构

### 3.1 分层架构

```
┌─────────────────────────────────────────────┐
│  L1 前端 — Gradio Blocks                     │  表单输入 + 报告展示 + 文件下载
├─────────────────────────────────────────────┤
│  L2 Agent — LangGraph                        │  5 层架构: 4 分析师并行 + Bull/Bear
│                                              │  2 轮辩论 + Trader + Risk Management
│                                              │  3 方 2 轮辩论 + Fund Manager
├─────────────────────────────────────────────┤
│  L3 数据 — pandas + SQLite                   │  AKShare 拉取 + 指标计算 + 缓存
├─────────────────────────────────────────────┤
│  L4 LLM — DeepSeek via LiteLLM               │  分析推理 + 报告文本生成
└─────────────────────────────────────────────┘
```

**分层原则**：Agent 节点是**纯 LLM 消费者**——只读 State + 调用 LLM，不拉数据、不做计算、不写文件。PREP 子图一次性注入全部数据，数据层全权负责所有 I/O 和计算。

### 3.2 LangGraph 图拓扑

```
START → check_cache → [fetch_data →] validate_financials → [FAIL: 终止] → compute_metrics
  │  (PREP: 一次性拉取三大报表 + K 线 + 宏观 + 新闻，计算 20+ 指标 + 技术指标 + 风控指标)
  │
  ├─ Layer I  → Send([macro, fundamental, technical, sentiment])   # 4 分析师并行
  ├─ Layer II → Send([bull_r1, bear_r1]) → Send([bull_r2, bear_r2]) → research_manager  # Bull/Bear 2 轮辩论
  ├─ Layer III → trader                                              # 交易决策
  ├─ Layer IV → Send([aggressive_r1, conservative_r1, neutral_r1])
  │            → Send([aggressive_r2, conservative_r2, neutral_r2]) → risk_judge  # 3 方 2 轮辩论
  └─ Layer V  → fund_manager ──→ [Approve] ──→ generate_report → END
                              ├──→ [Reject]  ──→ generate_report（标注未通过）→ END
                              └──→ [Return]  ──→ trader（最多 1 次）→ ... → fund_manager
```

**关键设计点**：

- **缓存旁路**：缓存命中直接跳过 `fetch_data`，节省网络请求
- **硬性校验门**：勾稽校验失败（资产 ≠ 负债 + 权益）直接终止管线，不生成错误报告
- **4 分析师 Send 并行**：Layer I 宏观/基本面/技术面/舆情 4 个分析师通过 `Send` API 并行执行，LLM 调用延迟从串行 4 次降到等价 1 次
- **Bull/Bear 2 轮辩论**：Layer II 多空双方各立论 + 反驳，每轮 `Send` 并行，Research Manager 综合结论
- **Risk Management 3 方压力测试**：Layer IV 激进/保守/中性 3 方 2 轮辩论 + Risk Judge 裁决，对 Trader 计划做风险压力测试
- **Fund Manager 退回机制（限 1 次）**：Layer V 可 Approve / Reject / Return to Trader，退回最多 1 次防死循环
- **隐式屏障同步**：LangGraph 自动等待所有并行节点完成后才进入下一层

### 3.3 State 设计

使用 `TypedDict(total=False)` —— 所有字段可选，节点逐步填充。混合模式：PREP 字段保持扁平（兼容现有代码），Agent 输出采用嵌套结构。

| 层 | 内容 | 示例字段 |
|----|------|----------|
| Input | 用户输入 | stock_code, analysis_type |
| PREP 原始数据（扁平） | 三大报表 + K 线 + 宏观 + 新闻 | balance_sheet, income_statement, cash_flow, kline, macro_indicators, news_list |
| PREP 计算指标（扁平） | 衍生计算指标 | solvency_metrics, dupont_tree, traffic_lights, health_score, technical_indicators, risk_metrics |
| Agent 输出（嵌套） | 4 分析师结构化报告 | `analyst_reports: dict[str, AnalystReport]` |
| Agent 输出（嵌套） | Bull/Bear + Risk 辩论记录 | `debate_history: list[DebateMessage]` |
| Agent 输出（嵌套） | 交易决策 | `trade_decision: TradeDecision` |

---

## 四、核心模块详解

### 4.1 数据层 — AKShare + 缓存

**`akshare_client.py`**：封装 AKShare 第三方 API，核心挑战是数据质量。

- 新浪 API 不稳定，实现了 3 次重试 + 5 秒间隔的容错机制
- AKShare 中文列名存在编码不一致问题（"归属母公司所有者净利润"在不同环境可能不同），通过位置索引硬编码解决
- 股票名称/行业信息有主备双源（东方财富主 → 巨潮资讯备）

**`cache.py`**：SQLite 单表双序列化（JSON for dict / Parquet for DataFrame）。

- WAL 模式支持并发读写
- TTL 惰性过期——读时检查删除，不启动清理线程
- 分层缓存策略：三大报表持久化、行情按交易日缓存、衍生指标不缓存（毫秒级重算）

### 4.2 勾稽校验 — 数据质量门

在指标计算前插入 4 条会计等式校验：

| 规则 | 等式 | 级别 |
|------|------|------|
| 试算平衡 | 资产 = 负债 + 权益 | 硬（失败终止） |
| 利润表内部 | 净利润 ≈ 利润总额 - 所得税 | 软（警告继续） |
| 现金流内部 | 经营 + 投资 + 筹资 = 净变动 | 软（警告继续） |
| 留存收益 | 期末 = 期初 + 净利润 - 分红 | 软（警告继续） |

**设计考量**：AKShare 数据可能存在列错位、字段缺失、合并/母公司报表混淆。错误数据会静默污染所有下游指标和 LLM 分析——"看起来合理的错误报告比明确的报错更危险"。

### 4.3 指标计算 — 纯函数层

20 个核心指标分 4 个维度 + 杜邦分解，全部是**纯函数**（DataFrame/dict 输入 → dict 输出，无 I/O）。

**偿债能力**（5 指标）：资产负债率、流动比率、速动比率、利息覆盖倍数、净债务/EBITDA

**盈利能力**（5 指标）：毛利率、净利率、ROE、ROA、ROIC
- ROE 优先使用 AKShare 预计算的加权平均 ROE（证监会标准），回退到自算的平均权益法
- 统一使用归母净利润/归母权益口径

**杜邦分析**（3 层递归）：
- L1：ROE = 净利率 × 资产周转率 × 权益乘数
- L2：净利率分解为毛利率 - 费用率；周转率分解为资产构成
- L3：费用率分解为销售/管理/研发/财务费用率

### 4.4 红黄绿灯评分

**双阈值模型**（ADR-0003）：

1. **绝对值水平**：每个指标有独立阈值（优良/关注/警告）
2. **同比变化率**：<20% 稳定 / 20-50% 波动 / >50% 异动
3. **最终灯色 = max(绝对值灯, 变化率灯)**

**安全下限**：当绝对值超过绿色阈值的 10 倍时，变化率灯强制为绿——防止优秀指标的微小波动触发假警报。

**行业覆写**：`INDUSTRY_OVERRIDES` 字典支持行业定制阈值（如白酒存货周转率天然低，不能套用通用阈值）。

**健康度评分**：4 维度 × 25 分 = 100 分。绿灯满分、黄灯半分、红灯零分。85+ 健康、60-84 关注、<60 警告。

### 4.5 事件管线 — 三级降级

```
L2 Web 搜索 (DuckDuckGo) → L1 预设事件库 → L3 兜底占位符
```

- L2 使用 LLM 从搜索结果中提取结构化事件（JSON schema），区分战略级（L1）和运营级（L2）事件
- 域名白名单过滤低质量来源
- **永远不会返回空**——L3 兜底保证系统健壮性
- 作为舆情分析师（ADR-0011 Layer I）的输入之一

### 4.6 Agent 节点 — 5 层多 Agent 架构

各层 Agent 共享相同的设计哲学：**PREP 注入 + 单轮 LLM + 结构化输出**，无 tool calling。

| 层 | Agent | 输入 | 输出 |
|----|-------|------|------|
| Layer I | 4 分析师（宏观/基本面/技术面/舆情） | PREP 一次性注入全量数据 | 各自 Pydantic schema 结构化报告 |
| Layer II | Bull / Bear | 4 份分析师报告 | 2 轮辩论论点（Round 1 立论 → Round 2 反驳） |
| Layer III | Trader | Research Manager 综合结论 | 交易计划（买卖方向 + 逻辑） |
| Layer IV | 激进/保守/中性 3 方 | Trader 计划 + PREP 风控指标 | 2 轮辩论 + Risk Judge 裁决 |
| Layer V | Fund Manager | `final_trade_decision` | Approve / Reject / Return to Trader |

**关键约束**：Prompt 中明确禁止 LLM 编造数据、自行计算未提供的指标——缺失数据必须标注"数据不可用"。

### 4.7 报告生成 — 10 章拼接

10 章报告由 `generate_report` 节点拼接：4 分析师章节 + 辩论摘要 + 交易建议 + 风险提示 + 执行摘要。

1. **执行摘要**（第 2 章）：Fund Manager 最终决策 + 关键理由
2. **分析师章节**（第 3-6 章）：宏观 / 基本面 / 技术面 / 舆情 4 份分析师输出
3. **辩论摘要**（第 7 章）：Bull/Bear 辩论核心论点 + Research Manager 结论
4. **交易建议**（第 8 章）：Trader 计划 + Risk Management 评估 + Fund Manager 批准
5. **风险提示**（第 9 章）：Risk Management 辩论中的风险点 + PREP 风控指标

### 4.8 LLM 调用封装

`llm.py` 是一个极简的同步封装（~60 行），设计哲学是"让异常冒泡"——不做重试、缓存、流式。

- 通过 LiteLLM 实现模型无关（DeepSeek/OpenAI/其他一键切换）
- `drop_params = True` 静默丢弃不支持的参数，保证跨模型兼容
- Thinking 模式与 Temperature 互斥——思考模式开启时不传 temperature

---

## 五、关键技术决策（ADR）

| ADR | 决策 | 状态 | 核心权衡 |
|-----|------|------|----------|
| 0001 | 数据准备子图 | Amended by 0011 | 集中数据拉取逻辑，PREP 子图扩展为全量数据注入 |
| 0002 | 纯 LLM 消费者 | Superseded by 0011 | FA/IA 双 Agent 废弃，职责并入 4 个并行分析师 |
| 0003 | 双阈值红黄绿灯 | Accepted | 硬编码阈值保证确定性和可重复性，但需要行业适配 |
| 0004 | 分层持久化 | Accepted | 原始数据缓存 + 衍生指标不缓存（毫秒重算），避免过期计算 bug |
| 0005 | 勾稽校验 | Amended by 0011 | 硬规则失败终止管线，校验范围扩展至 PREP 新增数据 |
| 0006 | Send API 并行 | Superseded by 0011 | 并行从 FA/IA 两 Agent 扩展到 4 分析师 + 辩论多轮 |
| 0007 | 综合报告结构 | Superseded by 0011 | 三层 merge 结构废弃，改为 10 章分析师主导拼接 |
| 0008 | MCP Server | Superseded by 0011 | 本项目撤销 MCP，内部 Agent 直接调 Python 函数 |
| 0009 | 延后辩论 | Reversed by 0011 | 辩论不再延后，作为核心组件立即采纳 |
| 0010 | 工具使用重构 | Partially Superseded by 0011 | Step 1（tool calling）撤销，Step 2/3（reflection + Claim 校验）保留 |
| 0011 | 5 层架构 | Accepted | TradingAgents 5 层架构：4 分析师 → 辩论 → 决策 → 风控 → 批准 |

---

## 六、踩过的坑与经验教训

### 6.1 LLM 幻觉事件

**现象**：输入数据完全正确，但 LLM 编造了负债率（~40% vs 实际 19%）、OCF/净利润比率（1.4 vs 实际 1.035）、行业 PE（~30x 无数据来源）。

**根因**：Prompt 约束不足，LLM 用"常识"填补缺失数据。

**修复**：添加明确禁止编造数据的 Prompt 条款；缺失数据标注"不可用"；实现 `fetch_industry_pe()` 补全数据源；为 PE 指标标注定义口径。

**教训**：LLM 会编造金融数字，null 远优于编造值。

### 6.2 报告准确性 — 行业适配

**现象**：茅台（2000 亿现金）被评"现金流弱、效率低"，健康度仅 60.8 分。

**根因**：通用指标体系不适用于白酒行业——白酒存货是升值资产而非拖累；现金流下降是非核心子公司存款导致，非盈利质量恶化。

**修复**：添加绝对值安全下限、行业定制阈值、行业分析指南。

**教训**：准确的数字是必要条件而非充分条件，没有行业上下文的正确数据也会得出错误结论。

### 6.3 年份错位 Bug

**现象**：300308 分析报告中 6 项数据与同花顺 iFinD 不一致。

**根因**：`efficiency.py` 使用行号索引匹配指标（`iloc[i]`），但 indicators 按日期升序排列而报表降序排列——2025 年的数据匹配上了 2020 年的指标。**影响所有股票，非个例。**

**调查过程**：根因修订了两次——先从"LLM 幻觉"到"数据源差异"，再到"代码 Bug（年份错位）"。验证发现 AKShare 数据与 iFinD 完全一致，Bug 纯在代码。

**修复**：实现日期匹配函数 `_find_indicator(indicators, year)` 替代行号索引。

**教训**：数据对齐必须用日期匹配，绝不能用行号。不同 DataFrame 可能有不同排序和行数。

### 6.4 Python NaN 陷阱

**现象**：净债务/EBITDA 对净现金公司（零借款）显示 NaN，`val or 0` 回退模式失效。

**根因**：Python 中 `bool(float('nan'))` 是 `True`，所以 `NaN or 0` 返回 `NaN` 而非 0。

**修复**：实现 `_safe_num()` 和 `_is_valid()` 辅助函数，使用 `pd.isna()` 检测。

### 6.5 格式化 Bug — 小数点 vs 百分号

**现象**：净利润增长率显示为 `-0.05%` 而非 `-4.53%`。

**根因**：`formatters.py` 对比率值使用 `:.2f` 而非 `:.2%`，导致 100 倍偏差。

**教训**：金融比率的格式字符串至关重要，`.2f` vs `.2%` 产生 100 倍差异。

---

## 七、工程实践

### 7.1 测试策略

- **纯函数指标层**：每个指标模块有独立测试，使用 fixture DataFrame 模拟 AKShare 数据
- **TDD 修复 Bug**：年份错位 Bug 使用 RED-GREEN-REFACTOR 循环修复，tracer-bullet 测试用升序 indicators + 降序 balance_sheet 的生产场景
- **E2E 验证**：Playwright 自动化端到端测试，验证 Gradio UI 完整流程
- **测试隔离**：测试输出通过 `REPORTS_DIR` 环境变量重定向，不污染生产 `reports/` 目录

### 7.2 代码质量

- **Ruff**：集成 pycodestyle、Pyflakes、isort、pep8-naming、pyupgrade、bugbear、bandit 等 lint 规则
- **MyPy**：strict 模式类型检查（`warn_return_any`、`check_untyped_defs`）
- **pre-commit**：Git hooks 保证提交质量
- **ADR 文档**：每个重要架构决策有编号记录，包含背景、方案对比、权衡分析

### 7.3 事件管理

系统性问题记录在 `docs/incidents/`，每个事件有编号、根因分析、修复方案和经验教训。目前已记录 5 个事件，覆盖 LLM 幻觉、行业适配、数据 Bug、格式化错误等典型场景。

---

## 八、项目亮点（面试讲述要点）

1. **5 层多 Agent 架构**：4 分析师并行（Send API）→ Bull/Bear 辩论 → Trader 决策 → Risk Management 压力测试 → Fund Manager 批准，展示角色专业化与协作
2. **Bull/Bear 辩论减少确证偏误**：多空双方 2 轮辩论（立论 + 反驳），Research Manager 综合结论，对抗单一视角偏见
3. **Risk Management 3 方压力测试**：激进/保守/中性 3 方 2 轮辩论 + Risk Judge 裁决，对交易计划做风险压力测试
4. **结构化输出 + Claim 校验**：agent 间通信从自由 Markdown 改为 Pydantic 结构化对象，FinGround 论文落地的 6 类 Claim 分类法 + 公式重算验证
5. **PREP 一次性数据注入 + 4 个新 metrics 模块**：无 tool calling，确定性数据需求由 PREP 全量注入；新增 macro/technical/risk/sentiment 4 个指标模块
6. **数据质量门控**：勾稽校验作为硬性门控，防止错误数据污染 LLM 分析
7. **纯函数指标层**：20+ 核心指标 + 技术指标（MACD/RSI/布林带/KDJ）+ 风控指标（回撤/波动率/Beta/VaR），全部无副作用、可独立测试
8. **双阈值评分模型**：绝对值 + 变化率双维度评估，安全下限防误报，行业定制阈值
9. **三级事件降级管线**：Web 搜索 → 预设库 → 兜底，保证永不返回空
10. **从踩坑中沉淀**：NaN 陷阱、年份错位、格式字符串 100 倍偏差——每个 Bug 都转化为 ADR 或事件文档

---

## 九、后续规划（v2.0）

- 快速模式（tool calling + 交互式问答）：PREP 全量注入适合"深度报告"，快速模式按需拉取数据、支持用户追问
- 蒸馏模型降低 Claim 校验成本：Claim 公式重算依赖 LLM 调用，蒸馏小模型可降低单次校验开销
- DCF 绝对估值定量计算（WACC ±1%、g ±0.5% 敏感性分析）
- Tavily 行业搜索，补全行业上下文
- Chroma 研报 RAG，引入券商研报作为分析参考
- 图表渲染（雷达图、趋势图）
- 行业自适应指标体系
