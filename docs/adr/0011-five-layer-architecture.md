# ADR-0011: Five-Layer Multi-Agent Architecture

**Status**: Accepted  
**Date**: 2026-06-30

## Context

本项目最初采用 FA/IA 双 Agent 架构（ADR-0002），输出财务分析报告和投资分析报告。ADR-0009 延后了多 Agent 辩论机制，ADR-0010 设计了 tool calling 重构但未落地。

在调研 TradingAgents (arXiv:2412.20138) 后，决定转向完整的多 Agent 交易决策架构。核心动机：

1. **作品集定位升级**：从"分析报告生成器"升级为"多 Agent 交易决策系统"，展示角色专业化、辩论机制、风险压力测试等 Agent 架构能力
2. **减少确证偏误**：Bull/Bear 辩论 + Risk Management 多方辩论，通过对抗减少单一视角的偏见
3. **结构化输出**：agent 间通信从自由 Markdown 改为 Pydantic 结构化对象，支持 A2A 信息传递和确定性校验

## Decision

采用 TradingAgents 的 5 层架构，适配本项目的数据层和合规要求。

### 架构总览

```
PREP → Layer I (4 分析师并行) → Layer II (Bull/Bear 辩论) → Layer III (Trader)
  → Layer IV (Risk Management 辩论) → Layer V (Fund Manager) → 报告生成
```

### Layer I: Analyst Team（4 个并行分析师）

| Agent | 职责 | 数据来源 |
|-------|------|---------|
| 宏观分析师 | 宏观经济、货币政策、行业政策 | PREP: 宏观指标 + 政策动态 + key_events |
| 基本面分析师 | 财务报表、盈利能力、成长性、估值 | PREP: 三大报表 + 四维度 + 杜邦 + 估值 + 同业 |
| 技术面分析师 | 价格走势、技术指标、支撑压力位 | PREP: K 线序列 + MACD/RSI/布林带/KDJ |
| 舆情分析师 | 新闻舆情、事件影响、情感分析 | PREP: 新闻列表 + key_events（情感分析由 agent LLM 完成） |

**数据注入方式**：PREP 一次性全量注入，无 tool calling。每个分析师的数据需求是确定性的（每次分析都要全部数据），LLM 无决策空间。tool calling 保留给未来的"快速模式"（交互式问答）。

**输出**：每 agent 专属 Pydantic schema（结构化分析对象 + 章节 Markdown 文字）。

### Layer II: Researcher Team（Bull/Bear 辩论）

- **Bull + Bear**：2 轮辩论，每轮用 LangGraph `Send` 并行产出（不串行等待）
- Round 1：各自立论
- Round 2：读到对方 Round 1 论点后反驳
- **Research Manager**：综合辩论结论，输出给 Trader

**无工具**：只读 4 份分析师报告。

### Layer III: Trader

基于 Research Manager 结论 + 分析师报告，产出交易计划（买卖方向 + 逻辑）。

**无工具**：只读上游输出。

### Layer IV: Risk Management Team（风险压力测试）

- **3 个辩论者**：激进 / 保守 / 中性，2 轮辩论，每轮 `Send` 并行
- **Risk Judge**：综合辩论结论，产出 `final_trade_decision`
- **PREP 风控指标注入**：回撤/波动率/Beta/VaR 作为 prompt context 直接注入（不用工具查）

**无工具**：只读 Trader 计划 + 分析师报告 + PREP 风控指标（prompt context）。

### Layer V: Fund Manager

审阅 `final_trade_decision`，三种决策：
- **Approve**：→ 报告生成
- **Reject**：→ 报告标注"未通过审批" → END
- **Return to Trader**：→ 回到 Layer III（最多 1 次，防死循环）

### Graph Topology

LangGraph 静态展开（无循环边）：

```
START → check_cache → [fetch_data →] validate → compute_metrics
  → Send([macro, fundamental, technical, sentiment])
  → Send([bull_r1, bear_r1])
  → Send([bull_r2, bear_r2])
  → research_manager
  → trader
  → Send([aggressive_r1, conservative_r1, neutral_r1])
  → Send([aggressive_r2, conservative_r2, neutral_r2])
  → risk_judge
  → fund_manager
  → [trader（如果退回）] 或 generate_report
  → END
```

### State 结构

混合模式：
- **PREP 字段**：保持扁平（兼容现有代码）
- **Agent 输出**：嵌套（`analyst_reports: dict[str, AnalystReport]` / `debate_history: list[DebateMessage]` / `trade_decision: TradeDecision`）

### PREP 扩展

PREP 子图新增数据拉取和计算：

| 新增数据 | 拉取位置 | 计算 | 服务对象 |
|---------|---------|------|---------|
| 日 K 线（1-2 年 OHLCV） | `fetch_data` | - | 技术面 + 风控 |
| 沪深 300 K 线 | `fetch_data` | - | 风控（Beta 基准） |
| 宏观指标（CPI/PMI/M2/LPR） | `fetch_data` | `metrics/macro.py` | 宏观 |
| 新闻列表 | `fetch_data` | `metrics/sentiment.py`（统计） | 舆情 |
| 技术指标 | - | `metrics/technical.py` | 技术面 |
| 风控指标 | - | `metrics/risk.py` | 风控（Layer IV） |

**情感分析**：PREP 只做统计（count/density），情感判断由舆情 agent 的 LLM 完成（`source_type: llm_inference`，不做 Claim 校验）。

### 报告结构

10 章结构，分析师主导：

| 章 | 标题 | 内容来源 |
|----|------|---------|
| 1 | 封面 | 标的名称、日期、评级 |
| 2 | 执行摘要 | Fund Manager 最终决策 + 关键理由 |
| 3 | 宏观环境分析 | 宏观分析师输出 |
| 4 | 基本面分析 | 基本面分析师输出（四维度+杜邦+估值） |
| 5 | 技术面分析 | 技术面分析师输出（趋势+指标+关键价位） |
| 6 | 舆情与事件分析 | 舆情分析师输出（新闻+事件+情感） |
| 7 | 多空辩论摘要 | Bull/Bear 辩论核心论点 + Research Manager 结论 |
| 8 | 交易建议 | Trader 计划 + Risk Management 评估 + Fund Manager 批准 |
| 9 | 风险提示 | Risk Management 辩论中的风险点 + PREP 风控指标 |
| 10 | 免责声明 | AI 生成 + 仅供参考 + 不构成投资建议 |

### LLM 调用预算

| 场景 | LLM 调用次数 | 预估延迟 |
|------|-------------|---------|
| 最少（无退回） | 14 | ~75s |
| 多轮辩论（2 轮） | 18 | ~95s |
| 含 1 次退回 | 20 | ~110s |

### Claim 校验（分 Agent 粒度）

| Agent | Claim 嵌入 | 溯源类型 | 验证策略 |
|-------|-----------|---------|---------|
| 基本面 | 强制 | data（`field_ref`）+ computational（公式重算） | `metrics/` 纯函数重算 |
| 风控（Layer IV） | 强制 | data（`field_ref`）+ computational | `metrics/risk.py` 重算 |
| 舆情 | 强制 | event（`event_ref` 查 key_events） | 引用存在性校验 |
| 宏观 | 不嵌入 | 标注 `source_type: llm_inference` | 跳过（FinGround regulatory 类型） |
| 技术面 | 部分 | 数字结论标 `field_ref`，定性判断标 `llm_inference` | 数字部分查 `metrics/technical.py` |

### MCP Server

- **本项目撤销 MCP**（ADR-0008 Superseded）：内部 Agent 直接调 Python 函数，同进程无需 MCP 协议
- **未来独立项目**：可另起项目将数据层或 Agent 封装为 MCP Server，与本项目解耦

## Consequences

- **撤销 ADR-0002**：FA/IA 双 Agent 模型废弃，职责并入 4 个并行分析师
- **撤销 ADR-0008**：MCP Server 从本项目退役，mcp_server.py 删除
- **推翻 ADR-0009**：辩论机制不再延后，作为核心组件立即采纳
- **部分撤销 ADR-0010**：Step 1（tool calling）撤销，Step 2（reflection）和 Step 3（Claim 校验）保留
- **PREP 子图扩展**：新增 K 线/宏观/新闻拉取 + 4 个新 metrics 模块
- **延迟增加**：从 ~20-30s 增加到 ~95s（5-8 倍 LLM 调用）
- **成本可控**：单次分析 ~¥0.12-0.24（DeepSeek V3）
- **合规声明保留**：即使给出交易建议，仍声明"不构成投资建议"（和 TradingAgents 一致）

## References

- [TradingAgents (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138) — 5 层架构参考
- [FinGround (arXiv:2604.23588)](https://arxiv.org/abs/2604.23588) — Claim 6 类分类法 + computational 公式重算
- [LangChain qa_sources](https://python.langchain.com/docs/how_to/qa_sources/) — 结构化 Citation 对象
- [ADR-0002](0002-pure-llm-agents.md) — FA/IA 双 Agent 模型（Superseded）
- [ADR-0008](0008-mcp-server.md) — MCP Server（Superseded）
- [ADR-0009](0009-defer-multi-agent-debate.md) — 延后辩论机制（Reversed）
- [ADR-0010](0010-tool-use-refactor.md) — 工具使用重构（Step 1 撤销，Step 2/3 保留）
- [docs/design/claim-verification-research.md](../design/claim-verification-research.md) — Claim 校验设计研究档案
- [CONTEXT.md](../../CONTEXT.md) — 领域模型（已更新 5 层架构术语）
