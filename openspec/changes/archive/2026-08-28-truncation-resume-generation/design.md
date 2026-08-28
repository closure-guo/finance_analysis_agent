# Design — 截断续写（llm-output-resume）

## Context

A 股 deep 分析的长 JSON 报告反复触发 `finish_reason=length`：方舟 GLM 的 reasoning 与正文共享 `max_tokens`（16384），report/trader/fund_manager 节点的长输出常在正文段被掐断。现状（`_llm_utils.py:241-270`）是「完整重试 + max_tokens 加倍 32768」，但重试会**重新生成 already 完成的 reasoning/正文**，长节点在 32768 下仍常再截（本次 evals 批跑 7 条 deep 全挂佐证）。且 quick 模式（harness ReAct）走异步 `complete_stream_async`，**没有** `classify_outcome`，length 被静默当作正常结束——截断内容当完整结果用。

约束：gateway 是三模式（deep/quick/follow_up）公共入口；管线节点经同步 `complete_stream`，harness 经异步 `complete_stream_async`，evals 两者都可能；LANGFUSE 观测走 `start_as_current_observation` generation。

## Goals / Non-Goals

**Goals**
- 截断后「续写缺失尾部」而非「重跑全文」，显著提高长输出完成率。
- 续写逻辑收敛在 gateway 三个 complete 入口，调用方零改动、自动继承。
- 续写/再截断在 Langfuse 可追溯（`resume_count` / `truncated`）。
- 非截断路径行为完全不变（零额外调用）。

**Non-Goals**
- 不实现「按 token 边界断词/重排」——拼接采用直接连接，断词由模型输出质量承担（模型续写自然以句/段对齐，实测可接受）。
- 不改变 `OutputTruncatedError` 的对外类型与 retryable 语义（续写上限仍按既有错误契约上抛）。
- 不解除 32768 硬编码（那是另一条独立优化线；续写让翻倍重试的触发频率大幅下降）。

## Decisions

### D1：续写上下文构造 = 尾部注入（基线）+ 进度标注（JSON 可解析时）+ assistant prefill（API 支持时）

**问题拆解**：模型要正确续写，需要两类信息——**内容信息**（之前生成了什么，防重复、保结构）与**进度信息**（当前断点在哪、还剩什么没写）。单靠「前段正文」只给了内容信息，进度要靠模型从尾部盲猜；深层 JSON 截断时猜错概率高。三层载体按可靠性叠加，每层有明确触发条件：

1. **尾部注入（基线，无条件）**：截断时保存已 yield 的前段正文（同步版 `_answer` / 异步版 `answer` 累积），把**尾部约 4000 字符**与续写指令「你正在续写一份分析报告，直接无缝继续输出剩余部分，不要重复以上已输出的内容」拼入续写请求。适配 OpenAI 兼容端点（把续写指令并入 user/prompt 消息），任何端点可用。
2. **进度标注（输出为 JSON 且可部分解析时）**：对已生成文本做**尽力部分解析**，标出已闭合字段（✅）、进行中字段与断点位置（⏳）、未开始字段（⬜），随续写请求注入。进度从已生成文本**计算**而来（扫描 JSON 已闭合的顶层字段、标记最后一个未闭合字段），不是模型猜的。部分解析失败时降级为仅尾部注入，与既有 `parse_degraded` 降级语义同族（`analysts.py:92-114`）。
3. **assistant prefill（API 支持时，可选增强）**：若目标 API 支持 assistant prefill / continuing message，直接把已生成正文作为 assistant 消息前缀续写，效果最自然。不确定支持与否的端点跳过该层，不阻塞基线。

续写返回正文追加到前段，`finish_reason` 以续写段为准。

**理由**：LLM 原生能力是续写一段既有文本；切分/重排会破坏 markdown/JSON 结构，且实现成本高。续写指令明确「不重复」以抑制头重复；进度标注显式告知「还剩什么没写」，把「进度信息」从模型盲猜变为确定性计算；prefill 层解决「内容信息」的最自然形态。三层各自独立可测，降级链清晰。

### D2：续写预算 = 剩余输出配额，不翻倍

**方案**：续写请求 `max_tokens` 取 `max(1, 原预算 - 前段已用估算)`（剩余配额）。不做 2 倍翻倍。

**理由**：续写只产出缺失尾部，剩余配额在统计上足够；翻倍会引入「配额越开越大」的失控面。已调研（Alternative）：翻倍并行于续写 → 两变量耦合难调试，弃。

### D3：续写仅 1 轮，再截断即终止

**方案**：续写结果若仍 `finish_reason=length`，停止继续，抛 `OutputTruncatedError`（保留原错误类型），观测 metadata 写 `resume_count=1, truncated=true`。

**理由**：限制成本与延迟 +1 次调用；「永远截断」场景防死循环。Alternative：最多 N 轮续写直至写出 → 延迟不可控，弃。

### D4：统一在 gateway complete 三入口实现，共用 `_resume_request_kwargs` helper

**方案**：`complete_text` / `complete_stream`（同步）/ `complete_stream_async`（异步）在各自「检测到 length」分支调用同一续写助手函数，构造续写 kwargs 并递归/循环调用。观测：续写时在 generation metadata 追加 `resume_count`；再截断补 `truncated=true`。

**理由**：三入口共享同语义，规避 `_llm_utils` 层重复（现状 32768 翻倍重试在 `_llm_utils`、同步流在 gateway、异步流无兜底——三个地方三种行为，正是本次要收敛的碎片化）。

### D5：异步路径补 `classify_outcome` 联动

**方案**：`complete_stream_async` 的 `finish=="length"` 分支从「静默 finished(None)」改为走续写；续写不成再按 `classify_outcome` 语义抛 `OutputTruncatedError`。修复「quick 模式截断被当正常结果」的静默问题。

**理由**：spec「截断时正文为空」要求统一；也是本次 root-cause 里异步路径的独立缺陷。

## Risks / Trade-offs

- [续写多 1 次 LLM 调用 → 成本/延迟 +1] → 仅截断时触发（统计低频，非每请求）；续写预算用剩余配额不放大。
- [拼接处头部重复（模型无视「不重复」指令）] → spec 锁定拼接契约直接连接；可后续用简单去叠（连续 N 字符相同则裁一刀）作为防御，本期不做。
- [异步路径从静默→抛错，行为变化] → 属 intent 修复（静默截断本就是 bug），spec 已定义；evals 隔离已存在。
- [续写后 Langfuse generation 是两条 observation] → 语义上更诚实（两次生成）；metadata `resume_count` 标识关联，本次不重组父子。

## Migration Plan

1. 纯新增/收敛行为，无数据迁移。
2. `classify_outcome` 保持原签名；`OutputTruncatedError` 类型与 retryable 不变，`_llm_utils` 32768 翻倍重试可保留（续写优先，翻倍成为 fallback）——两段共存，行为渐进收敛。
3. 回滚：撤 gateway 三入口改动即恢复现状（`_llm_utils` 未动，风险低）。

## Open Questions

1. ~~续写指令措辞按节点区分？~~ **已决策（本期）**：统一一句话续写指令 + 双层进度标注（[D1](#d1续写上下文构造--尾部注入基线--进度标注json-可解析时--assistant-prefillapi-支持时)），结构信息由标注承担，无需按节点定制措辞；如 evals 暴露问题再分。
2. `resume_count` 是否要同步落到 SQLite `analyst_reports`（session 层追溯）？——本期只落 Langfuse observation metadata；session 层是后续增量（另走 delta）。
3. 进度标注的解析深度：只标顶层字段（✅/⏳/⬜），还是展开嵌套（如 `key_findings` 数组内元素级）？——倾向顶层起步，嵌套元素级解析成本高、收益低（续写模型看尾部即可推断数组内部），如 evals 暴露再加深。