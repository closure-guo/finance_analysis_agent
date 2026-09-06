# agent-evaluation-suite Specification Delta

## ADDED Requirements

> v1 范围（2026-09-04 决策）：数值型 claim（价格/涨跌幅/财务指标/市值）以规则
> 抽取 + 行情/财务数据离线校验，无需 LLM。事实型 claim（事件/日期/主体）抽取
> 需 LLM，属后续增量（v1 不纳入，避免无样本校验的猜测性指标）。

### Requirement: 事实性 claim 抽取

评估链路 SHALL 从最终报告抽取可验证 claim（数值型：价格/涨跌幅/财务指标；事实型：事件/日期/主体）。

#### Scenario: claim 抽取

- **WHEN** 评测样本含最终报告文本
- **THEN** 输出结构化 claim 列表，每条标注类型与文中位置

### Requirement: 证据校验与幻觉率

系统 SHALL 将 claim 对照证据源（K 线/财报真实数据 + 检索内容）判定 supported/contradicted/unverifiable；`hallucination_rate` = contradicted / 可验证 claim 总数，unverifiable 单列不进分子。

#### Scenario: 矛盾识别

- **WHEN** 报告中数值 claim 与真实数据矛盾（超出容差）
- **THEN** 计为 contradicted 并计入幻觉率分子

#### Scenario: 合理推断不惩罚

- **WHEN** claim 无法从证据源证实亦不矛盾
- **THEN** 计为 unverifiable 单列，不影响幻觉率

### Requirement: 幻觉率门禁

幻觉率上限 SHALL 纳入评测门禁并 nightly 追踪趋势。

#### Scenario: 超限拦截

- **WHEN** hallucination_rate 超过配置上限
- **THEN** 门禁失败并输出 contradicted claim 清单
