# ADR 0010: Tool-Use Refactor — create_agent + middleware reflection + deterministic citation check

**Status**: Accepted
**Date**: 2026-06-18

## Context

ADR-0009 决定「工具使用重构优先于多 Agent 辩论」。本 ADR 是 ADR-0009 的落地设计，回答三个具体问题：

1. **用什么 API 造真 Agent？** 当前 `fa.py:24` / `ia.py` 的 `fa_analyze` 是「`_build_context` 把 state 拍平成字符串 → `call_llm(prompt)` 单轮 → 模板拼接」，`llm.py:23` 的 `call_llm` 没有 `tools` 参数。LLM 无法主动查数据、无法动态决策，是 ADR-0009 诊断的「伪 Agent」根因。

2. **reflection 怎么注入？** 「真 Agent」除了能调工具，还该能自我审视输出质量。直接改 `fa_analyze` 函数体会和现有模板组装逻辑深度耦合；需要一个标准化的注入点。

3. **数据准确性怎么校验？** [[llm-hallucination-incident]]（2026-06-01 负债率编造、PE 无源）是项目当前未解决的真实痛点。`finance_agent_tech_enhancement.md` 方向 5 把「数据准确性」交给 LLM-as-a-Judge —— 这是脆弱链，评审 LLM 自己也会幻觉。需要一个确定性的、可回归的校验机制。

三个问题有共同前提：本项目 LangGraph 已升到 1.2.0、langchain-core 1.4.0、Python ≥ 3.12，迁移到 LangChain v1 的 `create_agent` 无版本阻塞。

## Decision

分三步落地，三步互为独立但服务于同一目标（把 FA/IA 从「带格式化的 LLM 调用」升级为「能查数据、会反思、可校验的真 Agent」）。

### Step 1: FA/IA 节点迁移到 `create_agent` + 工具集

用 `langchain.agents.create_agent`（LangGraph v1 废弃了 `create_react_agent`，见 `docs/langgraph v1 migration guide`）重写 `fa_analyze` / `ia_analyze`。每个 Agent 绑定一组工具，LLM 在 ReAct 循环里自主决定何时调哪个工具。

**FA Analyst 工具集**（复用现有 `metrics/` 纯函数，不重写计算逻辑）：

| Tool | 复用模块 | 作用 |
|------|---------|------|
| `query_metric(metric_name, period)` | `metrics/*` | 查单个指标的历史值 + 红黄绿灯 |
| `compare_with_peers(metric_name)` | `metrics/relative.py` + `fetch` 同业数据 | 同业对比 |
| `decompose_roe()` | `metrics/dupont.py` | 3 层杜邦拆解 |
| `flag_anomaly()` | `metrics/traffic_light.py` | 列出所有红灯/异动指标 |
| `get_statement_line(item, period)` | `data/akshare_client.py` | 查原始报表科目（用于追溯） |

**IA Analyst 工具集**：复用 FA 的 `query_metric`/`compare_with_peers`，额外加 `get_valuation()`（PE/PB/GARP）和 `get_industry_info()`。

**与现有 PREP 子图的关系**：工具不重新拉数据，从已 `compute_metrics` 后的 state 读。即 PREP 子图（check_cache→fetch→validate→compute）保持不变，仍是数据准备的唯一入口；Agent 只在 PREP 完成后的 state 上做推理。这保证 Gradio / MCP Server / 新 Agent 三条入口走完全一样的数据路径（与 ADR-0008 的设计原则一致）。

**模型**：仍用 `litellm` 调 DeepSeek（`llm.py` 的 `call_llm` 保留，作为非 Agent 路径的回退）。`create_agent` 的 `model` 参数传一个 thin wrapper，内部调 `litellm.completion` 并支持 `tools` 透传。

### Step 2: reflection 用 `@after_model` middleware 注入

不重写 `fa_analyze` 函数体，改用 LangChain v1 middleware 的 `after_model` 钩子做 reflection。LLM 每次回复后，middleware 自动调一次 LLM「审视刚才输出质量」，不达标则把反馈塞回 messages 触发下一轮。

**关键设计**：middleware 装饰器自带 `state_schema`，绕开 `create_agent(middleware=, state_schema=)` 的互斥限制（GitHub #33217）：

```python
from typing_extensions import NotRequired
from langchain.agents.middleware import after_model, AgentState

class FAState(AgentState):
    reflection: NotRequired[str]
    reflection_pass: NotRequired[bool]

@after_model(state_schema=FAState)
def fa_reflection(state, runtime) -> dict | None:
    last = state["messages"][-1].content
    result = call_llm(REFLECTION_PROMPT.format(body=last), ...)
    passed = "[REFLECTION_PASSED]" in result
    return {"reflection": result, "reflection_pass": passed}
```

这样 FA Agent 既能有 reflection middleware，又能携带 `reflection`/`reflection_pass` 等财务专用字段，二选一的限制被绕开。

**reflection 不替代最终校验**：reflection 是 LLM 自我审视（主观，可能漏），确定性校验（Step 3）是程序比对（客观，不漏）。两者互补。

### Step 3: 确定性引用校验器（Deterministic Citation Check）

报告里每一个数字必须能反查到 state 字段并（对计算型指标）重算。这是 [[finhallu-grounding-research]] 里 FinGround 论文「computational claim 用公式重算比 LLM 评审高 +18.9 F1」的直接落地。

**区分两类数字**：

- **原始科目**（营业收入、总资产）：直接来自报表，无需重算，只校验 LLM 写的值是否与 state 字段一致
- **派生指标**（资产负债率、ROE、毛利率、杜邦分解）：原始科目算出来的，校验器用 `metrics/` 纯函数从原始科目重新推导，拿推导结果当 ground truth，比对 LLM 报告里的派生数字

**关键澄清**：重算不是「同一个公式用同样输入再算一遍」（那无意义），是「用原始科目重新推导派生指标，验证 LLM 报告的派生数字是否一致」。LLM 看到 prompt 里已经有 `metrics/` 算好的派生值，但仍可能抄错（58% 写成 62%）、张冠李戴（流动比率当资产负债率）、或编一个 prompt 里没有的数。程序无法判断 LLM 是「抄对」还是「编错」—— 除非自己从原始科目重算一遍，拿「程序算的真相」对「LLM 说的数」。

**杜邦三层逐层定位示例**（杜邦这种多层分解，LLM 极容易某一层错，正是重算最高价值的场景）：

```
程序从原始科目三层重算（ground truth，metrics/dupont.py）：
ROE 20% = 净利率 8% × 总资产周转率 1.5 × 权益乘数 1.67

LLM 报告写：
ROE 20% ✓
├ 净利率 8% ✓
├ 总资产周转率 1.2 ✗  ← 应为 1.5，定位到具体哪一层错
└ 权益乘数 1.67 ✓

→ citation_report: FAIL, layer=turnover, expected=1.5, stated=1.2, delta=-0.3
```

确定性校验能逐层定位错误，而 LLM-as-Judge 只能「整段报告 8/10 分」—— 精度差一个量级。

**前置条件：结构化输出**。FA/IA 的 LLM 输出从自由 Markdown 改为带 `response_format` 的结构化对象，每条结论携带：

```python
class Claim(BaseModel):
    claim_type: Literal["numerical","temporal","entity","comparative","regulatory","computational"]
    field_ref: str          # 反查的 state 字段路径，如 "solvency_metrics.debt_ratio" 或 "dupont_tree.turnover"
    stated_value: float | str
    interpretation: str
```

没有 `field_ref`，校验器无法知道「报告里的 62% 对应哪个指标」，重算无从谈起。所以「结构化输出 → 确定性校验」是硬顺序，不能反。

**校验器逻辑**（纯 Python，不调 LLM，可进 CI）：

| claim_type | 校验方式 | 复用模块 |
|-----------|---------|---------|
| numerical / entity | `abs(state[field_ref] - stated_value) < tol` | 直接读 state |
| computational | 识别公式 → 取操作数 → 重算 → 比对 | `metrics/dupont.py` / `profitability.py` 等纯函数 |
| comparative | 两侧 numerical 校验 + 比较方向校验 | 复用 numerical |
| temporal | 数值校验 + 时间窗口存在性校验 | 直接读 state |
| regulatory | 引用存在性（不在本项目数据范围，标 `unverifiable` 跳过）| — |

**护城河**：能做这个重算的前提是项目已有可信的指标纯函数库。本项目 `metrics/` 已有 20+ 指标 + 杜邦 + 勾稽校验（`validate.py`），这些就是 FinGround 说的 deterministic recomputation infrastructure，现成可复用。纯 LLM-only 的项目想做这个，得先从零建指标计算层。

**输出**：报告生成后跑一次校验器，产出 `citation_report`（每条 claim 的 PASS/FAIL/UNVERIFIABLE + 差异）。失败 claim 进 Langfuse score（见 [[langfuse-litellm-observability]]），让幻觉率成为可监控指标。

**与 LLM-as-Judge 的分工**：确定性校验管「数据对不对」（客观，不漏），LLM-as-Judge（未来 Eval Pipeline）只管「分析深不深、写得通不通顺」（主观）。两者不混用 —— 让 LLM 判 LLM 数字对错是脆弱链，评审 LLM 自己也会幻觉。

## Consequences

- **`llm.py` 的 `call_llm` 保留**：作为非 Agent 路径（如 MCP Server 的纯数据返回、summary 二次生成）的回退，不强行全部走 `create_agent`
- **`fa.py` / `ia.py` 重写**：`_build_context` 的大段格式化逻辑大部分退役（数据改为工具按需拉取，不再一次性塞 prompt），但 `format_*` 系列 formatter 保留供工具返回值使用
- **报告输出形态变化**：从「自由 Markdown」改为「结构化对象 → 渲染成 Markdown」。模板组装逻辑（`templates/`）需适配，但报告对外观感不变
- **新增依赖**：`langchain` 主包（当前只有 `langchain-core`）—— `create_agent` 在 `langchain.agents`。需确认 `langchain>=1.0` 与现有 `langchain-core==1.4.0` 兼容
- **CI 新增校验任务**：`citation_report` 失败率作为 CI gate，超过阈值的报告不通过
- **评估基础**：Step 3 落地后，「Agent 是否发起了预期数量的工具调用」「citation 通过率」成为可度量指标，让 ADR-0009 说的「Agent 行为可度量」真正成立
- **辩论机制的前置条件**：Step 1+2 让 Worker 具备工具调用 + grounding 能力后，ADR-0009 延后的 Multi-Agent 辩论（按 [[findebate-architecture-correction]] 的 5 专业 agent + Trust/Skeptic/Leader 单轮设计）才具备落地前提
- **不在本 ADR 范围**：RAG 向量库、Multi-Agent 辩论、Human-in-the-loop 审批 —— 这些是后续 ADR

## References

- [LangGraph v1 migration guide](https://docs.langchain.com/oss/python/migrate/langgraph-v1) — `create_react_agent` → `create_agent`
- [LangChain custom middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom) — `@after_model` + 装饰器级 `state_schema`
- [GitHub langchain-ai/langchain#33217](https://github.com/langchain-ai/langchain/issues/33217) — middleware 与 state_schema 互斥限制
- [FinGround (arXiv:2604.23588)](https://arxiv.org/abs/2604.23588) — atomic claim 分解 + computational claim 公式重算的学术背书
- [ADR-0009](0009-defer-multi-agent-debate.md) — 工具使用优先于辩论的决策（本 ADR 是其落地）
- [ADR-0002](0002-pure-llm-agents.md) — Agent 作为纯 LLM 消费者的初始决策（本 ADR 修正其「纯 LLM」被解读为「无工具」的偏差）
- [ADR-0008](0008-mcp-server.md) — PREP 子图作为唯一数据入口的设计（本 ADR 的工具复用其产物）
