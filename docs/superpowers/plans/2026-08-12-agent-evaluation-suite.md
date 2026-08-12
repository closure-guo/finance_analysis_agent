# agent-evaluation-suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `evals/` 评估套件(与 src 平级、业务零侵入):2 确定性评估器 + 4 LLM-as-Judge + 16 条 Dataset + run_experiment 一键实验,支撑 prompt 回归与 Judge 校准。

**Architecture:** 全部代码在 `evals/` 新目录,只读复用 `finance_agent` 的 graph/agent/loader/parse_json_response/truncate_for_trace,不修改任何 src 文件。实验经 langfuse 4.13 `DatasetClient.run_experiment(task=, evaluators=)` 跑(自动建 dataset run + trace 关联);langfuse 未配置时降级为本地循环(--local)。Judge 用独立 `Langfuse(environment="langfuse-llm-as-a-judge")` client 包裹 litellm 直调,成本独立核算。

**Tech Stack:** langfuse 4.13(dataset/experiment API)、litellm(judge 直调)、LangGraph invoke(deep task)、harness Agent.run_sync(quick task)、pytest。

**Spec:** `openspec/changes/agent-evaluation-suite/specs/evaluation/spec.md`(6 个 ADDED Requirement;Requirement 5 校准与 Requirement 6 线上托管 Evaluator 是人工门禁,本计划交付其输入产物与配置文档)。

## Global Constraints

1. **业务零侵入铁律**:禁止修改 `src/finance_agent/` 任何文件。只允许 import 复用。每个 task commit 前自查 `git diff --stat HEAD` 不含 src/。
2. **确定性评估器 SHALL NOT 调 LLM**:`section_coverage`/`ticker_match` 纯函数,零 LLM 调用(测试用 mock 断言 `litellm.completion` 未被调)。
3. **Judge 硬约束**:模型 `deepseek/deepseek-chat`,`temperature=0`;每个 rubric 末尾含「只输出 JSON: {"score": <1-5>, "reason": "<一句话理由>"}」与「不以报告长度论优劣」;解析失败重试一次,仍失败 `score=None`(不阻塞,计入 judge 失败率)。
4. **Judge 环境标记**:judge LLM 调用 SHALL 经独立 `Langfuse(environment="langfuse-llm-as-a-judge")` client 的 `start_as_current_observation(as_type="generation")` 包裹;langfuse 未配置(无 LANGFUSE_PUBLIC_KEY/SECRET_KEY)时降级为无 trace 直调,judge 功能不受影响。
5. **目录纪律**:代码 `evals/`;测试 `tests/evals/`;实验结果 JSON `reports/evals/`;验证报告 `tests/validation/`;配置文档 `evals/hosted_evaluator_setup.md`。禁止根目录新建其他目录。
6. **expected_output 只含结构性断言**(`ticker`/`must_cover`/`should_clarify`),SHALL NOT 含时效财务数值。
7. **并发**:`run_experiment(max_concurrency=1)`(管线单次分钟级,默认 50 会打爆 LLM 配额)。
8. **序列化**:task 返回值必须 JSON 可序列化——SHALL NOT 把含 DataFrame 的原始 state 放进 task output;judge 变量在 task 内经 `extract_judge_vars` 预提取为字符串。
9. **pytest 纪律**:`unittest.mock.patch(..., return_value=X)`(禁 `monkeypatch.setattr(..., return_value=)`,后者是 TypeError);新测试只增不改;`uv run pytest tests/ --ignore=tests/e2e --ignore=tests/scripts -m "not live" -x -q` 全绿;ruff 0 错误;mypy 零新增(基线 75 错误,HEAD vs merge-base 对比)。
10. **意图澄清与 follow_up 首版**:dataset 含 schema 完整 item;task 对 `follow_up` 及 `should_clarify` item 返回 `skipped` 原因,evaluators 对 `report=None` 返回 null/0 不报错。
11. **命名/注释**:camelCase 局部变量遵循项目既有风格混杂现状(eval/ 新代码用 snake_case 纯 Python 风格即可),注释中文。
12. **复用 import**:`from finance_agent.nodes._llm_utils import parse_json_response`、`from finance_agent.langfuse_tracing import truncate_for_trace, get_langfuse`——只读复用,禁止改原文件。

---

### Task 1: 确定性评估器(sections.py + evaluators.py)

**Files:**
- Create: `evals/__init__.py`(空文件)
- Create: `evals/sections.py`
- Create: `evals/evaluators.py`
- Test: `tests/evals/__init__.py`(空)、`tests/evals/test_evaluators.py`

**Interfaces:**
- Consumes: 无(纯函数)
- Produces:
  - `find_section(section: str, report: str) -> bool`(sections.py)
  - `section_coverage(report: str | None, expected_output: dict) -> dict | None` → `{"name": "section_coverage", "value": float 0-1, "comment": str | None}`;expected 无 `must_cover` 时返回 `None`
  - `ticker_match(ticker: str | None, expected_output: dict) -> dict | None` → `{"name": "ticker_match", "value": 1.0|0.0, "comment": str | None}`;expected 无 `ticker` 时返回 `None`
  - `make_evaluation(result: dict) -> "Evaluation"`(dict → langfuse Evaluation 适配,Task 6 用)

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_evaluators.py
"""确定性评估器单测:零 LLM 调用、同义词匹配、expected 缺省跳过。"""
from unittest.mock import patch

from evals.evaluators import section_coverage, ticker_match
from evals.sections import find_section


class TestFindSection:
    def test_exact_hit(self):
        assert find_section("偿债能力", "...偿债能力较强...") is True

    def test_synonym_hit(self):
        # spec「章节命中 SHALL 经同义词词典匹配」:"偿债分析" 命中 "偿债能力"
        assert find_section("偿债能力", "下面进行偿债分析...") is True

    def test_english_synonym_hit(self):
        assert find_section("盈利能力", "ROE 维持在 25%") is True

    def test_miss(self):
        assert find_section("技术面", "公司盈利良好") is False

    def test_unknown_section_falls_back_to_literal(self):
        # 词典没有的章节名,退化为字面匹配
        assert find_section("冷门章节", "包含冷门章节四个字") is True
        assert find_section("冷门章节", "完全没有相关内容") is False


class TestSectionCoverage:
    def test_full_coverage(self):
        report = "偿债能力分析:良好。盈利能力:ROE 高。技术面:均线上扬。风险提示:注意波动。"
        result = section_coverage(report, {"must_cover": ["偿债能力", "盈利能力", "技术面", "风险提示"]})
        assert result == {"name": "section_coverage", "value": 1.0, "comment": None}

    def test_partial_coverage_with_synonym(self):
        # "偿债分析" 命中 "偿债能力";"风险提示" 缺失
        report = "偿债分析:良好。盈利能力:ROE 高。技术面:均线上扬。"
        result = section_coverage(report, {"must_cover": ["偿债能力", "盈利能力", "技术面", "风险提示"]})
        assert result["value"] == 0.75
        assert "风险提示" in result["comment"]

    def test_missing_must_cover_returns_none(self):
        assert section_coverage("任何报告", {}) is None
        assert section_coverage("任何报告", {"ticker": "600519"}) is None

    def test_none_report_scores_zero_when_must_cover_present(self):
        result = section_coverage(None, {"must_cover": ["偿债能力"]})
        assert result["value"] == 0.0


class TestTickerMatch:
    def test_match(self):
        assert ticker_match("600519", {"ticker": "600519"})["value"] == 1.0

    def test_mismatch(self):
        assert ticker_match("000001", {"ticker": "600519"})["value"] == 0.0

    def test_missing_ticker_in_expected_returns_none(self):
        assert ticker_match("600519", {}) is None

    def test_none_ticker_scores_zero(self):
        assert ticker_match(None, {"ticker": "600519"})["value"] == 0.0


class TestNoLlmCall:
    def test_deterministic_evaluators_never_call_llm(self):
        # spec「确定性评估器 SHALL NOT 发起任何 LLM 调用」
        with patch("litellm.completion") as mock_llm:
            section_coverage("偿债能力 盈利能力", {"must_cover": ["偿债能力", "盈利能力"]})
            ticker_match("600519", {"ticker": "600519"})
        mock_llm.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_evaluators.py -v`
Expected: FAIL(ModuleNotFoundError: evals)

- [ ] **Step 3: Write minimal implementation**

```python
# evals/__init__.py
```

```python
# tests/evals/__init__.py
```

```python
# evals/sections.py
"""必备章节同义词词典(design 决策 5:替代裸字符串 in 匹配)。

每个必备章节配一组同义词,命中任一即算覆盖。词典没有的章节名退化为
字面匹配。首版词典按 4 分析师 + 报告骨架的常见章节维护,bad case 驱动追加。
"""

SECTION_SYNONYMS: dict[str, list[str]] = {
    "宏观环境": ["宏观环境", "宏观分析", "宏观经济", "政策面", "宏观"],
    "基本面": ["基本面", "基本面分析", "财务分析", "财务状况", "财务"],
    "偿债能力": ["偿债能力", "偿债分析", "债务分析", "资产负债率", "流动比率", "solvency"],
    "盈利能力": ["盈利能力", "盈利分析", "利润率", "ROE", "毛利率", "profitability"],
    "技术面": ["技术面", "技术分析", "K线", "均线", "走势分析", "趋势"],
    "市场情绪": ["市场情绪", "情绪分析", "资金面", "市场情绪面", "情绪"],
    "估值": ["估值", "估值分析", "估值水平", "PE", "PB", "市盈率"],
    "风险提示": ["风险提示", "风险分析", "风险因素", "风险揭示", "风险"],
    "交易建议": ["交易建议", "操作建议", "投资建议", "决策建议", "交易策略"],
}


def find_section(section: str, report: str) -> bool:
    """章节命中判定:同义词词典匹配,未知章节退化为字面匹配。"""
    synonyms = SECTION_SYNONYMS.get(section, [section])
    return any(s in report for s in synonyms)
```

```python
# evals/evaluators.py
"""确定性评估器:零 token、可重算、可进 CI(spec Requirement「确定性评估器」)。"""
from __future__ import annotations

from evals.sections import find_section


def section_coverage(report: str | None, expected_output: dict) -> dict | None:
    """必备章节覆盖率。expected 无 must_cover 时返回 None(不计入该维度)。"""
    must_cover = expected_output.get("must_cover")
    if not must_cover:
        return None
    if report is None:
        return {"name": "section_coverage", "value": 0.0, "comment": "无报告产出"}
    missing = [s for s in must_cover if not find_section(s, report)]
    value = (len(must_cover) - len(missing)) / len(must_cover)
    return {
        "name": "section_coverage",
        "value": round(value, 4),
        "comment": f"缺失章节: {', '.join(missing)}" if missing else None,
    }


def ticker_match(ticker: str | None, expected_output: dict) -> dict | None:
    """标的解析正确性。expected 无 ticker 时返回 None。"""
    expected_ticker = expected_output.get("ticker")
    if not expected_ticker:
        return None
    if ticker is None:
        return {"name": "ticker_match", "value": 0.0, "comment": "未解析出标的"}
    matched = ticker == expected_ticker
    return {
        "name": "ticker_match",
        "value": 1.0 if matched else 0.0,
        "comment": None if matched else f"期望 {expected_ticker},实际 {ticker}",
    }


def make_evaluation(result: dict):
    """评估结果 dict → langfuse Evaluation(langfuse 4.13 experiment API)。

    value 为 float;comment 可为 None。langfuse 未配置环境不会走到这里
    (--local 模式直接消费 dict)。
    """
    from langfuse.experiment import Evaluation

    return Evaluation(name=result["name"], value=result["value"], comment=result.get("comment"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_evaluators.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add evals/__init__.py evals/sections.py evals/evaluators.py tests/evals/__init__.py tests/evals/test_evaluators.py
git commit -m "feat: [evals] 确定性评估器 section_coverage/ticker_match + 同义词词典(Task 1)"
```

---

### Task 2: judge 变量提取(extract.py)

**Files:**
- Create: `evals/extract.py`
- Test: `tests/evals/test_extract.py`

**Interfaces:**
- Consumes: `finance_agent.langfuse_tracing.truncate_for_trace`(只读复用)
- Produces:
  - `extract_judge_vars(state: dict, query: str = "") -> dict[str, str]`,keys 固定:`query / report / report_conclusion / analyst_reports / debate_history / research_manager_decision / trade_decision / risk_judgment / fund_manager_decision`,值全为 `str`(缺失键给 `""`)
  - `extract_conclusion(report: str) -> str`(`## 结论`/`## 总结`/`## 交易建议` 章节到下一 `## ` 或文末;找不到取末尾 500 字符)

**变量映射**(state 键 → judge 变量,对应 spec consistency Scenario):
- `analyst_reports` ← `state["analyst_reports"]`(dict,4 个 key 每个取 `summary`/`conclusion`/截断 JSON)
- `debate_history` ← `state["debate_history"]`(list of dict,每条取 role/content)
- `research_manager_decision` ← `state["research_manager_conclusion"]`(str,注意 state 键名是 conclusion)
- `trade_decision` / `risk_judgment` ← `state["final_trade_decision"]`(dict→JSON 字符串;risk_judgment 额外拼 `state["risk_debate_history"]` 末条)
- `fund_manager_decision` ← `state["fund_manager_decision"]`(str)
- `report` ← `state["final_report"]`;`report_conclusion` ← `extract_conclusion(report)`
- 每个值经 `truncate_for_trace(text, 4096)` 截断(judge prompt 体积控制)

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_extract.py
"""judge 变量提取:state → 9 个字符串变量,缺失容错,结论章节提取。"""
from evals.extract import extract_conclusion, extract_judge_vars


def _state() -> dict:
    return {
        "final_report": "# 报告\n## 财务分析\n很好。\n## 结论\n建议买入,目标价 2000。\n## 风险提示\n波动。",
        "analyst_reports": {
            "fundamental": {"summary": "基本面强劲", "claims": []},
            "technical": {"conclusion": "均线上扬"},
            "macro": {},
            "sentiment": {"summary": "情绪偏热"},
        },
        "debate_history": [
            {"role": "bull", "content": "看多理由"},
            {"role": "bear", "content": "看空理由"},
        ],
        "research_manager_conclusion": "综合看多方占优",
        "final_trade_decision": {"action": "buy", "confidence": 0.8, "reasoning": "论据充分"},
        "risk_debate_history": [{"role": "risky", "content": "激进看法"}],
        "fund_manager_decision": "approve",
    }


class TestExtractJudgeVars:
    def test_nine_keys_all_str(self):
        vars_ = extract_judge_vars(_state(), query="分析茅台")
        expected_keys = {
            "query", "report", "report_conclusion", "analyst_reports",
            "debate_history", "research_manager_decision", "trade_decision",
            "risk_judgment", "fund_manager_decision",
        }
        assert set(vars_.keys()) == expected_keys
        assert all(isinstance(v, str) for v in vars_.values())

    def test_values_mapped_from_state(self):
        vars_ = extract_judge_vars(_state())
        assert "基本面强劲" in vars_["analyst_reports"]
        assert "看多理由" in vars_["debate_history"]
        assert vars_["research_manager_decision"] == "综合看多方占优"
        assert "buy" in vars_["trade_decision"]
        assert vars_["fund_manager_decision"] == "approve"
        assert "建议买入" in vars_["report_conclusion"]

    def test_missing_keys_give_empty_string(self):
        vars_ = extract_judge_vars({})
        assert vars_["report"] == ""
        assert vars_["analyst_reports"] == ""
        assert vars_["fund_manager_decision"] == ""

    def test_long_values_truncated(self):
        state = _state()
        state["research_manager_conclusion"] = "长" * 10000
        vars_ = extract_judge_vars(state)
        assert len(vars_["research_manager_decision"]) < 5000
        assert "truncated" in vars_["research_manager_decision"]


class TestExtractConclusion:
    def test_section_hit(self):
        report = "## 财务分析\nA\n## 结论\n买入。\n## 风险提示\nB"
        assert extract_conclusion(report) == "买入。"

    def test_fallback_to_tail(self):
        report = "没有任何章节标题。" + "尾" * 600
        conclusion = extract_conclusion(report)
        assert conclusion == "尾" * 500

    def test_empty_report(self):
        assert extract_conclusion("") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_extract.py -v`
Expected: FAIL(ModuleNotFoundError: evals.extract)

- [ ] **Step 3: Write minimal implementation**

```python
# evals/extract.py
"""state → judge 变量提取(spec consistency/decision_grounding 变量映射)。

所有值截断到 4096 字节(truncate_for_trace 头尾保留),控制 judge prompt 体积。
state 缺失键一律给空字符串,judge 输入永不 KeyError。
"""
from __future__ import annotations

import json
import re

from finance_agent.langfuse_tracing import truncate_for_trace

_JUDGE_MAX_BYTES = 4096
_CONCLUSION_HEADERS = ("结论", "总结", "交易建议")


def _trunc(text: str) -> str:
    return truncate_for_trace(text, _JUDGE_MAX_BYTES)


def extract_conclusion(report: str) -> str:
    """提取报告结论章节:行首 ## 结论/总结/交易建议 起,到下一 ## 或文末。

    找不到章节标题时取末尾 500 字符(design Open Question:首版启发式)。
    """
    if not report:
        return ""
    pattern = re.compile(
        r"^#{1,4}\s*(?:"
        + "|".join(_CONCLUSION_HEADERS)
        + r")[^\n]*\n(.*?)(?=^#{1,4}\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(report)
    if match:
        return match.group(1).strip()
    return report[-500:]


def _summarize_analyst_reports(reports: dict) -> str:
    parts: list[str] = []
    for name, rep in reports.items():
        if not isinstance(rep, dict):
            continue
        text = rep.get("summary") or rep.get("conclusion") or ""
        if not text:
            text = json.dumps(rep, ensure_ascii=False)[:500]
        parts.append(f"【{name}】{text}")
    return "\n".join(parts)


def _summarize_debate(history: list) -> str:
    parts: list[str] = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "?")
        content = msg.get("content", "")
        parts.append(f"【{role}】{content}")
    return "\n".join(parts)


def extract_judge_vars(state: dict, query: str = "") -> dict[str, str]:
    """提取 9 个 judge 变量,全字符串,缺失给 ""。"""
    report = state.get("final_report") or ""
    decision = state.get("final_trade_decision") or {}
    risk_debate = state.get("risk_debate_history") or []
    risk_tail = _summarize_debate(risk_debate[-2:]) if risk_debate else ""
    return {
        "query": query,
        "report": _trunc(report),
        "report_conclusion": _trunc(extract_conclusion(report)),
        "analyst_reports": _trunc(_summarize_analyst_reports(state.get("analyst_reports") or {})),
        "debate_history": _trunc(_summarize_debate(state.get("debate_history") or [])),
        "research_manager_decision": _trunc(state.get("research_manager_conclusion") or ""),
        "trade_decision": _trunc(json.dumps(decision, ensure_ascii=False) if decision else ""),
        "risk_judgment": _trunc(
            (json.dumps(decision, ensure_ascii=False) if decision else "")
            + ("\n" + risk_tail if risk_tail else "")
        ),
        "fund_manager_decision": state.get("fund_manager_decision") or "",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_extract.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add evals/extract.py tests/evals/test_extract.py
git commit -m "feat: [evals] judge 变量提取 extract_judge_vars + 结论章节启发式(Task 2)"
```

---

### Task 3: LLM-as-Judge(judges.py)

**Files:**
- Create: `evals/judges.py`
- Test: `tests/evals/test_judges.py`

**Interfaces:**
- Consumes: `finance_agent.nodes._llm_utils.parse_json_response`;Task 2 的变量 dict
- Produces:
  - `RUBRICS: dict[str, str]`(4 个 key:`report_relevance / debate_quality / decision_grounding / consistency`)
  - `JUDGE_MODEL = "deepseek/deepseek-chat"`、`JUDGE_ENV = "langfuse-llm-as-a-judge"`
  - `get_judge_langfuse()`(lru_cache;无凭据返回 None)
  - `run_judge(dimension: str, variables: dict[str, str]) -> dict` → `{"name": dimension, "score": int 1-5 | None, "reason": str}`;解析失败重试一次,仍失败 `score=None, reason="judge_parse_failed"`

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_judges.py
"""LLM-as-Judge:rubric 完整性、JSON 解析容错、环境标记、降级。"""
import os
from unittest.mock import MagicMock, patch

from evals.judges import JUDGE_ENV, JUDGE_MODEL, RUBRICS, run_judge


class TestRubricContract:
    def test_four_dimensions(self):
        assert set(RUBRICS.keys()) == {
            "report_relevance", "debate_quality", "decision_grounding", "consistency",
        }

    def test_rubrics_have_json_constraint_and_no_length_bias(self):
        for dim, rubric in RUBRICS.items():
            assert '{"score"' in rubric, f"{dim} rubric 缺 JSON 输出约束"
            assert "不以" in rubric and "长度" in rubric, f"{dim} rubric 缺「不以长度论优劣」"

    def test_consistency_rubric_checks_fund_vs_risk(self):
        # spec consistency Scenario「特别检查 Fund Manager 与 Risk Judge 一致性」
        assert "Fund Manager" in RUBRICS["consistency"]
        assert "Risk Judge" in RUBRICS["consistency"]


def _mock_completion(score_json: str):
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = score_json
    return resp


class TestRunJudge:
    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("evals.judges._judge_client", None)  # 重置 lru_cache 用 patch 见实施说明
    @patch("litellm.completion")
    def test_score_parsed(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 4, "reason": "基本切题"}')
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result == {"name": "report_relevance", "score": 4, "reason": "基本切题"}
        # 裁判模型与温度
        _, kwargs = mock_llm.call_args
        assert kwargs["model"] == JUDGE_MODEL
        assert kwargs["temperature"] == 0.0

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("litellm.completion")
    def test_parse_failure_retries_once_then_null(self, mock_llm):
        # 两次都返回非 JSON → score=None,不抛异常(spec「重试一次,仍失败记 null」)
        mock_llm.return_value = _mock_completion("这不是 JSON")
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result["score"] is None
        assert result["reason"] == "judge_parse_failed"
        assert mock_llm.call_count == 2

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("litellm.completion")
    def test_score_out_of_range_treated_as_failure(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 9, "reason": "x"}')
        result = run_judge("report_relevance", {"query": "q", "report": "r"})
        assert result["score"] is None

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": ""})
    @patch("litellm.completion")
    def test_variables_substituted_into_prompt(self, mock_llm):
        mock_llm.return_value = _mock_completion('{"score": 5, "reason": "ok"}')
        run_judge("report_relevance", {"query": "茅台怎么样", "report": "茅台是好公司"})
        prompt = mock_llm.call_args.kwargs["messages"][0]["content"]
        assert "茅台怎么样" in prompt and "茅台是好公司" in prompt
        assert "{{query}}" not in prompt

    @patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk"})
    @patch("litellm.completion")
    def test_judge_generation_marked_with_env(self, mock_llm):
        """spec「裁判成本独立核算」:有凭据时 generation 经 environment=judge client 包裹。"""
        mock_llm.return_value = _mock_completion('{"score": 3, "reason": "x"}')
        mock_client = MagicMock()
        with patch("evals.judges._create_judge_client", return_value=mock_client) as factory:
            run_judge("report_relevance", {"query": "q", "report": "r"})
        factory.assert_called_once_with(JUDGE_ENV)
        mock_client.start_as_current_observation.assert_called_once()
        _, kwargs = mock_client.start_as_current_observation.call_args
        assert kwargs.get("as_type") == "generation"
```

> 实施说明:`get_judge_langfuse` 用 lru_cache 时,测试隔离靠 patch 模块级工厂 `_create_judge_client(environment)`( judges.py 把 client 构造收敛到该函数),不要用 patch.dict 之外的缓存重置技巧;测试里 patch 该工厂即可。若 lru_cache 干扰,`get_judge_langfuse.cache_clear()` 也可接受。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_judges.py -v`
Expected: FAIL(ModuleNotFoundError: evals.judges)

- [ ] **Step 3: Write minimal implementation**

```python
# evals/judges.py
"""LLM-as-Judge 评估器(spec Requirement「LLM-as-Judge 评估器与 rubric 标准」)。

- 裁判模型 deepseek/deepseek-chat,temperature=0(可复现)
- rubric 末尾强约束 JSON {score, reason} + 「不以长度论优劣」
- 解析失败重试一次,仍失败 score=None(计入失败率,不阻塞实验)
- judge generation 经独立 Langfuse(environment="langfuse-llm-as-a-judge")
  client 包裹,成本 Dashboard 独立核算;无凭据降级为无 trace 直调
"""
from __future__ import annotations

import os
from functools import lru_cache

from finance_agent.nodes._llm_utils import parse_json_response

JUDGE_MODEL = "deepseek/deepseek-chat"
JUDGE_ENV = "langfuse-llm-as-a-judge"

_JSON_TAIL = '只输出 JSON: {"score": <1-5>, "reason": "<一句话理由>"}\n不以报告长度论优劣。'

RUBRICS: dict[str, str] = {
    "report_relevance": """你是投资研究报告评审专家。
【用户查询】{{query}}
【分析报告】{{report}}
评估报告对查询的切题度:
5 = 完全切题,紧扣查询意图展开
4 = 基本切题,少量无关内容
3 = 部分切题,有显著偏离或答非所需的段落
2 = 大部分答非所问,仅边缘相关
1 = 完全答非所问
""" + _JSON_TAIL,
    "debate_quality": """你是投资辩论质量评审专家。
【多空辩论记录】{{debate_history}}
评估辩论的实质交锋程度:
5 = 双方逐条回应对方论点且引用具体证据(数据/事实)
4 = 有实质交锋,证据基本充分,个别论点空泛
3 = 有交锋但多为立场声明,证据引用不足
2 = 交锋形式化,双方自说自话
1 = 单方输出或内容空洞,无实质辩论
""" + _JSON_TAIL,
    "decision_grounding": """你是投资决策依据评审专家。
【分析师结论】{{analyst_reports}}
【Research Manager 结论】{{research_manager_decision}}
【交易决策】{{trade_decision}}
评估交易决策的论据是否有前文支撑:
5 = 决策的每条论据都能在分析师结论/辩论结论中找到出处
4 = 主要论据有出处,个别细节无明确支撑
3 = 部分论据有出处,存在未论证的跳跃
2 = 论据与前文关联薄弱,或与前文结论有张力未解释
1 = 决策与前文矛盾,或论据无中生有
""" + _JSON_TAIL,
    "consistency": """你是投资报告一致性评审专家。
【分析师章节结论】{{analyst_reports}}
【Research Manager 结论】{{research_manager_decision}}
【Risk Judge 裁决】{{risk_judgment}}
【Fund Manager 最终决策】{{fund_manager_decision}}
【最终报告结论章节】{{report_conclusion}}
评估各层结论的一致性:
5 = 各层结论完全一致,无静默推翻
4 = 基本一致,个别表述差异但不影响方向
3 = 存在不一致但已显式说明理由
2 = 存在未说明的结论冲突
1 = 明显自相矛盾(如 Fund Manager 批准与 Risk Judge 否决相悖)
特别关注:Fund Manager 结论是否与 Risk Judge 裁决一致;报告结论章节是否与分析师章节一致。
""" + _JSON_TAIL,
}


def _create_judge_client(environment: str):
    """构造 judge 专用 Langfuse client(独立 environment,成本独立核算)。"""
    from langfuse import Langfuse

    return Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
        environment=environment,
    )


@lru_cache(maxsize=1)
def get_judge_langfuse():
    """judge client 单例;无凭据返回 None(降级为无 trace 直调)。"""
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return None
    try:
        return _create_judge_client(JUDGE_ENV)
    except Exception:
        return None


def _call_judge_llm(prompt: str) -> str:
    """裁判调用:有凭据时经 judge client generation 包裹,否则直调。"""
    import litellm

    kwargs = {
        "model": JUDGE_MODEL,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": prompt}],
    }
    client = get_judge_langfuse()
    if client is None:
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content or ""
    with client.start_as_current_observation(
        name="judge", as_type="generation", model=JUDGE_MODEL, input=prompt
    ) as gen:
        resp = litellm.completion(**kwargs)
        text = resp.choices[0].message.content or ""
        gen.update(output=text)
        return text


def _render(dimension: str, variables: dict[str, str]) -> str:
    prompt = RUBRICS[dimension]
    for key, value in variables.items():
        prompt = prompt.replace("{{" + key + "}}", value or "")
    return prompt


def run_judge(dimension: str, variables: dict[str, str]) -> dict:
    """跑一个 Judge 维度;解析失败重试一次,仍失败 score=None。"""
    prompt = _render(dimension, variables)
    for _attempt in range(2):
        try:
            data = parse_json_response(_call_judge_llm(prompt))
            score = int(data["score"])
            if not 1 <= score <= 5:
                raise ValueError(f"score 越界: {score}")
            return {"name": dimension, "score": score, "reason": str(data.get("reason", ""))}
        except Exception:
            continue
    return {"name": dimension, "score": None, "reason": "judge_parse_failed"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_judges.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add evals/judges.py tests/evals/test_judges.py
git commit -m "feat: [evals] 4 个 LLM-as-Judge rubric + JSON 容错 + judge 环境标记(Task 3)"
```

---

### Task 4: 实验 task 函数(task.py)

**Files:**
- Create: `evals/task.py`
- Test: `tests/evals/test_task.py`

**Interfaces:**
- Consumes: Task 2 `extract_judge_vars`;`finance_agent.graph.build_5layer_graph`;`finance_agent.agent_factory.build_agent`;`finance_agent.langfuse_tracing.get_callback_handler`(只读;**实施时先读 langfuse_tracing.py:55 附近确认其未配置时返回 None 还是抛异常,按实测处理**)
- Produces:
  - `run_task(*, item, **kwargs) -> dict`,返回 JSON 可序列化 dict:
    `{"report": str|None, "ticker": str|None, "judge_vars": dict[str,str], "mode": str, "skipped": str|None}`
  - deep:`build_5layer_graph().invoke(initial_state, config=...)`,initial_state 键与 api.py:727-737 对齐:`stock_code / stock_name / analysis_type="comprehensive" / peer_codes=None / enable_web_search=False / api_key=None / focus=query / llm_config=None`
  - quick:`asyncio.run(build_agent(mode="quick", session_id=...).run_sync(query))`
  - follow_up / 其他:`skipped` 原因,不报错

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_task.py
"""run_task:mode 分派、输出可序列化、follow_up 跳过、graph 配置。"""
import json
from unittest.mock import MagicMock, patch

from evals.task import run_task


class _Item:
    def __init__(self, input_):
        self.input = input_


class TestDeepTask:
    @patch("evals.task.build_5layer_graph")
    def test_deep_invokes_graph_and_extracts(self, mock_build):
        final_state = {
            "final_report": "## 结论\n买入。",
            "analyst_reports": {},
            "debate_history": [],
            "research_manager_conclusion": "rm",
            "final_trade_decision": {"action": "buy"},
            "risk_debate_history": [],
            "fund_manager_decision": "approve",
        }
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = final_state
        mock_build.return_value = mock_graph

        out = run_task(item=_Item({"query": "分析茅台", "mode": "deep",
                                   "stock_code": "600519", "stock_name": "贵州茅台"}))
        assert out["report"] == "## 结论\n买入。"
        assert out["ticker"] == "600519"
        assert out["mode"] == "deep"
        assert out["skipped"] is None
        assert "买入" in out["judge_vars"]["report_conclusion"]
        # 序列化铁律:不得含 DataFrame 等不可序列化对象
        json.dumps(out)
        # initial_state 关键键
        state_arg = mock_graph.invoke.call_args.args[0]
        assert state_arg["stock_code"] == "600519"
        assert state_arg["enable_web_search"] is False


class TestQuickTask:
    @patch("evals.task.build_agent")
    def test_quick_runs_agent_sync(self, mock_build):
        agent = MagicMock()

        async def _run_sync(query):
            return "茅台是好公司"

        agent.run_sync = _run_sync
        mock_build.return_value = agent

        out = run_task(item=_Item({"query": "茅台怎么样", "mode": "quick", "ticker": "600519"}))
        assert out["report"] == "茅台是好公司"
        assert out["ticker"] == "600519"
        assert out["judge_vars"]["query"] == "茅台怎么样"
        mock_build.assert_called_once()
        assert mock_build.call_args.kwargs["mode"] == "quick"
        json.dumps(out)


class TestSkippedModes:
    def test_follow_up_skipped(self):
        out = run_task(item=_Item({"query": "再分析下", "mode": "follow_up", "session_id": "s1"}))
        assert out["skipped"] is not None
        assert out["report"] is None
        json.dumps(out)

    def test_should_clarify_skipped(self):
        out = run_task(item=_Item({"query": "帮我看看", "mode": "deep"}),
                       expected_output={"should_clarify": True})
        assert out["skipped"] is not None
        json.dumps(out)
```

> 实施说明:`run_task(*, item, expected_output=None, **kwargs)`——langfuse run_experiment 会把 expected_output 传进 task;本地循环显式传。`should_clarify` 检查:`expected_output and expected_output.get("should_clarify")`。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_task.py -v`
Expected: FAIL(ModuleNotFoundError: evals.task)

- [ ] **Step 3: Write minimal implementation**

```python
# evals/task.py
"""实验 task 函数:按 item.input.mode 分派管线,输出 JSON 可序列化结果。

- deep:离线 graph.invoke(initial_state),judge_vars 经 extract_judge_vars 预提取
- quick:ReAct agent run_sync(quick 不进 5 层图,无辩论/决策层)
- follow_up / should_clarify:首版跳过(skipped 原因,不报错)
序列化铁律:不得把含 DataFrame 的原始 state 放进返回值。
"""
from __future__ import annotations

import asyncio
from typing import Any

from evals.extract import extract_judge_vars


def _run_deep(inp: dict) -> dict:
    from finance_agent.graph import build_5layer_graph
    from finance_agent.langfuse_tracing import get_callback_handler

    graph = build_5layer_graph()
    initial_state = {
        "stock_code": inp["stock_code"],
        "stock_name": inp.get("stock_name", ""),
        "analysis_type": "comprehensive",
        "peer_codes": None,
        "enable_web_search": False,
        "api_key": None,
        "focus": inp.get("query"),
        "llm_config": None,
    }
    # langfuse 配置时注入回调,使管线 span 挂到实验 item trace 下
    handler = get_callback_handler()
    config = {"callbacks": [handler]} if handler else None
    state = graph.invoke(initial_state, config=config)
    return {
        "report": state.get("final_report"),
        "ticker": inp["stock_code"],
        "judge_vars": extract_judge_vars(state, query=inp.get("query", "")),
        "mode": "deep",
        "skipped": None,
    }


def _run_quick(inp: dict) -> dict:
    from finance_agent.agent_factory import build_agent

    agent = build_agent(mode="quick", session_id=inp.get("session_id"))
    answer = asyncio.run(agent.run_sync(inp["query"]))
    return {
        "report": answer,
        "ticker": inp.get("ticker"),
        "judge_vars": {"query": inp["query"], "report": answer or ""},
        "mode": "quick",
        "skipped": None,
    }


def run_task(*, item, expected_output: dict | None = None, **kwargs: Any) -> dict:
    """langfuse run_experiment TaskFunction 兼容签名(task(*, item, **kwargs))。

    item 可以是 DatasetItemClient(有 .input)或本地 dict(有 ["input"])。
    """
    inp = item.input if hasattr(item, "input") else item["input"]
    exp = expected_output or (item.expected_output if hasattr(item, "expected_output") else None) or {}
    mode = inp.get("mode", "deep")
    if exp.get("should_clarify"):
        return {"report": None, "ticker": None, "judge_vars": {}, "mode": mode,
                "skipped": "意图澄清项首版不进自动化实验"}
    if mode == "deep":
        return _run_deep(inp)
    if mode == "quick":
        return _run_quick(inp)
    return {"report": None, "ticker": None, "judge_vars": {}, "mode": mode,
            "skipped": f"mode={mode} 首版不支持(follow_up 需 session fixture)"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_task.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add evals/task.py tests/evals/test_task.py
git commit -m "feat: [evals] run_task 模式分派(deep graph/quick agent/skip)+ 可序列化输出(Task 4)"
```

---

### Task 5: Dataset(dataset_items.json + dataset_seed.py)

**Files:**
- Create: `evals/dataset_items.json`
- Create: `evals/dataset_seed.py`
- Test: `tests/evals/test_dataset_seed.py`

**Interfaces:**
- Consumes: `finance_agent.langfuse_tracing.get_langfuse`(只读)
- Produces:
  - `DATASET_NAME = "a-share-analysis-v1"`
  - `load_items(path: Path | None = None) -> list[dict]`(读 JSON,seed 与 --local 共用)
  - `seed(client=None) -> dict` → `{"created": int, "skipped": int, "error": str|None}`;幂等键 `(input.query, input.mode)`;dataset 不存在则 `create_dataset(name=DATASET_NAME, ...)`

**覆盖矩阵**(16 条,spec: deep 典型 5-6 / deep 边界 2-3 / quick 3-4 / follow_up 2-3 / 意图澄清 1-2):

```json
[
  {"input": {"query": "全面分析贵州茅台(600519)的投资价值", "mode": "deep", "stock_code": "600519", "stock_name": "贵州茅台"},
   "expected_output": {"ticker": "600519", "must_cover": ["宏观环境", "基本面", "技术面", "市场情绪", "风险提示"]},
   "metadata": {"category": "deep_typical", "source": "hand_authored"}},
  {"input": {"query": "全面分析宁德时代(300750)的投资价值", "mode": "deep", "stock_code": "300750", "stock_name": "宁德时代"},
   "expected_output": {"ticker": "300750", "must_cover": ["基本面", "技术面", "风险提示"]},
   "metadata": {"category": "deep_typical", "source": "hand_authored"}},
  {"input": {"query": "全面分析平安银行(000001)的投资价值", "mode": "deep", "stock_code": "000001", "stock_name": "平安银行"},
   "expected_output": {"ticker": "000001", "must_cover": ["基本面", "估值", "风险提示"]},
   "metadata": {"category": "deep_typical", "source": "hand_authored"}},
  {"input": {"query": "全面分析比亚迪(002594)的投资价值", "mode": "deep", "stock_code": "002594", "stock_name": "比亚迪"},
   "expected_output": {"ticker": "002594", "must_cover": ["基本面", "技术面", "风险提示"]},
   "metadata": {"category": "deep_typical", "source": "hand_authored"}},
  {"input": {"query": "全面分析招商银行(600036)的投资价值", "mode": "deep", "stock_code": "600036", "stock_name": "招商银行"},
   "expected_output": {"ticker": "600036", "must_cover": ["基本面", "估值", "风险提示"]},
   "metadata": {"category": "deep_typical", "source": "hand_authored"}},
  {"input": {"query": "贵州茅台的现金流健康吗?重点看经营性现金流", "mode": "deep", "stock_code": "600519", "stock_name": "贵州茅台"},
   "expected_output": {"ticker": "600519", "must_cover": ["基本面"]},
   "metadata": {"category": "deep_edge", "source": "hand_authored"}},
  {"input": {"query": "全面分析中芯国际(688981)的投资价值", "mode": "deep", "stock_code": "688981", "stock_name": "中芯国际"},
   "expected_output": {"ticker": "688981", "must_cover": ["基本面", "风险提示"]},
   "metadata": {"category": "deep_edge", "source": "hand_authored"}},
  {"input": {"query": "茅台现在能买吗", "mode": "quick", "ticker": "600519"},
   "expected_output": {"ticker": "600519"},
   "metadata": {"category": "quick", "source": "hand_authored"}},
  {"input": {"query": "宁德时代今天怎么样", "mode": "quick", "ticker": "300750"},
   "expected_output": {"ticker": "300750"},
   "metadata": {"category": "quick", "source": "hand_authored"}},
  {"input": {"query": "比亚迪和特斯拉哪个更值得买", "mode": "quick", "ticker": "002594"},
   "expected_output": {},
   "metadata": {"category": "quick", "source": "hand_authored"}},
  {"input": {"query": "银行股现在估值贵吗", "mode": "quick"},
   "expected_output": {},
   "metadata": {"category": "quick", "source": "hand_authored"}},
  {"input": {"query": "那它的风险呢", "mode": "follow_up", "session_id": "fixture-session-1"},
   "expected_output": {},
   "metadata": {"category": "follow_up", "source": "hand_authored"}},
  {"input": {"query": "和目标价比还差多少", "mode": "follow_up", "session_id": "fixture-session-1"},
   "expected_output": {},
   "metadata": {"category": "follow_up", "source": "hand_authored"}},
  {"input": {"query": "换个角度再看看", "mode": "follow_up", "session_id": "fixture-session-2"},
   "expected_output": {},
   "metadata": {"category": "follow_up", "source": "hand_authored"}},
  {"input": {"query": "帮我分析一下这只股票", "mode": "deep"},
   "expected_output": {"should_clarify": true},
   "metadata": {"category": "clarify", "source": "hand_authored"}},
  {"input": {"query": "现在适合入场吗", "mode": "quick"},
   "expected_output": {"should_clarify": true},
   "metadata": {"category": "clarify", "source": "hand_authored"}}
]
```

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_dataset_seed.py
"""Dataset:schema 合规、覆盖矩阵、幂等 seed。"""
import json
from unittest.mock import MagicMock

from evals.dataset_seed import DATASET_NAME, load_items, seed


class TestDatasetItems:
    def test_schema_and_coverage_matrix(self):
        items = load_items()
        assert 15 <= len(items) <= 20
        categories = [it["metadata"]["category"] for it in items]
        for cat, lo, hi in [("deep_typical", 5, 6), ("deep_edge", 2, 3),
                            ("quick", 3, 4), ("follow_up", 2, 3), ("clarify", 1, 2)]:
            assert lo <= categories.count(cat) <= hi, f"{cat}: {categories.count(cat)}"
        for it in items:
            assert it["input"]["query"] and it["input"]["mode"]
            assert it["metadata"]["category"] and it["metadata"]["source"]

    def test_expected_has_no_time_sensitive_numbers(self):
        # spec「expected 不含时效数值」:不允许出现金额/百分比形态
        import re
        for it in load_items():
            text = json.dumps(it["expected_output"], ensure_ascii=False)
            assert not re.search(r"\d+(\.\d+)?\s*(亿|万|%)", text), text


class TestSeed:
    def _client(self, existing_keys=()):
        client = MagicMock()
        ds = MagicMock()
        ds.items = [
            MagicMock(input={"query": q, "mode": m}) for (q, m) in existing_keys
        ]
        client.get_dataset.return_value = ds
        return client

    def test_creates_all_on_empty(self):
        client = self._client()
        result = seed(client=client)
        assert result["created"] == 16
        assert result["skipped"] == 0

    def test_idempotent_on_rerun(self):
        # spec「幂等建库」:全部已存在 → 0 created,不重复
        keys = [(it["input"]["query"], it["input"]["mode"]) for it in load_items()]
        client = self._client(existing_keys=keys)
        result = seed(client=client)
        assert result["created"] == 0
        assert result["skipped"] == 16
        client.create_dataset_item.assert_not_called()

    def test_creates_dataset_when_missing(self):
        client = MagicMock()
        client.get_dataset.side_effect = Exception("not found")
        ds = MagicMock()
        ds.items = []
        client.create_dataset.return_value = ds
        result = seed(client=client)
        client.create_dataset.assert_called_once()
        assert client.create_dataset.call_args.kwargs["name"] == DATASET_NAME
        assert result["created"] == 16

    def test_no_client_returns_error(self):
        result = seed(client=None)
        assert result["created"] == 0
        assert result["error"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_dataset_seed.py -v`
Expected: FAIL(ModuleNotFoundError: evals.dataset_seed)

- [ ] **Step 3: Write minimal implementation**

`evals/dataset_items.json` 用上面「覆盖矩阵」代码块的完整 JSON(16 条,逐条写入文件)。

```python
# evals/dataset_seed.py
"""Dataset 建库(spec Requirement「评估 Dataset 与覆盖矩阵」)。

幂等:以 (input.query, input.mode) 为去重键,已存在 item 跳过不覆盖。
langfuse 未配置时返回 error,不抛异常(CI/本地可无 langfuse 跑 --local)。
"""
from __future__ import annotations

import json
from pathlib import Path

DATASET_NAME = "a-share-analysis-v1"
_ITEMS_PATH = Path(__file__).parent / "dataset_items.json"


def load_items(path: Path | None = None) -> list[dict]:
    """读取 dataset items(seed 与 --local 实验共用的 source of truth)。"""
    return json.loads((path or _ITEMS_PATH).read_text(encoding="utf-8"))


def seed(client=None) -> dict:
    """幂等建库。返回 {created, skipped, error}。"""
    if client is None:
        from finance_agent.langfuse_tracing import get_langfuse

        client = get_langfuse()
    if client is None:
        return {"created": 0, "skipped": 0, "error": "langfuse 未配置,跳过 seed"}
    items = load_items()
    try:
        dataset = client.get_dataset(DATASET_NAME)
    except Exception:
        dataset = client.create_dataset(
            name=DATASET_NAME,
            description="A 股分析评估 Dataset v1(覆盖矩阵:deep 典型/边界、quick、follow_up、意图澄清)",
            metadata={"version": "v1"},
        )
    existing = {(it.input.get("query"), it.input.get("mode")) for it in dataset.items}
    created = skipped = 0
    for item in items:
        key = (item["input"]["query"], item["input"]["mode"])
        if key in existing:
            skipped += 1
            continue
        client.create_dataset_item(
            dataset_name=DATASET_NAME,
            input=item["input"],
            expected_output=item.get("expected_output"),
            metadata=item.get("metadata"),
        )
        created += 1
    client.flush()
    return {"created": created, "skipped": skipped, "error": None}


if __name__ == "__main__":
    print(seed())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_dataset_seed.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add evals/dataset_items.json evals/dataset_seed.py tests/evals/test_dataset_seed.py
git commit -m "feat: [evals] a-share-analysis-v1 Dataset 16 条覆盖矩阵 + 幂等 seed(Task 5)"
```

---

### Task 6: run_experiment 入口(run.py)

**Files:**
- Create: `evals/run.py`
- Test: `tests/evals/test_run.py`

**Interfaces:**
- Consumes: Task 1-5 全部;`langfuse` DatasetClient.run_experiment(探明签名:`dataset.run_experiment(name=, task=, evaluators=, max_concurrency=, metadata=)`,evaluator 签名 `(*, input, output, expected_output, metadata) -> Evaluation | list[Evaluation]`;**实施时先验证 `Evaluation.value` 接受 None,若不接受则 judge 失败返回 `Evaluation(name=f"{dimension}_failed", value=1.0, comment=...)` 并在报告中计入失败率**)
- Produces:
  - `all_evaluators(judge_client_ok: bool) -> list`(确定性 2 + judge 4;quick 模式 item 的 debate/decision/consistency 在适配器内跳过返回 `[]`)
  - `run_local(items, experiment_name) -> list[dict]`(无 langfuse 降级路径)
  - `main()`:`uv run python -m evals.run "<实验名>" [--local]`;产出终端结果表 + `reports/evals/<name>-<YYYYMMDD-HHMMSS>.json`(含 per-item 明细、各 Score 均值、judge 失败数、prompt_versions)
  - `_collect_prompt_versions() -> dict[str, str]`:对 14 个 prompt 名(macro_analyst/fundamental_analyst/technical_analyst/sentiment_analyst/bull_debater/bear_debater/research_manager/trader/risk_debater/risk_judge/fund_manager/quick_mode/deep_mode/follow_up_mode)调 `load_prompt_with_meta(name).prompt_version`(spec「prompt 版本关联」;Langfuse trace 侧由 Delta 1 的 generation metadata 兜底)

- [ ] **Step 1: Write the failing test**

```python
# tests/evals/test_run.py
"""run_experiment:evaluator 装配、quick 模式 judge 跳过、本地降级、结果表。"""
from unittest.mock import MagicMock, patch

from evals.run import all_evaluators, run_local, _mean_rows


class TestEvaluatorAssembly:
    def test_six_evaluators(self):
        evals = all_evaluators()
        assert len(evals) == 6  # 2 确定性 + 4 judge

    def test_deterministic_evaluator_shape(self):
        evals = {e.__name__: e for e in all_evaluators()}
        result = evals["eval_section_coverage"](
            input={"query": "q", "mode": "deep"},
            output={"report": "偿债能力 盈利能力", "ticker": "600519", "judge_vars": {}, "mode": "deep"},
            expected_output={"must_cover": ["偿债能力", "盈利能力"]},
            metadata={},
        )
        assert result is not None
        # langfuse Evaluation 或本地 dict 两种形态都可能,统一经 _as_dict
        assert getattr(result, "name", None) == "section_coverage" or result["name"] == "section_coverage"

    @patch("evals.run.run_judge")
    def test_judge_skipped_for_quick_mode(self, mock_judge):
        mock_judge.return_value = {"name": "debate_quality", "score": 4, "reason": "x"}
        evals = {e.__name__: e for e in all_evaluators()}
        result = evals["eval_debate_quality"](
            input={"query": "q", "mode": "quick"},
            output={"report": "r", "ticker": None, "judge_vars": {}, "mode": "quick"},
            expected_output={},
            metadata={},
        )
        # quick 无辩论 → 返回空(list)或 None,不调 judge
        mock_judge.assert_not_called()
        assert result in (None, [])

    @patch("evals.run.run_judge")
    def test_judge_uses_output_judge_vars(self, mock_judge):
        mock_judge.return_value = {"name": "report_relevance", "score": 5, "reason": "切题"}
        evals = {e.__name__: e for e in all_evaluators()}
        evals["eval_report_relevance"](
            input={"query": "茅台", "mode": "quick"},
            output={"report": "r", "ticker": None,
                    "judge_vars": {"query": "茅台", "report": "茅台好"}, "mode": "quick"},
            expected_output={},
            metadata={},
        )
        mock_judge.assert_called_once_with("report_relevance", {"query": "茅台", "report": "茅台好"})


class TestLocalRun:
    @patch("evals.run.run_task")
    @patch("evals.run.run_judge")
    def test_local_run_produces_rows(self, mock_judge, mock_task):
        mock_task.return_value = {
            "report": "偿债能力 盈利能力", "ticker": "600519",
            "judge_vars": {"query": "q", "report": "r"}, "mode": "deep", "skipped": None,
        }
        mock_judge.return_value = {"name": "report_relevance", "score": 4, "reason": "x"}
        items = [{"input": {"query": "q", "mode": "deep", "stock_code": "600519"},
                  "expected_output": {"ticker": "600519", "must_cover": ["偿债能力"]},
                  "metadata": {"category": "deep_typical", "source": "test"}}]
        rows = run_local(items, "test-exp")
        assert len(rows) == 1
        row = rows[0]
        assert row["scores"]["ticker_match"] == 1.0
        assert row["scores"]["section_coverage"] == 1.0
        assert row["scores"]["report_relevance"] == 4

    def test_mean_rows(self):
        rows = [
            {"scores": {"a": 1.0, "b": 4}, "judge_failures": 0},
            {"scores": {"a": 0.0, "b": None}, "judge_failures": 1},
        ]
        means = _mean_rows(rows)
        assert means["a"] == 0.5
        assert means["b"] == 4.0  # None 不计入均值
        assert means["judge_failures"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_run.py -v`
Expected: FAIL(ModuleNotFoundError: evals.run)

- [ ] **Step 3: Write minimal implementation**

```python
# evals/run.py
"""实验回归工作流(spec Requirement「实验回归工作流」)。

用法:
    uv run python -m evals.run "<实验名>"            # langfuse dataset.run_experiment
    uv run python -m evals.run "<实验名>" --local    # 无 langfuse 本地循环

产出:终端结果表 + reports/evals/<name>-<ts>.json(per-item 明细 + 均值 +
judge 失败数 + prompt_versions)。该 JSON 是 Judge 校准(Req 5,人工)的输入。
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from evals.dataset_seed import DATASET_NAME, load_items
from evals.evaluators import make_evaluation, section_coverage, ticker_match
from evals.judges import run_judge
from evals.task import run_task

_PROMPT_NAMES = [
    "macro_analyst", "fundamental_analyst", "technical_analyst", "sentiment_analyst",
    "bull_debater", "bear_debater", "research_manager", "trader",
    "risk_debater", "risk_judge", "fund_manager",
    "quick_mode", "deep_mode", "follow_up_mode",
]
_JUDGE_DIMS = ["report_relevance", "debate_quality", "decision_grounding", "consistency"]
# quick 模式无辩论/决策层:只有 report_relevance 适用(design §7 过滤器)
_JUDGE_DEEP_ONLY = {"debate_quality", "decision_grounding", "consistency"}


def _collect_prompt_versions() -> dict[str, str]:
    """记录实验所用 prompt 版本(production label;load_prompt_with_meta 只读复用)。"""
    from finance_agent.prompts.loader import load_prompt_with_meta

    versions: dict[str, str] = {}
    for name in _PROMPT_NAMES:
        try:
            versions[name] = str(load_prompt_with_meta(name).prompt_version)
        except Exception:
            versions[name] = "unknown"
    return versions


# ── langfuse evaluator 适配器(签名 (*, input, output, expected_output, metadata))──

def eval_section_coverage(*, input, output, expected_output, metadata):
    result = section_coverage(output.get("report") if output else None, expected_output or {})
    return make_evaluation(result) if result else None


def eval_ticker_match(*, input, output, expected_output, metadata):
    result = ticker_match(output.get("ticker") if output else None, expected_output or {})
    return make_evaluation(result) if result else None


def _judge_adapter(dimension: str):
    def _eval(*, input, output, expected_output, metadata):
        mode = (output or {}).get("mode") or (input or {}).get("mode")
        if mode == "quick" and dimension in _JUDGE_DEEP_ONLY:
            return None  # quick 无辩论,跳过
        if not (output or {}).get("report"):
            return None  # skipped item
        result = run_judge(dimension, (output or {}).get("judge_vars") or {})
        if result["score"] is None:
            # score=null:解析失败,记入失败率(Evaluation.value None 支持实施时验证;
            # 不支持则返回 name=f"{dimension}_failed", value=1.0)
            return make_evaluation(
                {"name": dimension, "value": None, "comment": result["reason"]}
            )
        return make_evaluation(
            {"name": dimension, "value": float(result["score"]), "comment": result["reason"]}
        )

    _eval.__name__ = f"eval_{dimension}"
    return _eval


def all_evaluators() -> list:
    return (
        [eval_section_coverage, eval_ticker_match]
        + [_judge_adapter(d) for d in _JUDGE_DIMS]
    )


# ── 本地降级路径(无 langfuse)──

def _local_scores(output: dict, expected: dict) -> tuple[dict, int]:
    scores: dict = {}
    failures = 0
    for result in (section_coverage(output.get("report"), expected),
                   ticker_match(output.get("ticker"), expected)):
        if result:
            scores[result["name"]] = result["value"]
    mode = output.get("mode")
    for dim in _JUDGE_DIMS:
        if mode == "quick" and dim in _JUDGE_DEEP_ONLY:
            continue
        if not output.get("report"):
            continue
        result = run_judge(dim, output.get("judge_vars") or {})
        if result["score"] is None:
            failures += 1
        else:
            scores[dim] = result["score"]
    return scores, failures


def run_local(items: list[dict], experiment_name: str) -> list[dict]:
    rows: list[dict] = []
    for item in items:
        output = run_task(item=item, expected_output=item.get("expected_output"))
        if output.get("skipped"):
            rows.append({"item": item["input"]["query"], "mode": item["input"]["mode"],
                         "skipped": output["skipped"], "scores": {}, "judge_failures": 0})
            continue
        scores, failures = _local_scores(output, item.get("expected_output") or {})
        rows.append({"item": item["input"]["query"], "mode": item["input"]["mode"],
                     "skipped": None, "scores": scores, "judge_failures": failures})
    return rows


def _mean_rows(rows: list[dict]) -> dict:
    """各 Score 均值(None 不计入)+ judge 失败总数。"""
    buckets: dict[str, list[float]] = {}
    failures = 0
    for row in rows:
        failures += row.get("judge_failures", 0)
        for name, value in (row.get("scores") or {}).items():
            if value is not None:
                buckets.setdefault(name, []).append(float(value))
    means = {name: round(sum(vals) / len(vals), 4) for name, vals in buckets.items() if vals}
    means["judge_failures"] = failures
    return means


def _print_table(rows: list[dict], means: dict) -> None:
    for row in rows:
        if row.get("skipped"):
            print(f"[skip] {row['item']} ({row['mode']}): {row['skipped']}")
            continue
        score_str = " ".join(f"{k}={v}" for k, v in row["scores"].items())
        print(f"[{row['mode']:9}] {row['item'][:30]:32} {score_str}")
    print("─" * 60)
    print("均值:", json.dumps(means, ensure_ascii=False))


def _write_report(rows: list[dict], means: dict, name: str, prompt_versions: dict) -> Path:
    out_dir = Path("reports/evals")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = out_dir / f"{name}-{ts}.json"
    path.write_text(
        json.dumps({"experiment": name, "timestamp": ts,
                    "prompt_versions": prompt_versions,
                    "means": means, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="evals 实验回归")
    parser.add_argument("name", help="实验名(如 baseline-v1)")
    parser.add_argument("--local", action="store_true", help="无 langfuse 本地循环")
    args = parser.parse_args()

    prompt_versions = _collect_prompt_versions()
    print("prompt_versions:", json.dumps(prompt_versions, ensure_ascii=False))

    client = None
    if not args.local:
        from finance_agent.langfuse_tracing import get_langfuse

        client = get_langfuse()

    if client is not None:
        dataset = client.get_dataset(DATASET_NAME)
        result = dataset.run_experiment(
            name=args.name,
            task=run_task,
            evaluators=all_evaluators(),
            max_concurrency=1,  # 管线分钟级,禁高并发
            metadata={"prompt_versions": prompt_versions},
        )
        rows = [
            {"item": str(r.item.input.get("query")), "mode": r.item.input.get("mode"),
             "skipped": None,
             "scores": {e.name: e.value for e in r.evaluations if e.value is not None},
             "judge_failures": sum(1 for e in r.evaluations if e.value is None)}
            for r in result.item_results
        ]
    else:
        print("langfuse 未配置(或 --local),走本地循环")
        rows = run_local(load_items(), args.name)

    means = _mean_rows(rows)
    _print_table(rows, means)
    path = _write_report(rows, means, args.name, prompt_versions)
    print(f"结果已写入 {path}")
    if client is not None:
        client.flush()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_run.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add evals/run.py tests/evals/test_run.py
git commit -m "feat: [evals] run_experiment 入口(langfuse/本地双路)+ 结果表 + prompt 版本关联(Task 6)"
```

---

### Task 7: @live 用例 + 托管 Evaluator 配置文档 + 验证报告 + 质量门禁

**Files:**
- Create: `tests/evals/test_eval_live.py`(`@live`,nightly)
- Create: `evals/hosted_evaluator_setup.md`(Req 6 第二阶段人工配置手册)
- Create: `tests/validation/2026-08-12-agent-evaluation-suite-validation.md`

**Interfaces:**
- Consumes: 全部前序任务
- Produces: @live 冒烟(judge 真实调用 + quick task 真实调用);人工门禁文档

- [ ] **Step 1: Write the @live test**

```python
# tests/evals/test_eval_live.py
"""@live 用例:真实 DeepSeek 裁判 + 真实 quick task,nightly 跑防漂移。"""
import os

import pytest

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.getenv("DEEPSEEK_API_KEY"), reason="需 DEEPSEEK_API_KEY"),
]


def test_live_judge_returns_score_in_range():
    """真实裁判调用:report_relevance 返回 1-5 整数(明显切题的输入应得高分)。"""
    from evals.judges import run_judge

    result = run_judge("report_relevance", {
        "query": "贵州茅台盈利能力如何",
        "report": "贵州茅台盈利能力极强,ROE 长期维持 30% 以上,毛利率 91%。",
    })
    assert result["score"] is not None, f"裁判解析失败: {result}"
    assert 1 <= result["score"] <= 5
    assert result["reason"]


def test_live_quick_task_produces_report():
    """真实 quick task:run_task 产出非空 report(防 ReAct/stub 漂移)。"""
    from evals.task import run_task

    out = run_task(item={"input": {"query": "茅台现在能买吗", "mode": "quick", "ticker": "600519"}})
    assert out["skipped"] is None
    assert out["report"]
    assert out["judge_vars"]["query"] == "茅台现在能买吗"
```

- [ ] **Step 2: collect 验证(本环境不跑 live)**

Run: `uv run pytest tests/evals/test_eval_live.py --collect-only -m live -q`
Expected: 2 tests collected

- [ ] **Step 3: 托管 Evaluator 配置文档**

写 `evals/hosted_evaluator_setup.md`,内容:第二阶段在 Langfuse UI 配置托管 Evaluator 的步骤——① Evaluators → New Managed Evaluator,4 个 Judge 各建一条,rubric 文本从 `evals/judges.py: RUBRICS` 原样复制(线下线上一把尺,design 决策 2),裁判模型 `deepseek-chat`;② 变量映射表(变量名 → trace span 路径,照抄 spec consistency/decision_grounding 的变量清单,依赖 Delta 1 span 保真);③ 采样率初值 10-20%;④ 过滤器:`mode=quick` 的 trace 只挂 `report_relevance`;⑤ Monitors 告警:Score 均值窗口骤降 → webhook;⑥ 校准前置:线下一致性 ≥ 80% 前不得开启线上阻塞。

- [ ] **Step 4: 人工验证报告骨架**

写 `tests/validation/2026-08-12-agent-evaluation-suite-validation.md`:

```markdown
# 人工验证报告: agent-evaluation-suite

**日期**: 2026-08-12
**验证人**: [待填]
**关联 delta**: openspec/changes/agent-evaluation-suite/
**E2E 门禁**: 不适用(纯后端评估基建,非交互类变更,§2 判别)

## 验证结果

| Scenario | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|
| 确定性评估器零 LLM | section_coverage/ticker_match 不调 LLM,同义词命中 | 单测锁定(test_deterministic_evaluators_never_call_llm 等 12 例) | ✅ |
| Judge rubric 契约 | 4 rubric 含 JSON 约束 + 不以长度论优劣 | 单测锁定(test_rubrics_have_json_constraint_and_no_length_bias) | ✅ |
| Judge 容错 | 非 JSON 重试一次后 score=None,不阻塞 | 单测锁定(test_parse_failure_retries_once_then_null) | ✅ |
| Dataset 幂等 | 重复 seed 0 created | 单测锁定(test_idempotent_on_rerun) | ✅ |
| 业务零侵入 | git diff 无 src/ 改动 | 全分支 diff 审查 | ✅ |
| seed 真实建库 | langfuse UI 可见 a-share-analysis-v1 16 条 | [待人工:配好 langfuse 后跑 `uv run python -m evals.dataset_seed`] | ⬜ |
| 基线实验 | `uv run python -m evals.run baseline-v1` 全 Dataset 跑通,产出 reports/evals/ JSON | [待人工:真 LLM,约 1-2 小时] | ⬜ |
| Judge 校准 | 抽 20-30 条人工打分,一致性 ≥ 80% | [待人工:用实验 JSON + Annotation Queue;校准报告回填本节] | ⬜ |
| judge 环境标记 | Langfuse 按 environment=langfuse-llm-as-a-judge 过滤可见裁判 generation | [待人工:实验后 UI 核对] | ⬜ |
| 托管 Evaluator | 按 evals/hosted_evaluator_setup.md 配置,采样 10-20% | [待人工:第二阶段,校准定稿后] | ⬜ |

## 异常记录
[待填]

## 结论
[x] 存在待人工确认项(seed/基线实验/校准/托管配置)
[ ] 全部通过,可 archive
```

- [ ] **Step 5: 质量门禁**

```bash
uv run pytest tests/ --ignore=tests/e2e --ignore=tests/scripts -m "not live" -x -q
uv run ruff check
uv run mypy src/ evals/   # 与基线 75 错误对比(HEAD vs merge-base worktree),零新增
```

Expected: 全绿;ruff 0;mypy 零新增(evals/ 是新目录,基线无,故 evals/ 自身须 0 错误)。

- [ ] **Step 6: Commit**

```bash
git add tests/evals/test_eval_live.py evals/hosted_evaluator_setup.md tests/validation/2026-08-12-agent-evaluation-suite-validation.md
git commit -m "test: [evals] @live 用例 + 托管 Evaluator 配置文档 + 人工验证报告骨架(Task 7)"
```

---

## Self-Review

**1. Spec coverage**(对照 spec 6 个 ADDED Requirement):
- ✅ 确定性评估器(4 Scenario)→ Task 1(同义词/跳过/零 LLM 各有测试)
- ✅ LLM-as-Judge(7 Scenario)→ Task 3(4 rubric/容错/环境标记;rubric 内容按 design 决策 4 补全 consistency,其余按 spec Scenario 的 1-5 定义撰写)
- ✅ Dataset(3 Scenario)→ Task 5(schema/幂等/无时效数值)
- ✅ 实验回归(3 Scenario)→ Task 4+6(run_experiment/prompt 版本/零侵入)
- ⏸ Judge 校准(Req 5)→ 人工门禁;本计划交付校准输入(实验 JSON per-item 明细,Task 6)与验证报告校准栏(Task 7)
- ⏸ 线上托管 Evaluator(Req 6)→ 人工门禁;本计划交付配置手册(Task 7)

**2. Placeholder scan**:无 TBD/TODO;所有代码步含完整实现;dataset_items.json 16 条完整列出。

**3. Type consistency**:`run_judge` 返回 `{"name","score","reason"}` 跨 Task 3/6 一致;task output dict 五键(`report/ticker/judge_vars/mode/skipped`)跨 Task 4/6 一致;`make_evaluation(dict)` 消费 Task 1 的 dict 结构;evaluator 适配器签名 `(*, input, output, expected_output, metadata)` 与 langfuse 4.13 EvaluatorFunction 探明签名一致。

**4. 已知实施风险**(brief 中提示 implementer):
- `Evaluation.value=None` 是否被 langfuse 4.13 接受 → Task 6 实施时验证,不接受则按注释 fallback(`{dim}_failed` value=1.0)
- `get_callback_handler()` 未配置行为 → Task 4 实施时先读 langfuse_tracing.py:55 确认
- `Agent.run_sync` 真实行为 → Task 4 单测已用 async mock,真实路径由 @live 覆盖
- judges.py lru_cache 测试隔离 → 统一 patch `_create_judge_client`
