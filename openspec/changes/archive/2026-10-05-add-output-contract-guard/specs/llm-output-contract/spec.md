# Delta for llm-output-contract

## ADDED Requirements

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
