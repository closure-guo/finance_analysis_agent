# Agent 输出截断治理设计方案

> 版本：v1.0
> 状态：可落地实施
> 适用范围：基于大模型 API 构建的 Agent / 多轮对话系统（兼容 OpenAI、Anthropic、Gemini 等主流供应商）

---

## 1. 背景与问题定义

Agent 在单次模型调用中输出超过 `max_tokens` 时会被截断，引发四类典型故障：

| 编号 | 故障模式 | 危害等级 |
|---|---|---|
| F1 | 普通文本被截断，用户看到半截回复 | 中 |
| F2 | **工具调用（function call）在参数 JSON 中途被截断**，无法解析或解析出错 | 高 |
| F3 | `write_file`/`edit` 类工具因截断把**半成品内容写入磁盘** | 高（破坏性） |
| F4 | 截断发生在 assistant 消息中途，**续写拼接后构成非法消息序列**（如 functionCall 与 tool response 之间插入了文本），后续请求被 API 拒绝，陷入重试死循环 | 高 |

### 设计目标

1. **检出率 100%**：任何截断都必须被检测，不得静默通过；
2. **恢复有界**：恢复链路最多重试 N 次后明确报错，绝不无限循环；
3. **截断无害**：半截写操作永不落盘，半截工具调用永不执行；
4. **可观测**：每次截断、升级、续写都有指标和日志；
5. **渐进可落地**：分三阶段实施，每阶段独立可上线。

---

## 2. 总体架构：五层防线

```
┌─────────────────────────────────────────────────────────────┐
│  L1 输出预算管理  OutputBudgetManager                        │
│     按轮次类型分级分配 max_tokens，截断后一次性升级           │
├─────────────────────────────────────────────────────────────┤
│  L2 截断检测      TruncationDetector                         │
│     finish_reason 归一化 + 结构性完整性校验                  │
├─────────────────────────────────────────────────────────────┤
│  L3 恢复控制      RecoveryController（有界状态机）            │
│     升级重试 → 续写兜底 → 明确报错                           │
├─────────────────────────────────────────────────────────────┤
│  L4 工具调用防护  ToolCallGuard                              │
│     半截写操作拒绝落盘；谨慎处理截断 JSON                    │
├─────────────────────────────────────────────────────────────┤
│  L5 上下文减负    ContextPressureManager                     │
│     大结果落盘留指针、分级压缩、子代理隔离                   │
└─────────────────────────────────────────────────────────────┘
```

**核心原则**：截断是常态事件流，不是异常。harness 的健壮性体现在"检测—恢复—无害化"的闭环上。

---

## 3. 核心组件设计

### 3.1 L1：OutputBudgetManager —— 输出预算分级

不要全程使用固定 `max_tokens`。按轮次类型分级，并为截断预留升级空间。

```python
from dataclasses import dataclass
from enum import Enum

class TurnType(Enum):
    PLANNING = "planning"            # 规划/推理轮，输出短
    TOOL_FOLLOWUP = "tool_followup"  # 工具调用后的处理轮
    FINAL_ANSWER = "final_answer"    # 最终长回复
    FILE_WRITE = "file_write"        # 预期产生大文件内容的轮

@dataclass
class BudgetPolicy:
    base_budget: dict[TurnType, int] = None
    escalation_budget: int = 48000       # 截断后一次性升级的预算
    model_hard_limit: int = 64000        # 模型输出硬上限
    context_window: int = 200000

    def __post_init__(self):
        self.base_budget = self.base_budget or {
            TurnType.PLANNING: 8000,
            TurnType.TOOL_FOLLOWUP: 16000,
            TurnType.FINAL_ANSWER: 16000,
            TurnType.FILE_WRITE: 32000,
        }

class OutputBudgetManager:
    def __init__(self, policy: BudgetPolicy):
        self.policy = policy
        self._escalated = False   # 本次任务是否已升级过预算（只升级一次）

    def compute_budget(self, turn_type: TurnType,
                       prompt_tokens: int,
                       escalated: bool = False) -> int:
        """计算本轮 max_tokens，需同时受模型硬上限和上下文余量钳制。"""
        if escalated and not self._escalated:
            budget = self.policy.escalation_budget
        else:
            budget = self.policy.base_budget[turn_type]

        room = self.policy.context_window - prompt_tokens
        safety_margin = int(room * 0.05)          # 预留 5% 余量
        budget = min(budget, self.policy.model_hard_limit,
                     room - safety_margin)

        if budget < 1024:
            raise ContextExhaustedError(
                "上下文余量不足，请先压缩或新开会话")   # 预检拒绝，宁缺毋滥
        return budget

    def mark_escalated(self):
        self._escalated = True
```

**预检拒绝**（发请求前检查）是关键防线：宁可请求发出前就报"预算不足"，也不要生成半截浪费 token。

### 3.2 L2：TruncationDetector —— 截断检测

多供应商 `finish_reason` 写法不同，必须归一化；同时做结构性校验兜底。

```python
TRUNCATED_REASONS = {"length", "max_tokens", "MAX_TOKENS"}
NORMAL_REASONS    = {"stop", "end_turn", "STOP", "tool_calls", "tool_use"}

@dataclass
class DetectionResult:
    truncated: bool
    reason: str                    # "finish_reason" | "structure" | "none"
    tool_call_midway: bool = False # 截断是否发生在工具调用参数中途

class TruncationDetector:
    def detect(self, response) -> DetectionResult:
        fr = response.finish_reason

        # 1. 显式信号
        if fr in TRUNCATED_REASONS:
            return DetectionResult(
                truncated=True,
                reason="finish_reason",
                tool_call_midway=self._is_tool_call_incomplete(response))

        # 2. 结构性兜底：finish_reason 显示正常，但结构不完整
        #    （某些供应商/代理层会丢失 stop_reason，必须兜住）
        if self._is_tool_call_incomplete(response):
            return DetectionResult(truncated=True,
                                   reason="structure",
                                   tool_call_midway=True)
        return DetectionResult(truncated=False, reason="none")

    def _is_tool_call_incomplete(self, response) -> bool:
        """工具调用 JSON 括号不配平 / 流式消息有 tool_call 头但参数未闭合"""
        for tc in response.tool_calls or []:
            if not self._json_balanced(tc.arguments):
                return True
        return False
```

**注意**：检测链路上任何一环（SDK 封装、代理网关、流式聚合器）丢弃 `stop_reason` 字段，下游恢复逻辑将全部失效。上线前需对全链路做字段透传审计。

### 3.3 L3：RecoveryController —— 有界恢复状态机

```
            ┌──────────────┐
            │  检测到截断   │
            └──────┬───────┘
                   ▼
        ┌─────────────────────┐   成功   ┌────────┐
   ┌───▶│ 步骤1：升级预算重试   │────────▶│  完成   │
   │    │ （仅一次）           │         └────────┘
   │    └─────────┬───────────┘
   │              │ 仍截断
   │              ▼
   │    ┌─────────────────────┐   成功   ┌────────┐
   │    │ 步骤2：续写循环       │────────▶│  完成   │
   │    │ （最多3次，有产出才继续）│       └────────┘
   │    └─────────┬───────────┘
   │              │ 无新增产出 / 超限
   │              ▼
   │    ┌─────────────────────┐
   └───┤ 步骤3：明确报错        │
       │ 返回部分结果 + 可操作建议 │
       └─────────────────────┘
```

```python
class RecoveryController:
    MAX_CONTINUATIONS = 3

    def recover(self, ctx, request, partial) -> str:
        # 步骤1：一次性升级预算重试（仅当截断不在工具调用中途时）
        if not ctx.tool_call_midway and not ctx.escalated:
            ctx.escalated = True
            budget = ctx.budget_mgr.compute_budget(
                ctx.turn_type, prompt_tokens=ctx.prompt_tokens,
                escalated=True)
            retry = ctx.llm.call(request, max_tokens=budget)
            if not ctx.detector.detect(retry).truncated:
                return retry.text
            partial = retry.text or partial

        # 步骤2：续写循环（带产出监控，防无限烧 token）
        output = partial
        for _ in range(self.MAX_CONTINUATIONS):
            cont = ctx.llm.call(
                self._build_continuation_request(ctx, output),
                max_tokens=ctx.budget_mgr.compute_budget(
                    ctx.turn_type, ctx.prompt_tokens))
            new_text = cont.text
            if len(new_text.strip()) < 16:
                # 只产出了推理没有可见文本：停止续写
                break
            output += new_text
            if not ctx.detector.detect(cont).truncated:
                return output

        # 步骤3：明确报错，交付已有部分
        raise OutputTruncatedError(partial=output)
```

**续写请求构造的要点**（避免 F4 非法消息序列）：

```python
def _build_continuation_request(self, ctx, output_so_far: str):
    """
    关键约束：
    - 只把已生成内容的【尾部】（如最后 1000 token）带回上下文，控制输入长度；
    - 若截断发生在工具调用中途，禁止续写（走步骤3报错或触发重新分片），
      否则续写文本会插在 functionCall 和 tool response 之间构成非法序列；
    - 若模型 API 支持 assistant prefill，直接把已生成内容作为 assistant
      消息前缀续写，效果最自然。
    """
    tail = output_so_far[-4000:]   # 约 1000 token 的尾部上下文
    return ctx.messages + [
        {"role": "assistant", "content": tail},
        {"role": "user", "content":
         "从中断处继续输出，不要重复已写内容，不要使用任何前导语。"}
    ]
```

### 3.4 L4：ToolCallGuard —— 工具调用防护

这是**工程上最讲究**的一层，直接决定截断是否造成实际破坏。

**规则一：半截写操作，永不落盘**

```python
WRITE_LIKE_TOOLS = {"write_file", "edit_file", "apply_patch", "fs_write"}

class ToolCallGuard:
    def execute(self, tool_call, detection: DetectionResult):
        if tool_call.name in WRITE_LIKE_TOOLS:
            if detection.tool_call_midway or \
               not self._content_complete(tool_call):
                # 拒绝执行 + 引导模型分片重写，半成品绝不上盘
                return ToolResult.error(
                    code="TRUNCATED_WRITE_REJECTED",
                    message=("文件内容因输出长度限制被截断，已拒绝写入。"
                             "请分多次调用：先写入前半部分，"
                             "再用 append 模式追加后续内容。"))
        return self._do_execute(tool_call)
```

**规则二：谨慎对待截断 JSON 的自动修复**

自动补齐被截断的参数 JSON 看似友好，但若修复结果碰巧通过 schema 校验，工具会以**不完整甚至错误的参数静默执行**（如 `edit_file` 的 `old_string` 被截断后匹配到错误位置）。

```python
def safe_parse_args(self, raw_json: str, schema: dict):
    try:
        return json.loads(raw_json), "ok"
    except json.JSONDecodeError:
        repaired = self._attempt_repair(raw_json)   # 括号补齐等保守修复
        if repaired and self._passes_schema(repaired, schema) \
           and self._no_string_field_trimmed(raw_json, repaired):
            # 额外条件：修复不得截断任何字符串字段的值
            return repaired, "repaired"
        return None, "unrecoverable"   # 宁错杀不放过
```

**规则三：从设计上消灭单次超长输出的需求**

引导模型**分片写文件**，并提供机制保证：

- 系统提示中明确规定：单文件超过约 2000 行时，必须首次调用写入前半、后续调用用 `append` 模式追加；
- 大工具结果自动落盘：工具返回超过阈值（如 20000 token）时，全文写入临时文件，上下文中只保留 `文件路径 + 前 10 行预览`。

### 3.5 L5：ContextPressureManager —— 上下文侧减负

截断的根因之一是输入挤占输出。采用**分级压缩管线**，按代价从低到高依次启用：

| 级别 | 触发条件 | 动作 |
|---|---|---|
| G1 | 单个工具结果 > 20000 token | 全文落盘，上下文留路径 + 头部预览 |
| G2 | 上下文用量 > 70% | 老的 write/edit 工具参数替换为文件指针 |
| G3 | 上下文用量 > 80% | LLM 滚动摘要：压缩最老的一半消息，**触发点要留足余量**（经验：触发点从 ~90% 提前到 ~75–80%，压缩质量和后续轮次质量都更高，有效会话反而更长） |
| G4 | 结构性隔离 | 探索类子任务派发给子代理，独立上下文执行，只回传结论摘要 |

```python
class ContextPressureManager:
    def before_turn(self, messages, usage_ratio: float):
        if usage_ratio < 0.70:
            return messages
        messages = self.offload_large_tool_results(messages)      # G1/G2
        if usage_ratio > 0.80:
            messages = self.summarize_oldest_half(messages)       # G3
            # 摘要前将原始消息完整落盘，支持回溯
        return messages
```

---

## 4. 关键流程：主循环整合

```python
def agent_loop(task):
    ctx = init_context(task)
    while not task.done:
        turn_type = classify_turn(ctx)                       # L1
        budget = ctx.budget_mgr.compute_budget(
            turn_type, ctx.prompt_tokens)

        ctx.messages = ctx.pressure_mgr.before_turn(         # L5
            ctx.messages, ctx.usage_ratio)

        response = ctx.llm.call(ctx.messages, max_tokens=budget)
        detection = ctx.detector.detect(response)            # L2

        if detection.truncated:
            if detection.tool_call_midway:
                # 工具调用中途截断：不执行、不续写，
                # 回注错误引导模型分片重来                    # L4
                ctx.messages.append(tool_guard_rejection(detection))
                ctx.metrics.incr("truncation.tool_call_rejected")
                continue
            response_text = ctx.recovery.recover(            # L3
                ctx, request, partial=response.text)
        else:
            response_text = response.text

        if response.tool_calls:
            for tc in response.tool_calls:
                result = ctx.tool_guard.execute(tc, detection)  # L4
                ctx.messages.append(result)

    return task.result
```

---

## 5. 配置项与默认值

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `budget.planning` | 8000 | 规划轮输出预算 |
| `budget.tool_followup` | 16000 | 工具后续轮预算 |
| `budget.final_answer` | 16000 | 最终回复预算 |
| `budget.escalation` | 48000 | 截断后一次性升级预算 |
| `budget.escalation_max_count` | 1 | 每次任务允许升级次数 |
| `recovery.max_continuations` | 3 | 续写最大次数 |
| `recovery.min_progress_chars` | 16 | 续写最小新增产出（低于则终止） |
| `guard.reject_truncated_writes` | true | 拒绝半截写操作落盘 |
| `guard.allow_json_repair` | false | 默认关闭截断 JSON 自动修复 |
| `offload.tool_result_threshold` | 20000 token | 工具结果落盘阈值 |
| `compaction.trigger_ratio` | 0.80 | 摘要触发点 |
| `continuation.tail_chars` | 4000 | 续写时带回的尾部上下文长度 |

---

## 6. 可观测性

**必须埋点的指标**（Metrics）：

- `truncation.detected{reason=finish_reason|structure}` — 截断发生次数
- `truncation.tool_call_midway` — 工具调用中途截断（最高危，应配告警）
- `recovery.escalated / recovery.continued / recovery.failed` — 恢复路径分布
- `tool_write.rejected` — 被拒绝落盘的半截写操作
- `budget.exhausted_preflight` — 预检拒绝次数（反映上下文管理是否健康）
- 每次事件的 `task_id`、`turn_type`、`prompt_tokens`、`output_tokens` 结构化日志

**告警建议**：`truncation.tool_call_midway` 单小时 > 10 次，或 `recovery.failed` 率 > 5% 时告警。

---

## 7. 测试方案

**故障注入测试**（用 mock LLM 精确构造截断场景）：

1. **F1 普通截断**：mock 返回 `finish_reason="length"` + 半截文本 → 断言走升级重试 → 续写 → 拼接完整；
2. **F2 工具调用中途截断**：mock 返回括号不配平的 tool_call JSON → 断言不执行工具、不续写、回注分片引导；
3. **F3 半截写文件**：mock 截断的 `write_file` 调用 → 断言磁盘上**不存在**该文件或文件未被修改；
4. **F4 非法序列防护**：构造"functionCall 后接续写文本"的消息序列 → 断言续写逻辑被拒绝；
5. **预算预检**：构造 `room < 1024` 的上下文 → 断言请求未发出、抛出 `ContextExhaustedError`；
6. **死循环防护**：mock 连续 5 次截断 → 断言恰好重试 1 次升级 + 3 次续写后报错，总调用数有上界；
7. **供应商兼容**：分别用 `length` / `max_tokens` / `MAX_TOKENS` 三种写法注入，断言均被归一化检出；
8. **字段透传审计**：集成测试验证从 API 原始响应到 Detector 的链路上 `finish_reason` 无丢失。

---

## 8. 分阶段落地路线图

| 阶段 | 内容 | 预期收益 | 工作量 |
|---|---|---|---|
| **P0（1 周）** | L2 截断检测 + L3 续写兜底 + L4 半截写拒绝 + 基础指标 | 消除 F3 数据破坏、F1 静默截断 | 小 |
| **P1（2 周）** | L1 动态预算分级 + 预检拒绝 + 工具调用中途截断处理（F2/F4）+ 故障注入测试 | 消除重试死循环，截断恢复率 > 95% | 中 |
| **P2（2–4 周）** | L5 上下文分级压缩（落盘 offload → 滚动摘要）+ 工具结果预截断 + 子代理隔离 | 从源头降低截断发生率 | 中 |

P0 即可上线：即使只有"检测 + 续写 + 拒绝半截写入"三件套，也能把截断从"数据损坏事故"降级为"可自动恢复的小颠簸"。

---

## 9. 风险与注意事项

1. **续写拼接质量**：跨截断点拼接可能出现重复或断裂。缓解：续写 prompt 明确"不要重复"，落盘前对拼接处做一次去重检查；
2. **续写成本**：每次续写需重发部分上下文。缓解：只带尾部 ~1000 token；任务级设置续写总成本上限；
3. **自动修复 JSON 的正确性风险**：默认关闭，仅在字符串字段完整性可验证时启用；
4. **"上下文焦虑"**：模型感知到接近限额时可能提前放弃任务、自我摘要。缓解：压缩由 harness 程序化触发，不依赖模型自觉；
5. **不同供应商语义差异**：`finish_reason` 取值、流式事件结构、prefill 支持程度均不同，供应商适配层需逐一验证（对应测试用例 7、8）。

---

## 附：核心不变量（Invariants）

评审和测试中始终成立的三条铁律：

1. **任何被判定为截断的工具调用，不得产生副作用**（不落盘、不发请求、不改状态）；
2. **任何恢复路径的 API 调用次数有硬上界**（1 次升级 + 3 次续写）；
3. **任何交付给用户的结果，要么是完整的，要么明确标注为部分结果并附可操作建议**。
