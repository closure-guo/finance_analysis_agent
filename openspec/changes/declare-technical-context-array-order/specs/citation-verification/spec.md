# Delta for Citation Verification

## MODIFIED Requirements

### Requirement: 序列引用负索引语义

引用校验器对序列型 field_ref SHALL 支持负索引（-1 = 最新一期，-N = 倒数第 N 期），该语义与序列长度及上下文裁剪窗口解耦。技术指标 context 的窗口说明 SHALL 明示负索引约定（"field_ref 引用序列值时用负索引：-1=最新一期"）。正索引按底层序列原位解析（legacy 语义不变）。
(Previously: 同前句；未涉及数组顺序声明)

技术指标 context SHALL 同时声明序列数组内部顺序：序列为**时间正序（旧→新）**，列表**末尾元素为最新一期**；LLM 引用负索引值前 SHALL 核对所在序列尾部（-1 即最后一个元素），不得将展示容器首元素或记忆中历史行情当作最新值。
(Previously: 无此条款——incident 022 中际旭创 13 条技术 claim 因方向歧义整体期次错位)

#### Scenario: 负索引解析为最新值

- GIVEN state 中某指标序列为升序时间序列且任意长度
- WHEN claim 的 field_ref 以 `-1` 索引该序列（如 `technical_indicators.MA.5.-1`）
- THEN 校验器 SHALL 取序列最后一个元素作为 ground truth

#### Scenario: 裁剪窗口变更不影响校验语义

- GIVEN 分析师 context 的序列裁剪窗口从 60 期调整为任意值
- WHEN LLM 按负索引约定引用序列值
- THEN 校验结果 SHALL 不因窗口变更而改变（负索引与长度无关）

#### Scenario: 数组方向歧义消除

- GIVEN 技术指标 context 展示时间正序序列（旧→新）且末尾为最新一期
- WHEN LLM 引用「最新一期」的指标值
- THEN LLM SHALL 引用序列末尾元素（`-1` 或对应的负索引），SHALL NOT 将窗口首元素（最旧一期）当作最新值
- AND 校验结果 SHALL 与其真实最新值一致（修复前该场景系统性期次错位 FAIL——incident 022）

#### Scenario: 引用自证约束

- GIVEN LLM 反幻觉规则要求引用负索引值前核对序列尾部
- WHEN LLM 声明「最新 MA5 = X」
- THEN LLM SHALL 从序列末尾元素读取 X（不得凭记忆或展示首元素推断）
- AND 该自证要求 SHALL 在技术分析师 prompt 中可判定生效（发布经 deploy_prompts.py）