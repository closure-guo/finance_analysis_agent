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

### Requirement: 纯文本交付物输出合同

凡 LLM 文本直接进入用户可见交付物（报告章节、研究聚焦摘要、导出文件等）的路径，SHALL 在嵌入交付物前经确定性输出校验：泄露检测（任务独白标记、非目标语言段落占比）与截断检测（`finish_reason=length`，或正文以句中悬空收尾）。判定违约 MUST 定向重试 1 次（附「直接输出最终文本、禁止解释思考过程」强化指令）；重试仍违约 SHALL 回退到不依赖 LLM 新输出的结构化兜底；系统 MUST NOT 将原始模型输出（含任务独白、半句截断）直接嵌入交付物。当 `content` 为空而 reasoning 非空时，MUST NOT 将 reasoning 作为交付文本回退（reasoning 仅进 trace 观测）。校验判定结果与命中规则 SHALL 进 trace metadata。以中文为交付目标的调用，校验 SHALL 以中文字符占比为泄露信号之一；规则阈值 MUST 以真实泄露样本与干净样本双向校准（误伤干净输出的判定视为校验器缺陷）。

#### Scenario: 思考独白泄露拦截

- GIVEN 使用思考型模型（如 glm-5.3）生成研究聚焦摘要
- WHEN 模型在 content 通道输出任务独白（"The user wants …"、"Draft:" 等标记）而非仅最终摘要
- THEN 校验判定违约，该文本不得出现在交付物中，触发定向重试

#### Scenario: 重试仍违约回退结构化兜底

- GIVEN 首次输出判定违约
- WHEN 定向重试后输出仍含泄露或截断
- THEN 回退到调用方既有结构化兜底（如 report.py 的各层 summary 拼接），交付物不含任何原始模型输出

#### Scenario: raw_reasoning 禁止作为交付回退

- GIVEN 模型返回 content 为空、reasoning_content 非空
- WHEN 调用方获取交付文本
- THEN 不得将 reasoning 嵌入交付物，按违约处置走重试或兜底；reasoning 仅出现在 trace 观测中

#### Scenario: 干净输出直通不误伤

- GIVEN 模型输出合规纯文本摘要（如 2026-10-04 中远海能报告案例）
- WHEN 校验执行
- THEN 判定通过，文本直接嵌入交付物，不重试、不兜底

#### Scenario: 截断检测

- GIVEN 输出预算被推理消耗（usage output 恰为 max_tokens）
- WHEN `finish_reason=length`，或 finish_reason 不可得而正文以句中悬空收尾（如「PE_ttm 85.」数字中断）
- THEN 按违约处置（续写或重试或兜底），不得交付句中截断的半句

#### Scenario: 判定结果可观测

- WHEN 校验执行完毕
- THEN trace metadata 携带判定结果（pass/leak/truncated）与命中规则，`complete_text` 观测 metadata 携带 `finish_reason` 与 `resume_count`

### Requirement: 分析师输出批注剥离

分析师 LLM 输出经解析合同装配为 AnalystReport 时，SHALL 对 summary、plain_conclusion、key_findings、markdown 四个交付字段执行确定性批注剥离：命中「括号内以『需修正』收尾」的自我修正批注（括号内容 ≤48 字符且无嵌套括号）SHALL 整体移除（含括号本身）；「无需修正/不必修正/不需修正」否定形态（「需修正」紧邻前字符为「无/不/必」）与未被括号包裹的辩论/叙述用语 MUST NOT 被剥离；剥离命中数 SHALL 进 trace metadata（`editor_notes_stripped`）。批注剥离 MUST NOT 应用于辩论、裁决、交易决策等其他 LLM 文本。

#### Scenario: 自我修正批注被剥离

- **GIVEN** 技术分析师 key_findings 含「收盘价高于MA20约1.9%的偏离反向（低于MA20约1.9%需修正）」（2026-10-05 深南电路 002916 实例）
- **WHEN** AnalystReport 装配执行批注剥离
- **THEN** 该条目 SHALL 变为「收盘价高于MA20约1.9%的偏离反向，…」（批注含括号整体移除，其余文字保留）
- **AND** trace metadata SHALL 记录 `editor_notes_stripped` ≥ 1

#### Scenario: 否定形态不误伤

- **GIVEN** 某交付字段含「（中报口径无需修正）」
- **WHEN** 批注剥离执行
- **THEN** 该括号内容 SHALL 原样保留

#### Scenario: 辩论用语不触碰

- **GIVEN** 文本含「需修正其『多空证据实质均衡』的定性」（未被括号包裹，2026-10-05 赛轮轮胎辩论用语）
- **WHEN** 批注剥离执行
- **THEN** 该文本 SHALL 原样保留

#### Scenario: 非收尾形态不误伤

- **GIVEN** 括号内容为「该结论需修正后才成立」（「需修正」不在括号收尾位置）
- **WHEN** 批注剥离执行
- **THEN** 该括号内容 SHALL 原样保留

