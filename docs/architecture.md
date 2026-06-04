# 金融AI分析报告系统 — 架构设计

> 基于架构设计文档讨论的最终确定方案。所有决策记录在 `docs/adr/` 中。

---

## 一、系统全景

### 1.1 四层架构

| 层级     | 选型                          | 职责                                                                |
| -------- | ----------------------------- | ------------------------------------------------------------------- |
| L1 前端  | Gradio 5.x Blocks API         | 表单输入（股票搜索+分析类型+对标股）+ 报告展示 + 文件下载           |
| L2 Agent | LangGraph                     | 12 节点 + 2 子图 + 数据准备子图 + 条件路由                          |
| L3 数据  | pandas + SQLite               | AKShare 数据拉取 + 全部计算 + SQLite 缓存（MVP 不含 Chroma/Tavily） |
| L4 LLM   | DeepSeek (deepseek-v4-pro) | LiteLLM 路由                                               |

### 1.2 核心原则

- **分层单向**：L3 管数据进出 → L2 管思考 → L1 管展示
- **Agent 纯 LLM**：Agent 只读 State + 调 LLM，不拉数据、不做计算
- **指标硬编码**：四维度 20 指标 + 阈值 + 杜邦 + 红黄绿灯，全部代码硬编码
- **MVP 无 MCP**：数据拉取和计算直接用 Python 模块，不包 MCP 层
- **MCP 扩展预留**：后期可将整个 Agent 封装为 MCP Server，对外暴露分析能力

---

## 二、图拓扑：8 节点

```mermaid
flowchart TB
    START([用户输入 stock_code + analysis_type]) --> PREP

    subgraph MAIN["主图"]
        direction TB

        subgraph PREP["数据准备子图 L3"]
            direction TB
            CC["① check_cache<br/>查持久化报表+缓存行情"]
            FP["② fetch_data<br/>Step1: AKShare并行拉取<br/>Step2: 同业数据(依赖行业归属)"]
            VF["③ validate_financials<br/>4条勾稽校验<br/>硬等式FAIL→终止 软等式→warning"]
            CM["④ compute_metrics<br/>20指标+杜邦+红黄绿灯<br/>+同业对比+相对估值+GARP<br/>纯pandas无LLM"]
            CC -->|"MISS 首次"| FP --> VF
            CC -->|"HIT 报表已有"| VF
            VF -->|"PASS"| CM
            VF -->|"FAIL 硬等式"| END_ERR(["终止: 数据校验失败"])
        end

        FA["⑤ fa_analyze<br/>读State全部分析数据<br/>LLM生成正文+摘要+组装8章报告"]

        IA["⑥ ia_analyze<br/>读State行业+估值+风险<br/>LLM生成正文+摘要+组装7章报告"]

        Merge["⑦ merge<br/>拼接FA+IA报告<br/>LLM写300-500字综合摘要(仅comprehensive)"]
        GenFile["⑧ generate_file<br/>python-docx/pptx生成Word/PPT"]
    end

    PREP --> Route

    Route -->|"financial"| FA
    Route -->|"investment"| IA
    Route -->|"comprehensive 并行"| FA
    Route -->|"comprehensive 并行"| IA

    FA -->|"comprehensive"| Merge
    IA -->|"comprehensive"| Merge
    FA -->|"单Agent"| GenFile
    IA -->|"单Agent"| GenFile
    Merge --> GenFile
    GenFile --> END([END])

    style PREP fill:#e8f5e9
    style CC fill:#81c784,color:#fff
    style FP fill:#81c784,color:#fff
    style VF fill:#ffcc80,color:#fff
    style CM fill:#81c784,color:#fff
    style END_ERR fill:#ef5350,color:#fff
    style Route fill:#ff9800,color:#fff
    style FA fill:#e3f2fd
    style IA fill:#f3e5f5
    style GenFile fill:#ef9a9a
    style Merge fill:#ab47bc,color:#fff
```

---

## 三、节点详细规格

| #   | 节点                | 读 State                             | 写 State                                 | LLM |
| --- | ------------------- | ------------------------------------ | ---------------------------------------- | --- |
| ①   | check_cache         | stock_code                           | 命中时填充 L1-L3 全部                    | 否  |
| ②   | fetch_data          | missing_items                        | L1+L2+L4 全部原始数据                    | 否  |
| ③   | validate_financials | L1 三大报表                          | validation_result + warnings             | 否  |
| ④   | compute_metrics     | L1-L4 原始数据                       | 四维度+杜邦+灯+同业+相对估值+GARP+健康度 | 否  |
| ⑤   | fa_analyze          | 四维度+灯+杜邦+同业+异常+warnings    | financial_analysis + financial_report    | 是  |
| ⑥   | ia_analyze          | 行业+估值+GARP+风险                  | investment_analysis + investment_report  | 是  |
| ⑦   | merge               | financial_report + investment_report | final_report                             | 是  |
| ⑧   | generate_file       | final_report                         | file_path + file_paths                   | 否  |

> 注：fa_analyze / ia_analyze 采用双阶段生成（Phase 1 正文 → Phase 2 摘要 → Phase 3 模板组装），原设计的独立 fa_report / ia_report 节点已合并，以简化图拓扑。路由通过 LangGraph `Send` API 实现并行派发，不是独立节点。

---

## 四、数据持久化与缓存

### 4.1 数据分层策略

| 策略       | 数据               | 存储方式                 | 原因                                     |
| ---------- | ------------------ | ------------------------ | ---------------------------------------- |
| **持久化** | 三大报表           | SQLite                   | 历史事实不可变，拉一次存下来，新季度追加 |
| **缓存**   | 行情数据           | SQLite（TTL 到当日收盘） | 每天变动                                 |
| **缓存**   | 行业归属           | SQLite（TTL 30 天）      | 极少变                                   |
| **缓存**   | AKShare 预计算指标 | SQLite（TTL 同报表）     | 跟随报表时效                             |
| **缓存**   | 行业 PE            | SQLite（TTL 1 天）       | 每天变动                                 |
| **不存储** | L3 衍生计算        | 每次重算                 | 纯 pandas，无 API，毫秒级                |

### 4.2 自动追踪（v2.0 计划）

| 用途                                         | 方式        | 备注                    |
| -------------------------------------------- | ----------- | ----------------------- |
| 断点恢复                                     | SqliteSaver | 本地，不跨会话（未接入）|
| 历史观测（每节点 I/O + 耗时 + token + 异常） | LangSmith   | 云端，30 天保留，零代码（未接入）|

### 4.3 缓存状态机

```mermaid
stateDiagram-v2
    [*] --> CHECK_CACHE: 输入(stock_code, analysis_type)

    CHECK_CACHE --> COMPUTE: HIT（报表持久化命中 + 行情未过期）
    CHECK_CACHE --> FETCH: MISS（首次分析）

    FETCH --> VALIDATE: 拉取成功
    FETCH --> VALIDATE: 部分失败(标记N/A)
    VALIDATE --> COMPUTE: PASS（硬等式通过）
    VALIDATE --> [*]: FAIL（硬等式失败,终止）
    COMPUTE --> READY: 计算完成
    READY --> [*]
```

两条执行路径：

| 路径 | 触发条件                    | 经过节点                                                 | API 调用         | 耗时 |
| ---- | --------------------------- | -------------------------------------------------------- | ---------------- | ---- |
| HIT  | 报表持久化命中 + 行情未过期 | check_cache → validate → compute → Route → Agent         | 0（数据）+ LLM   | ~2s  |
| MISS | 首次分析                    | check_cache → fetch → validate → compute → Route → Agent | 5-8（数据）+ LLM | ~8s  |
| FAIL | 硬等式校验失败              | check_cache → [fetch →] validate → END                   | 0-5（数据）      | ~1s  |

> 注：两条路径都走 Route → Agent，因为分析报告不缓存，LLM 每次重新生成。

### 4.4 fetch_data 内部分步（MVP）

- **Step 1 并行**：三大报表 + 行情 + 行业归属 + 预计算指标（AKShare，无依赖）
- **Step 2 依赖**：同业公司财务数据（需要 Step 1 的行业归属 + 同业列表）

> v2.0 增加：Tavily 搜索（依赖行业名称）、巨潮 PDF 解析、Chroma 研报 RAG

---

## 五、四维度 20 指标

### 5.1 指标清单与数据来源

| 维度      | 指标              | 来源   | 说明                                           |
| --------- | ----------------- | ------ | ---------------------------------------------- |
| 偿债(5)   | 资产负债率        | 自算   | 负债合计 / 资产总计                            |
|           | 流动比率          | 自算   | 流动资产 / 流动负债                            |
|           | 速动比率          | 自算   | (流动资产 - 存货) / 流动负债                   |
|           | 利息覆盖倍数      | 自算   | EBIT / 利息费用                                |
|           | 净债务/EBITDA     | 自算   | (有息负债 - 货币资金) / EBITDA                 |
| 盈利(5)   | 毛利率            | 自算   | (营业收入 - 营业成本) / 营业收入               |
|           | 净利率            | 自算   | 归母净利润 / 营业收入                          |
|           | ROE               | 混合   | 优先取 AKShare 加权 ROE；降级自算              |
|           | ROA               | 自算   | 净利润 / 资产总计                              |
|           | ROIC              | 自算   | NOPAT / 投入资本                               |
| 运营(4)   | 存货周转率        | 混合   | 优先取 AKShare 预计算；降级自算                |
|           | 应收账款周转率    | 自算   | 营业收入 / 应收账款平均余额                    |
|           | 总资产周转率      | 自算   | 营业收入 / 资产总计                            |
|           | 应付账款周转率    | 自算   | 营业成本 / 应付账款                            |
| 现金流(6) | 经营现金流/净利润 | 自算   | 经营现金流净额 / 净利润                        |
|           | FCF               | 自算   | 经营现金流净额 - 资本支出                      |
|           | 资本支出/折旧     | 自算   | 资本支出 / 折旧变动                            |
|           | 现金流覆盖比率    | 自算   | FCF / (资本支出 + 利息)                        |
|           | FCF 收益率        | 自算   | FCF / 营业收入 (MVP 简化版)                    |
|           | 留存现金流比率    | 自算   | (FCF - 分红) / FCF                             |

### 5.2 红黄绿灯阈值

**绝对值阈值（部分示例）**：

| 指标       | 🟢 优良  | 🟡 关注  | 🔴 警告 |
| ---------- | -------- | -------- | ------- |
| 资产负债率 | <40%     | 40-65%   | >65%    |
| 流动比率   | >2.0     | 1.0-2.0  | <1.0    |
| ROE        | >15%     | 8-15%    | <8%     |
| FCF        | 正且增长 | 正但下降 | 负值    |

运营效率维度使用固定阈值，白酒/酿酒行业通过 `INDUSTRY_OVERRIDES` 覆盖存货周转率阈值（因基酒需长期陈酿）。

**变化率阈值（统一）**：<20% 🟢 / 20-50% 🟡 / >50% 🔴

### 5.3 评分

四维度各 25 分。🟢=满分 🟡=半分 🔴=零分。
85-100=🟢健康 | 60-84=🟡关注 | <60=🔴警告

### 5.4 杜邦分解（3 层）

```
L1: ROE = 净利率 × 总资产周转率 × 权益乘数
L2: 净利率 → 毛利率 - 费用率
L3: 费用率 → 销售费用率 + 管理费用率 + 研发费用率 + 财务费用率
```

---

## 六、LangGraph State 结构

```python
from typing import TypedDict, Literal
import pandas as pd

class AnalysisState(TypedDict, total=False):
    # ── 输入 ──
    query: str
    stock_code: str
    analysis_type: Literal["financial", "investment", "comprehensive"]
    peer_codes: list[str] | None
    enable_web_search: bool  # Gradio 开关：是否启用实时事件搜索

    # ── Cache ──
    cache_result: str  # HIT | MISS

    # ── Validation ──
    validation_result: str  # PASS | FAIL
    validation_warnings: list[str]

    # ── Layer 1: 基础公共数据 ──
    balance_sheet: pd.DataFrame
    income_statement: pd.DataFrame
    cash_flow_statement: pd.DataFrame
    stock_quote: dict
    industry_info: dict

    # ── Layer 2: 分析导向 ──
    financial_indicators: pd.DataFrame | None
    industry_pe: dict | None

    # ── Layer 3: 衍生计算 ──
    solvency_metrics: dict
    profitability_metrics: dict
    efficiency_metrics: dict
    cashflow_metrics: dict
    dupont_tree: dict
    growth_rates: dict
    anomalies: list
    traffic_lights: dict
    health_score: dict | None

    # ── Layer 3 扩展: 同业+估值 ──
    peer_financials: pd.DataFrame | None
    peer_comparison: dict | None
    relative_valuation: dict | None
    garp_result: dict | None

    # ── Layer 3 扩展: 季度趋势 ──
    quarterly_income: pd.DataFrame | None
    quarterly_trend: dict | None

    # ── Layer 2.5: 关键非财务事件（仅 IA 使用）──
    key_events: list[dict] | None

    # ── Agent 输出 ──
    financial_analysis: str | None
    financial_report: str | None
    investment_analysis: str | None
    investment_report: str | None
    final_report: str | None
    file_path: str | None
    file_paths: dict | None
```

---

## 七、条件路由

```python
# 数据准备子图条件边
def after_check_cache(state):
    result = state["cache_result"]
    if result == "HIT":
        return "validate_financials"  # 报表已有，先校验再算
    return "fetch_data"

# 勾稽校验条件边
def after_validate(state):
    result = state["validation_result"]
    if result == "FAIL":
        return "__end__"  # 硬等式失败，短路终止
    return "compute_metrics"

# 主图路由
def route_to_agent(state):
    return state["analysis_type"]

# Agent完成后
def after_agent(state):
    if state["analysis_type"] == "comprehensive":
        return "merge"
    return "generate_file"
```

---

## 八、技术选型

| 层级      | 选型              | 备选            | 决策依据                        |
| --------- | ----------------- | --------------- | ------------------------------- |
| 前端      | Gradio 5.x Blocks | Streamlit       | 表单布局灵活 + share 链接       |
| Agent     | LangGraph         | CrewAI          | Supervisor + Sub-graph 原生支持 |
| LLM(开发) | DeepSeek-V4-Pro  | Qwen2.5         | 成本 4元/M tokens，中文财务更优 |
| LLM 路由  | LiteLLM           | 自定义          | 100+ 模型统一接口               |
| PDF       | pdfplumber        | Unstructured.io | 表格准确率 98.3%，速度快 6x     |
| 数据      | AKShare           | Tushare         | 免费无 API Key                  |
| 向量      | Chroma            | FAISS           | 本地零配置                      |
| 关系      | SQLite            | PostgreSQL      | 零配置单文件                    |
| 搜索      | Tavily            | Brave           | 为 LLM 优化                     |
| Word      | python-docx       | —               | 程序化生成                      |
| PPT       | python-pptx       | —               | 程序化生成                      |

---

## 九、未决定项

| 问题                     | 选项                                     | 影响                                                                               |
| ------------------------ | ---------------------------------------- | ---------------------------------------------------------------------------------- |
| ~~DCF 的 WACC 假设来源~~ | ~~公式估算 vs LLM 生成 vs 硬编码默认值~~ | ~~已决定：公式估算（CAPM + 利息费用/有息负债）~~                                   |
| ~~项目目录结构~~         | ~~见架构文档~~                           | ~~已决定：src/finance_agent/ 分 nodes/metrics/mcp_servers/data/prompts/templates~~ |
| ~~实施阶段划分~~         | ~~P0骨架→P1数据层→P2分析层→P3输出层~~    | ~~已决定：4阶段渐进~~                                                              |

### 补充决定

- **State 使用 TypedDict**：LangGraph 原生一等公民，Reducer/Checkpoint/节点返回值零摩擦
- **实施 4 阶段**：P0 骨架(脚手架+空图+happy path) → P1 数据层(AKShare+20指标+缓存) → P2 分析层(Agent+prompt+报告模板) → P3 输出层(Word/PPT+Gradio打磨)
- **MVP 范围**：仅 AKShare 数据源，无 Tavily/Chroma/巨潮PDF/DCF 定量计算。v2.0 扩展 DCF、外部搜索、RAG、图表
- **分析年份跨度**：动态，尽量拉 5 年，不足则有多少用多少，最低 2 年（保证同比变化率可计算），低于 2 年报错
- **同业选择**：默认申万同三级行业市值 Top 5；用户可手动输入对标股票代码覆盖自动选取
- **数据降级策略**：必需数据（三大报表）缺失→报错终止；非必需（同业、研报、搜索）缺失→标记 N/A 继续
- **DCF 参数**：预测期 5 年，终端增长率 2%，市场风险溢价 7%（硬编码），无风险利率动态拉取（失败降级 1.8%），FCF 分阶段增长（前 3 年历史均值，后 2 年线性衰减至 g）
- **DCF 输出原则**：输出估值区间 + 敏感性分析（WACC ±1%、g ±0.5%），不输出单一精确数字
