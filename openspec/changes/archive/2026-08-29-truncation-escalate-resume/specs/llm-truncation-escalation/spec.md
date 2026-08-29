# Delta for LLM Truncation Escalation

## ADDED Requirements

### Requirement: 截断升级重试以续写进行

管线 LLM 调用层（call_llm_streaming）在收到输出截断错误（OutputTruncatedError）后发起的升级重试 SHALL 以续写方式进行：请求 SHALL 携带首轮已生成正文的尾部（复用 gateway 续写机制的尾部注入与续写指令），配额 SHALL 取翻倍预算（131072）扣除已生成部分的剩余值；SHALL NOT 以原始 messages 从头重新生成。两轮均截断时 SHALL 维持既有上抛语义（OutputTruncatedError）。非截断错误的重试语义 SHALL 不变（预算不翻倍、不携带续写上下文）。

#### Scenario: 升级重试续写而非从头重跑

- GIVEN 首轮生成产出部分正文后以 finish_reason=length 截断（含 gateway 内续写一次仍未完成）
- WHEN 调用层发起升级重试
- THEN 重试请求 SHALL 在原始 messages 末尾追加携带首轮正文尾部的续写指令消息
- AND 重试配额 SHALL 为 131072 减去已生成部分的估算 token
- AND 最终返回值 SHALL 为首轮正文与续写正文拼接

#### Scenario: 两轮截断仍失败上抛

- GIVEN 升级续写后仍以 finish_reason=length 截断
- WHEN 调用层重试次数耗尽
- THEN SHALL 上抛 OutputTruncatedError（既有语义不变）

#### Scenario: 首轮无正文的截断

- GIVEN 首轮截断时未产出任何正文
- WHEN 升级重试发起
- THEN 配额 SHALL 为完整翻倍预算（131072），续写指令消息仍追加（尾部为空）

#### Scenario: 非截断错误重试不携带续写上下文

- GIVEN 首轮以可重试的非截断错误失败（如空输出）
- WHEN 调用层重试
- THEN 请求 SHALL 使用原始 messages 与原始预算（不翻倍、不追加续写指令）
