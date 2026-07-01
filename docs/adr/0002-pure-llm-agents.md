# ADR-0002: Agent Nodes Are Pure LLM Consumers

## Status: Superseded by [ADR-0011](0011-five-layer-architecture.md)

> **Superseded**: 本 ADR 的 fa/ia 双 Agent 模型已被 ADR-0011 的 5 层架构（4 分析师 + Bull/Bear 辩论 + Trader + Risk Management + Fund Manager）替代。FA/IA Agent 解散，职责并入新的 4 个并行分析师。"数据层与 Agent 层分离"的分层原则仍然有效，被 ADR-0011 继承。

## Context

初始设计中，Agent 节点混合了三种职责：

1. 数据拉取（fa_peer_compare 调 MCP 拉同业数据）
2. 计算（ia_valuation 调 MCP 执行 DCF Python 代码）
3. LLM 推理（归因分析、报告撰写）

这违反了五层架构的分层原则：L2 Agent 层不应该承担 L4 数据层的职责。

## Decision

Agent 节点改为**纯 LLM 消费者**：

- **只读** State 中的数据（四维度指标、红黄绿灯、同业对比、相对估值等）
- **只做** LLM 推理（解读数据、写分析文字）
- **不调** 外部服务（数据拉取和计算在数据准备子图中完成）
- **不写** 文件（报告文件生成由独立的 generate_file 节点负责）

所有数据拉取和计算集中在数据准备子图中完成，包括：

- 四维度 20 指标计算
- 杜邦分解（3 层）
- 红黄绿灯矩阵
- 同业对比计算
- 相对估值计算
- GARP 筛选

> 注：DCF 定量计算计划于 v2.0 实现，当前 MVP 不含 DCF。

节点从初始设计的 15 个精简到 8 个，Agent 子图从 4 节点精简到 2 节点（fa_analyze、ia_analyze 各自完成正文+摘要+模板组装）。

## Consequences

- 严格的分层：L4 管数据进出，L2 管思考，L3 管文件输出
- Agent 节点简单、可测试（用 mock State 即可测试）
- 数据准备节点变重，但职责单一
- 报告文件生成（Word/PPT）从 Agent 中剥离到独立的 generate_file 节点
- 数据拉取通过 Python 模块直接调用（MVP 无 MCP 层）
