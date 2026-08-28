# llm-output-contract Specification

## Purpose

定义 LLM 结构化输出统一合同：凡 LLM 文本后续要 `json.loads` / Pydantic 校验 / 写库 / 进管线 / 进评估的路径，SHALL 经 `extract_json` → Pydantic validate → repair 重试 → profile fallback 的统一输出合同，禁止散落裸 `json.loads` / 裸 `float()` 直通；评估（LLM-as-a-Judge）输入变量在打分前同样过合同，空输入不照常打分。

## Requirements

### Requirement: 结构化输出统一合同

凡是 LLM 文本后续要 `json.loads` / Pydantic 校验 / 写库 / 进管线 / 进评估的路径，SHALL 经统一输出合同：`extract_json`（markdown fence、首尾噪声、第一个平衡对象）→ Pydantic validate → 失败生成 repair prompt（含 schema、错误、原输出）重试 1-2 次 → 仍失败按 profile fallback 换同能力模型 → 最终失败抛 `OutputContractError`（带 raw_excerpt 进 trace）。系统 MUST NOT 出现散落的裸 `json.loads` / 裸 `float()` 直通管线。

#### Scenario: 尾逗号容错不触发重试
- **WHEN** LLM 输出 JSON 含尾逗号（`,]` / `,}`）
- **THEN** extract 阶段直接清理解析成功，不消耗 repair 重试

#### Scenario: 空输出触发 repair 而非炸管线
- **WHEN** 模型返回空正文（reasoning 有内容、content 为空，如方舟 GLM thinking 后即止）
- **THEN** 输出合同走 repair 重试（带「直接输出合法 JSON」强化指令），仍失败抛 OutputContractError 由调用方按节点语义处理，不静默降级关键决策（如 fund_manager 不得静默 approve）

#### Scenario: 数值校验类型防御
- **WHEN** 结构化字段（如 citation 的 field_ref）解析结果为非数值容器类型（dict/list）
- **THEN** 校验按 FAIL（无法核验）返回，不抛 TypeError 中断管线

### Requirement: 评估链路输入合同

评估（LLM-as-a-Judge）的输入变量在提交打分前 SHALL 过合同：变量提取器 MUST 兼容 dict 与 pydantic 形态（LangGraph state 原样保留 pydantic 实例）；关键维度变量（debate_history/analyst_reports 等）SHALL 非空断言，为空时该维度 MUST 记为「输入缺失」跳过或显式标注，不得对空输入照常打分。

#### Scenario: pydantic state 提取
- **WHEN** 管线 state 中辩论记录为 pydantic DebateMessage 实例（LangGraph reducer 不序列化）
- **THEN** judge 变量提取器正常产出辩论文本，不因形态判断静默返回空串

#### Scenario: 空输入不打分
- **WHEN** 某评估维度依赖的变量（如 debate_quality 依赖 debate_history）为空
- **THEN** 该维度标记「输入缺失」（score=null + 原因），不出具看似正常的数字分数混入均值
