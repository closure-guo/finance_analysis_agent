# Finance Analysis Agent

基于 LangGraph 的 A 股上市公司 AI 分析报告系统。输入股票代码，自动生成多 Agent 交易决策分析报告。

## 在线演示

[![Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-Spaces-blue)](https://closure-guo-finance-analysis-agent.hf.space)

**股票搜索与配置**

<img src="https://cdn.jsdelivr.net/gh/closure-guo/finance_analysis_agent@main/docs/assets/demo-search.gif" width="700" />

**报告生成与下载**

<img src="https://cdn.jsdelivr.net/gh/closure-guo/finance_analysis_agent@main/docs/assets/demo-report.gif" width="700" />

## 架构

<p align="center">
  <img src="https://cdn.jsdelivr.net/gh/closure-guo/finance_analysis_agent@main/docs/assets/graph.png" alt="LangGraph 运行时拓扑" width="700" />
</p>

> 图由 build_5layer_graph() 生成，Mermaid 源码见 [graph.mmd](docs/assets/graph.mmd)

五层架构：

| 层级     | 选型            | 职责                                                              |
| -------- | --------------- | ----------------------------------------------------------------- |
| L1 前端  | Gradio 5.x      | 表单输入 + 报告展示 + 文件下载                                    |
| L2 Agent | LangGraph       | 5 层架构 + 多 Agent 辩论 + Send 并行派发                          |
| L3 数据  | pandas + SQLite | AKShare 拉取 + 指标计算 + K 线/宏观/新闻 + 报表持久化 + 行情缓存  |
| L4 LLM   | DeepSeek        | LiteLLM 路由                                                      |

> L2 Agent 5 层：4 分析师并行 → Bull/Bear 辩论 → Trader → Risk Management 辩论 → Fund Manager（详见 [ADR-0011](docs/adr/0011-five-layer-architecture.md)）

## 快速开始

**环境要求**：Python >= 3.12, uv

```bash
# 安装依赖
uv sync

# 启动
uv run python -m finance_agent.app
```

浏览器打开 Gradio 页面，输入股票代码（如 600519）即可。

## 环境变量配置

首次运行前需要配置 LLM API Key，否则会报错。

```bash
# 复制模板并填入你的 API Key
cp .env.example .env
```

### 变量一览

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `LLM_API_KEY` | **是** | — | LLM API Key；也可用 `DEEPSEEK_API_KEY` 作为回退 |
| `LLM_MODEL` | 否 | `deepseek/deepseek-v4-pro` | 模型名，litellm 格式 |
| `LLM_BASE_URL` | 否 | `https://api.deepseek.com` | API 端点 |
| `LLM_THINKING` | 否 | `enabled` | 思考模式 `enabled` / `disabled` |
| `LLM_REASONING_EFFORT` | 否 | `max` | 思考强度 `low` / `high` / `max` |
| `REPORTS_DIR` | 否 | `reports` | 报告输出目录 |
| `EVENT_SOURCE` | 否 | `auto` | 事件数据源 `builtin` / `web` / `auto` |

### 示例

**使用 DeepSeek（默认）**：

```bash
# .env
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
```

**使用其他 LLM（通过 litellm 格式）**：

```bash
# .env
LLM_API_KEY=sk-xxxxxxxxxxxxxxxx
LLM_MODEL=openai/gpt-4o
LLM_BASE_URL=https://api.openai.com/v1
```

## 项目结构

```
src/finance_agent/
├── graph.py              # LangGraph 主图 (build_graph + build_5layer_graph)
├── state.py              # AnalysisState TypedDict (含 Annotated reducers)
├── citation.py           # 确定性引用校验器 (Claim/CitationReport/verify_claims)
├── models.py             # 结构化输出模型 (AnalystReport/DebateMessage/TradeDecision)
├── app.py                # Gradio 前端入口
├── app_search.py         # 股票搜索
├── formatters.py         # LLM 上下文格式化
├── routing.py            # 路由函数 + Send 并行派发
├── llm.py                # LLM 调用封装
├── nodes/                # 图节点
│   ├── cache.py          # check_cache
│   ├── fetch.py          # fetch_data
│   ├── validate.py       # validate_financials (勾稽校验)
│   ├── compute.py        # compute_metrics (含技术指标 + 风控)
│   ├── analysts.py       # Layer I: technical_analyst
│   ├── debate.py         # Layer II: bull/bear debater
│   ├── research_manager.py # Layer II: research_manager
│   ├── trader.py         # Layer III: trader
│   ├── risk.py           # Layer IV: 3 debaters + risk_judge
│   ├── fund_manager.py   # Layer V: fund_manager
│   ├── citation_node.py  # 引用校验节点
│   ├── report.py         # 5 层报告生成
│   ├── _llm_utils.py     # 共享 LLM 工具 (parse_json_response)
│   ├── output.py         # generate_file (Word/PPT 生成)
│   ├── fa.py             # 旧架构 (ADR-0011 已废弃)
│   ├── ia.py             # 旧架构 (ADR-0011 已废弃)
│   └── merge.py          # 旧架构 (ADR-0011 已废弃)
├── metrics/              # 指标计算（纯函数）
│   ├── validate.py       # 勾稽校验 4 规则
│   ├── solvency.py       # 偿债 5 指标
│   ├── profitability.py  # 盈利 5 指标
│   ├── efficiency.py     # 运营 4 指标
│   ├── cashflow.py       # 现金流 6 指标
│   ├── dupont.py         # 杜邦 3 层分解
│   ├── traffic_light.py  # 红黄绿灯 + 健康度评分
│   ├── relative.py       # 相对估值
│   ├── garp.py           # GARP 筛选
│   ├── technical.py      # 技术指标 (MA/MACD/RSI/BOLL/KDJ)
│   └── risk.py           # 风控指标 (回撤/波动率/Beta/VaR)
├── data/                 # 数据层
│   ├── akshare_client.py # AKShare API 封装
│   └── cache.py          # SQLite 持久化 + 缓存
├── events/               # 关键事件获取
│   ├── pipeline.py       # 事件管线（3 级降级）
│   ├── preset_loader.py  # L1 预设事件
│   ├── web_fetcher.py    # L2 DuckDuckGo 搜索
│   └── fallback.py       # L3 兜底注释
├── export/               # 报告导出
│   ├── parser.py         # Markdown 解析器
│   ├── docx_exporter.py  # Word 导出
│   └── pptx_exporter.py  # PPT 导出
├── prompts/              # LLM prompt
└── templates/            # 报告模板
```

## 实施阶段

- [x] **P0 骨架** — 脚手架 + 空图 + Gradio 表单 + stub happy path
- [x] **P1 数据层** — AKShare + 20 指标 + 缓存
- [x] **P2 分析层** — prompt 工程 + 投资报告
- [x] **P3 输出层** — 综合分析 + Word/PPT 导出 + UI 打磨
- [x] **P4 5 层架构重构** — 多 Agent 辩论 + 交易决策 + 引用校验 + 技术指标/风控 (ADR-0011)

## 文档

- [PRD](docs/PRD.md) — 产品需求文档
- [架构设计](docs/architecture.md) — 系统架构详细设计
- [领域上下文](CONTEXT.md) — 术语表和分析框架定义
- [ADR](docs/adr/) — 架构决策记录

## 思路来源

本项目的多 Agent 架构和引用校验机制借鉴了以下研究与开源项目：

| 来源 | 用途 | 说明 |
|------|------|------|
| [TradingAgents (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138) | 5 层架构 | 4 分析师并行 → Bull/Bear 辩论 → Trader → Risk Management 辩论 → Fund Manager 的整体流程参考 |
| [FinGround (arXiv:2604.23588)](https://arxiv.org/abs/2604.23588) | 引用校验 | Claim 6 类分类法 + computational 公式重算机制（见 [citation.py](src/finance_agent/citation.py)） |
| [LangChain qa_sources](https://python.langchain.com/docs/how_to/qa_sources/) | 引用结构 | 结构化 Citation 对象设计参考 |

> 数据层（AKShare）、指标计算（四维度 + 杜邦 + 技术指标 + 风控指标）和报告结构为自主设计，详见 [CONTEXT.md](CONTEXT.md) 和 [ADR](docs/adr/)。

## License

MIT
