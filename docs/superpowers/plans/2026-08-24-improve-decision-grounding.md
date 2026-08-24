# Improve Decision Grounding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让交易决策（Trader/Risk Judge）输出结构化论据引用 `evidence_refs`，并让 decision_grounding judge 能逐条核对「决策论据 vs 来源」，把 baseline 1.57/5 拉起来。

**Architecture:** `TradeDecision` 增加 `evidence_refs: list[TradeEvidenceRef]`（宽松 source + 归一 validator，绝不炸管线）；trader.md + risk_judge.md 强制输出引用（risk_judge 是 judge 看到的 `final_trade_decision`，必须回显）；`_serialize_decision` 经 `model_dump()` 自动透传；`_summarize_analyst_reports` 附 claims 数值使 judge 能核对；judges.py rubric 加 evidence_refs 显式规则 + 无引用降级路径。

**Tech Stack:** Python 3.11 / Pydantic v2（`field_validator` mode="before"）/ LangGraph / pytest / ruff / mypy

## Global Constraints

- 红线（AGENTS.md）：没有先写失败测试的代码 → 删除重写。每步先红后绿。
- `TradeDecision` 解析失败不降级（harden-llm-output-validation）——但 `evidence_refs.source` **必须宽松**：LLM 输出抖动只归一不拒绝（delta Task 1.1 明确「宽松 str + validator 归一」），引用清洗失败不应中断管线。
- `source` 规范枚举（spec 契约）：`technical/macro/fundamental/sentiment/debate_bull/debate_bear/research_manager`。已知别名归一到规范值。
- 既有字段（action/confidence/reasoning/position_size/entry_price/stop_loss/target_price）行为不变；`evidence_refs` 带默认空列表，旧输出/旧 stub 解析不受影响（`Field(default_factory=list)`）。
- judge 变量 `trade_decision` = `final_trade_decision` = **Risk Judge 输出**（`evals/extract.py:78,89`），不是 trader 的 `trader_plan`。因此 `prompts/risk_judge.md` 也必须要求输出 evidence_refs。
- 本 delta 为纯后端变更（无前端 UI / SSE / 会话切换 / 状态流转）→ 不适用 E2E 门禁（project-workflow §2）。
- `truncate_for_trace` 保首尾各 1/4（`langfuse_tracing.py:142-154`）；`evidence_refs` 作为 TradeDecision JSON 最后一个字段，会落在 4096 截断的尾部，不丢失。

---

### Task 1: TradeDecision 模型 + 两个 prompt + stub

**Files:**
- Modify: `src/finance_agent/models.py:55-68`（TradeDecision 加字段）+ 文件末尾附近（新增 TradeEvidenceRef）
- Modify: `src/finance_agent/prompts/trader.md`
- Modify: `src/finance_agent/prompts/risk_judge.md`
- Modify: `src/finance_agent/nodes/_llm_utils.py:54-59`（`_STUB_TRADE_DECISION`）
- Test: `tests/test_models.py`（新增类）
- Create: `tests/test_trade_decision_prompts.py`
- Test: `tests/test_pipeline_stub.py:96`（扩展既有断言）

**Interfaces:**
- Consumes: 无（本任务独立）
- Produces: `models.TradeEvidenceRef`（字段 `claim: str`、`source: str`，before-validator 归一）；`models.TradeDecision.evidence_refs: list[TradeEvidenceRef] = Field(default_factory=list)`；`models.TRADE_EVIDENCE_SOURCES: frozenset[str]`；`models._SOURCE_ALIASES: dict[str, str]`。Task 2 依赖 `model_dump()` 输出含 `evidence_refs`。

- [ ] **Step 1: Write the failing test（模型层）**

在 `tests/test_models.py` 追加（文件已 `from finance_agent.models import ...` 引入 TradeDecision；无 TradeEvidenceRef 导入时加）：

```python
class TestTradeDecisionEvidenceRefs:
    """TradeDecision.evidence_refs 结构化论据引用（improve-decision-grounding）。"""

    def test_evidence_refs_parsed(self):
        decision = TradeDecision.model_validate({
            "action": "buy",
            "confidence": 0.75,
            "reasoning": "理由",
            "evidence_refs": [
                {"claim": "ROE 3.4% 高于行业均值", "source": "fundamental"},
                {"claim": "股价站上 60 日均线", "source": "technical"},
            ],
        })
        assert len(decision.evidence_refs) == 2
        assert decision.evidence_refs[0].source == "fundamental"
        assert decision.evidence_refs[0].claim == "ROE 3.4% 高于行业均值"

    def test_evidence_refs_default_empty(self):
        decision = TradeDecision.model_validate(
            {"action": "hold", "confidence": 0.5, "reasoning": "理由"}
        )
        assert decision.evidence_refs == []

    def test_source_aliases_normalized(self):
        decision = TradeDecision.model_validate({
            "action": "buy",
            "confidence": 0.6,
            "reasoning": "理由",
            "evidence_refs": [
                {"claim": "a", "source": "Technical_Analyst"},
                {"claim": "b", "source": "BULL"},
                {"claim": "c", "source": "research_manager_conclusion"},
                {"claim": "d", "source": " sentiment "},
            ],
        })
        sources = [r.source for r in decision.evidence_refs]
        assert sources == ["technical", "debate_bull", "research_manager", "sentiment"]

    def test_unknown_source_lenient(self):
        decision = TradeDecision.model_validate({
            "action": "buy",
            "confidence": 0.6,
            "reasoning": "理由",
            "evidence_refs": [{"claim": "a", "source": "risk_debater"}],
        })
        assert decision.evidence_refs[0].source == "risk_debater"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -k EvidenceRefs -v`
Expected: FAIL — `AttributeError: 'TradeDecision' object has no attribute 'evidence_refs'`；TradeEvidenceRef 未定义。

- [ ] **Step 3: Write minimal implementation**

`src/finance_agent/models.py`：在 `TradeDecision` 之前插入：

```python
# TradeDecision.evidence_refs 的 source 规范枚举（improve-decision-grounding）
TRADE_EVIDENCE_SOURCES = frozenset({
    "technical",
    "macro",
    "fundamental",
    "sentiment",
    "debate_bull",
    "debate_bear",
    "research_manager",
})

# LLM 输出常见别名 → 规范 source（归一不拒绝，见 TradeEvidenceRef validator）
_SOURCE_ALIASES = {
    "technical_analyst": "technical",
    "macro_analyst": "macro",
    "fundamental_analyst": "fundamental",
    "sentiment_analyst": "sentiment",
    "bull": "debate_bull",
    "bear": "debate_bear",
    "research_manager_conclusion": "research_manager",
}


class TradeEvidenceRef(BaseModel):
    """交易决策的论据引用 — 决策论据到来源的可核对映射。

    source 宽松接收：仅做大小写/别名归一，未知值原样保留（LLM 抖动
    不炸管线——judge 自会因无法核对而判低分；与 action/confidence 的
    硬校验相反，此处是「降级不中断」路线）。
    """

    claim: str
    source: str

    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        norm = value.strip().lower()
        return _SOURCE_ALIASES.get(norm, norm)
```

`TradeDecision` 末尾（`target_price` 之后）追加字段：

```python
    evidence_refs: list[TradeEvidenceRef] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -k EvidenceRefs -v`
Expected: PASS（4 passed）。随后跑全模型层：`uv run pytest tests/test_models.py -v` 确认既有 3 个测试类不受影响。

- [ ] **Step 5: 两个 prompt 更新（先写断言测试）**

Create `tests/test_trade_decision_prompts.py`：

```python
"""TradeDecision 相关 prompt 的内容契约（improve-decision-grounding）。

prompt 是行为契约的一部分：trader/risk_judge 必须要求模型输出
evidence_refs，否则 judge 无结构化引用可核对。
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "src/finance_agent/prompts"


def _load(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


class TestTraderPromptEvidenceRefs:
    def test_example_contains_evidence_refs(self):
        assert '"evidence_refs"' in _load("trader.md")

    def test_mandates_ref_for_each_reasoning_claim(self):
        text = _load("trader.md")
        assert "evidence_ref" in text
        assert "source" in text

    def test_source_enum_listed(self):
        text = _load("trader.md")
        assert "technical" in text
        assert "debate_bull" in text
        assert "research_manager" in text


class TestRiskJudgePromptEvidenceRefs:
    def test_example_contains_evidence_refs(self):
        assert '"evidence_refs"' in _load("risk_judge.md")

    def test_mandates_passthrough_without_fabrication(self):
        text = _load("risk_judge.md")
        assert "evidence_ref" in text
        # 不虚构来源 + 允许空数组（无可对应来源时）
        assert "不得" in text
        assert "[]" in text
```

Run: `uv run pytest tests/test_trade_decision_prompts.py -v`
Expected: FAIL（trader.md/risk_judge.md 尚无 evidence_refs）。

- [ ] **Step 6: 更新 prompt 实现**

`src/finance_agent/prompts/trader.md` 全文替换为：

```markdown
你是 Trader（交易员）。基于分析师报告和辩论结论，做出交易决策。

## 输出格式

返回 JSON 格式的 TradeDecision：

```json
{
  "action": "buy",
  "confidence": 0.75,
  "reasoning": "决策理由",
  "position_size": "moderate",
  "entry_price": 1500.0,
  "stop_loss": 1400.0,
  "target_price": 1800.0,
  "evidence_refs": [
    {"claim": "ROE 3.4% 高于行业均值", "source": "fundamental"},
    {"claim": "股价站上 60 日均线", "source": "technical"}
  ]
}
```

action 仅允许: buy / sell / hold / watch
confidence 必须是 0 到 1 之间的小数（如 0.75 表示 75% 置信度），不要用百分数

evidence_refs（论据引用）是强制字段：reasoning 中的每条例据必须对应一条
evidence_ref（claim 为论据原文，source 为来源）；source 仅允许以下枚举值之一：
technical / macro / fundamental / sentiment / debate_bull / debate_bear /
research_manager；每条论据中的数值必须与对应来源报告一致，禁止引用来源中
不存在的数值。
```

`src/finance_agent/prompts/risk_judge.md` 全文替换为：

```markdown
你是 Risk Judge（风险裁判）。综合风险辩论，给出最终交易决策。

## 输出格式

返回 JSON 格式的 TradeDecision：

```json
{
  "action": "buy",
  "confidence": 0.6,
  "reasoning": "最终决策理由",
  "position_size": "light",
  "evidence_refs": [
    {"claim": "ROE 3.4% 高于行业均值", "source": "fundamental"}
  ]
}
```

action 仅允许: buy / sell / hold / watch
confidence 必须是 0 到 1 之间的小数（如 0.6 表示 60% 置信度），不要用百分数

evidence_refs（论据引用）：采纳自「交易方案」的论据，原样保留其 claim 与
source（source 仅允许 technical / macro / fundamental / sentiment /
debate_bull / debate_bear / research_manager）；不得编造来源；如论据无法
对应上述来源，可省略该项（evidence_refs 允许为 []）。
```

Run: `uv run pytest tests/test_trade_decision_prompts.py -v`
Expected: PASS（5 passed）。

- [ ] **Step 7: `_STUB_TRADE_DECISION` 补字段**

`src/finance_agent/nodes/_llm_utils.py:54-59`：

```python
# 交易决策 stub answer（Trader / Risk Judge 共用 TradeDecision schema）
_STUB_TRADE_DECISION: dict = {
    "action": "hold",
    "confidence": 0.6,
    "reasoning": "STUB 交易决策：多因素均衡，建议持有观察（测试数据）",
    "evidence_refs": [],
}
```

`tests/test_pipeline_stub.py:96` 的 `test_trader_answer_parses_to_trade_decision` 追加断言：

```python
    assert decision.evidence_refs == []
```

Run: `uv run pytest tests/test_pipeline_stub.py -v`
Expected: PASS。

- [ ] **Step 8: Commit**

```bash
git add src/finance_agent/models.py src/finance_agent/prompts/trader.md src/finance_agent/prompts/risk_judge.md src/finance_agent/nodes/_llm_utils.py tests/test_models.py tests/test_trade_decision_prompts.py tests/test_pipeline_stub.py
git commit -m "feat(models): TradeDecision 增加 evidence_refs 结构化论据引用（trader/risk_judge prompt 强制输出）"
```

---

### Task 2: judge 输入增强（extract + rubric）

**Files:**
- Modify: `evals/extract.py:50-60`（`_summarize_analyst_reports` 附 claims 数值）；同文件新增 `_format_claims`
- Modify: `evals/judges.py`（`RUBRICS["decision_grounding"]` 文本）
- Test: `tests/evals/test_extract.py`（新增两个测试类）
- Test: `tests/evals/test_judges.py`（`TestRubricContract` 加一个用例）

**Interfaces:**
- Consumes: Task 1 的 `TradeDecision.evidence_refs`（`_serialize_decision` 经 `model_dump()` 已自动透传，本任务只加测试确认）；`Claim` 的 `interpretation`/`stated_value` 字段（`finance_agent.citation.Claim`，extract 已 import-compatible）
- Produces: 无新对外接口。`extract_judge_vars` 输出的 `trade_decision` 含 evidence_refs、`analyst_reports` 含 claims 数值。

- [ ] **Step 1: Write the failing test**

`tests/evals/test_extract.py` 追加（文件已有 `from evals.extract import extract_judge_vars` 等导入；`TradeDecision` 需 `from finance_agent.models import TradeDecision`）：

```python
class TestSerializeDecisionEvidenceRefs:
    """_serialize_decision / trade_decision 变量含 evidence_refs。"""

    def test_judge_var_trade_decision_contains_evidence_refs(self):
        state = {
            "final_trade_decision": TradeDecision.model_validate({
                "action": "buy",
                "confidence": 0.75,
                "reasoning": "理由",
                "evidence_refs": [{"claim": "ROE 3.4%", "source": "fundamental"}],
            }),
            "analyst_reports": {},
            "risk_debate_history": [],
        }
        vars_ = extract_judge_vars(state)
        assert "evidence_refs" in vars_["trade_decision"]
        assert "fundamental" in vars_["trade_decision"]


class TestSummarizeAnalystReportsKeepsNumbers:
    """_summarize_analyst_reports 必须保留可核对的数值（claims 附注）。"""

    def test_claim_numbers_preserved(self):
        reports = {
            "fundamental": {
                "agent_name": "fundamental",
                "summary": "盈利能力稳健",
                "key_findings": ["ROE 提升"],
                "claims": [
                    {
                        "claim_type": "numerical",
                        "source_type": "data",
                        "field_ref": "profitability_metrics.roe.2024",
                        "stated_value": 3.4,
                        "interpretation": "ROE 处于行业中等水平",
                    }
                ],
                "markdown": "# fundamental\n正文",
            }
        }
        state = {
            "final_trade_decision": {},
            "analyst_reports": reports,
            "risk_debate_history": [],
        }
        vars_ = extract_judge_vars(state)
        assert "3.4" in vars_["analyst_reports"]
        assert "ROE 处于行业中等水平" in vars_["analyst_reports"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_extract.py -k "EvidenceRefs or KeepsNumbers" -v`
Expected: FAIL — `analysis_reports` 变量无 claims 数值（`test_claim_numbers_preserved` 里 `"3.4" not in vars_["analyst_reports"]`）；`test_judge_var_trade_decision_contains_evidence_refs` 在模型未定义时同样红（若 Task 1 先合入则此用例绿，只余 KeepsNumbers 红——两者都需实现）。

- [ ] **Step 3: Write minimal implementation**

`evals/extract.py`：替换 `_summarize_analyst_reports` 并在其后新增 `_format_claims`：

```python
def _summarize_analyst_reports(reports: dict) -> str:
    parts: list[str] = []
    for name, rep in reports.items():
        rep = _as_dict(rep)
        if not rep:
            continue
        text = rep.get("summary") or rep.get("conclusion") or ""
        if not text:
            text = json.dumps(rep, ensure_ascii=False)[:500]
        claims = _format_claims(rep.get("claims") or [])
        if claims:
            text = f"{text}\n论据: {claims}"
        parts.append(f"【{name}】{text}")
    return "\n".join(parts)


def _format_claims(claims: list) -> str:
    """把报告 Claim 列表压缩成 judge 可核对的一行（论据 + 数值）。

    judge 需要具体数值核对 evidence_refs 的 claim（delta 根因 2：摘要
    抹掉数值导致「无中生有」误判）。interpretation 缺失时退回 stated_value。
    """
    items: list[str] = []
    for c in claims:
        c = _as_dict(c)
        if not c:
            continue
        interp = c.get("interpretation", "")
        value = c.get("stated_value", "")
        if interp and value not in ("", None):
            items.append(f"{interp}({value})")
        elif interp:
            items.append(interp)
        elif value not in ("", None):
            items.append(str(value))
    return "; ".join(items)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_extract.py -v`
Expected: PASS（原有 TestExtractJudgeVars / TestPydanticStateCompat 9 个用例 + 新增 2 个全绿）。

- [ ] **Step 5: rubric 更新（先写失败断言）**

`tests/evals/test_judges.py::TestRubricContract` 加用例：

```python
    def test_decision_grounding_rubric_mentions_evidence_refs(self):
        rubric = RUBRICS["decision_grounding"]
        assert "evidence_refs" in rubric
        assert "无引用" in rubric or "按以下原规则" in rubric
```

Run: `uv run pytest tests/evals/test_judges.py -k mentions_evidence_refs -v`
Expected: FAIL。

- [ ] **Step 6: rubric 实现**

`evals/judges.py` `RUBRICS["decision_grounding"]` 文本替换为：

```python
    "decision_grounding": (
        """你是投资决策依据评审专家。
【分析师结论】{{analyst_reports}}
【Research Manager 结论】{{research_manager_decision}}
【交易决策】{{trade_decision}}
评估交易决策的论据是否有前文支撑:
若交易决策含 evidence_refs（结构化论据引用，每项含 claim 与 source），逐条核对：
- claim 的数值/事实能在对应 source（technical/macro/fundamental/sentiment/debate_bull/debate_bear/research_manager）的结论中找到出处，
  且 reasoning 的主要论据都能在 evidence_refs 中找到对应项 → 4-5 分；
- source 与论据对不上、claim 数值在来源中不存在（无中生有）、或 evidence_refs 大量缺失
  reasoning 论据 → 1-2 分。
无 evidence_refs 时按以下原规则从自由文本推断（不因缺字段报错）:
5 = 决策的每条论据都能在分析师结论/辩论结论中找到出处
4 = 主要论据有出处,个别细节无明确支撑
3 = 部分论据有出处,存在未论证的跳跃
2 = 论据与前文关联薄弱,或与前文结论有张力未解释
1 = 决策与前文矛盾,或论据无中生有
"""
        + _JSON_TAIL
    ),
```

- [ ] **Step 7: Run rubric tests**

Run: `uv run pytest tests/evals/test_judges.py -v`
Expected: PASS（含新用例 + 既有 4 维度/JSON 约束/输入缺失守卫用例）。

- [ ] **Step 8: Commit**

```bash
git add evals/extract.py evals/judges.py tests/evals/test_extract.py tests/evals/test_judges.py
git commit -m "feat(evals): decision_grounding judge 输入含 evidence_refs 与 claims 数值，rubric 对齐结构化核对"
```

---

### Task 3: 全量回归 + 静态检查 + delta 验证 + 提交

**Files:** 无代码改动；验证 + 勾选 `openspec/changes/improve-decision-grounding/tasks.md`（1.1/1.2/1.3/2.1/2.2/2.3/3.1-3.4）。

- [ ] **Step 1: 全量测试**

Run: `uv run pytest tests/ -m "not live" -q`
Expected: `1185 passed`（或 ≥ 基线，0 failed）。

- [ ] **Step 2: lint / 类型**

Run: `uv run ruff check`
Expected: `All checks passed!`
Run: `uv run mypy`
Expected: `Success: no issues found`

- [ ] **Step 3: delta 验证**

Run: `openspec validate improve-decision-grounding --strict`
Expected: 通过。

- [ ] **Step 4: tasks.md 回填勾选**

`openspec/changes/improve-decision-grounding/tasks.md` 全部勾选（1.1-3.4）。

- [ ] **Step 5: Commit**

```bash
git add openspec/changes/improve-decision-grounding/
git commit -m "docs(evals): improve-decision-grounding tasks 全勾，delta 待人工验证"
```