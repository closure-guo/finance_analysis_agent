# ADR 0008: MCP Server for Claude Desktop Integration

**Status**: Accepted
**Date**: 2026-06-07

## Context

系统 MVP 已完成，采用 Gradio 前端 + LangGraph Agent + pandas/SQLite 数据层 + DeepSeek LLM 的四层架构。PRD 和架构文档预留了「后期可将整个 Agent 封装为 MCP Server」的扩展方向。

当前痛点：每次分析必须打开 Gradio Web UI，手动输入股票代码，等待完整报告生成。无法在 Claude Desktop / IDE 对话中直接调取分析能力，也无法针对单一维度（如偿债、估值）做轻量查询。

## Decision

新增 MCP Server（stdio 传输），暴露 5 个 tool，只返回结构化指标数据，不调用 LLM 生成分析文字。Claude 自己充当分析师角色，基于返回的指标做解读和追问。

### 5 个 Tool

| Tool | 对应 L3 模块 | 返回内容 |
|------|-------------|---------|
| `get_financial_health` | solvency + profitability + efficiency + cashflow + traffic_light | 四维度 20 指标 + 红黄绿灯 + 健康度评分 |
| `get_valuation` | relative + garp | PE/PB 同业对比 + GARP 筛选结果 |
| `get_dupont_analysis` | dupont | 3 层杜邦拆解树 |
| `get_peer_comparison` | fetch (同业数据) | 同业公司财务数据对比表 |
| `get_financial_statements` | fetch (三大报表) | 原始资产负债表 / 利润表 / 现金流量表 |

### 关键设计选择

1. **粒度：按分析维度拆分，非整体封装**。Claude 可以按需调取单个维度，不必每次跑完整流水线。token 开销从 ~10000 字降到 ~2000-4000 字/次。

2. **返回原始指标，不返回 LLM 分析文字**。Claude 本身是 LLM，让它直接解读结构化数据，避免 DeepSeek 和 Claude 双重解读的 token 浪费。

3. **复用现有 PREP 子图**（check_cache → fetch_data → validate → compute_metrics）。不重写数据层逻辑，保证 MCP 和 Gradio 走完全一样的缓存、校验、计算路径。

4. **返回格式带红黄绿灯 + 阈值**。每个指标包含 value / light / thresholds，Claude 无需猜测行业特定阈值（如白酒存货周转率 override），减少幻觉风险。

5. **stdio 传输**。Claude Desktop 直接 spawn server 进程，零部署。

6. **不暴露 `generate_report`**。Claude 自己就是报告生成器。

## Consequences

- Gradio 前端与 MCP Server 并存，共享同一套 L3 数据层
- MCP Server 不依赖 LLM（无 DeepSeek 调用），tool 响应秒级返回
- PREP 子图需从主图中提取为可独立调用的入口
- tool 接口一旦发布给 Claude Desktop 配置，变更需考虑向后兼容
- 未来如需支持远程/多客户端，可在此基础上增加 Streamable HTTP 传输
