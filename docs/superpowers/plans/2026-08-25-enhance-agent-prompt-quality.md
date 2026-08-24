# Enhance Agent Prompt Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 10 个角色提示词补齐分析方法论/反幻觉硬规则/对抗性辩论/决策语义契约，并收敛股票解析硬编码 prompt（删除 nlp.py 冗余解析与 REACT_SYSTEM_PROMPT 死代码）。

**Architecture:** 全部改动集中在 `src/finance_agent/prompts/*.md` 模板文本 + `src/finance_agent/nodes/report.py` 摘要 system prompt + 删除 `src/finance_agent/nlp.py` 冗余模块。输出 JSON schema 与 LangGraph 节点结构不变。契约测试直接读文件断言关键段落存在（参照 `tests/test_trade_decision_prompts.py` 的 `_load` 模式），防止编辑漂移。

**Tech Stack:** Python 3.14（.venv）、pytest、ruff、mypy、Langfuse（prompt 版本管理，未启用时本地兜底）。

## Global Constraints

- 工作目录: `D:\WorkSpace\finance_analysis_agent`，HEAD 基线 `d4e1a82`
- 运行测试: `uv run pytest <path> -v`；Lint: `uv run ruff check`；类型: `uv run mypy`
- 提示词正文用中文，禁用 emoji，保持现有文件的行内代码/JSON 示例风格
- 不改变任何输出 JSON schema、state 字段、LangGraph 节点结构与调用签名
- 每个分析师/辩论者/决策层提示词必须保留现有内容（含 evidence_refs 段），只追加新段落
- 硬编码收敛只删除冗余：`nlp.py` 在生产 src 中无 import（已确认），`REACT_SYSTEM_PROMPT` 在 src/tests 中仅定义无引用（已确认）
- 契约测试关键词必须是稳定段落标题（如 `## 反幻觉硬规则`），不得断言全文措辞

---

### Task 1: 分析师提示词 — 方法论 + 反幻觉硬规则

**Files:**
- Modify: `src/finance_agent/prompts/fundamental_analyst.md`
- Modify: `src/finance_agent/prompts/macro_analyst.md`
- Modify: `src/finance_agent/prompts/technical_analyst.md`
- Modify: `src/finance_agent/prompts/sentiment_analyst.md`
- Create: `tests/test_prompt_contracts.py`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces: `tests/test_prompt_contracts.py::_load(name)`（后续任务复用）、`assert 反幻觉硬规则` 等断言模式；4 个分析师 .md 追加"## 分析方法论"与"## 反幻觉硬规则"两段

- [ ] **Step 1: Write the failing test**

创建 `tests/test_prompt_contracts.py`，断言 4 个分析师提示词含方法论与硬规则段：

```python
"""提示词行为契约（enhance-agent-prompt-quality）。

prompt 是行为契约的一部分：分析师必须含反幻觉硬规则与分析方法论，
辩论者必须含对抗性指令，决策层必须含语义契约，research_manager 必须
含评级表态，deep_mode 必须含输出约束。
"""

from pathlib import Path

import pytest

_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "src/finance_agent/prompts"


def _load(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text(encoding="utf-8")


ANALYSTS = ["fundamental_analyst", "macro_analyst", "technical_analyst", "sentiment_analyst"]


@pytest.mark.parametrize("name", ANALYSTS)
class TestAnalystAntiHallucination:
    def test_has_methodology_section(self, name):
        assert "## 分析方法论" in _load(f"{name}.md")

    def test_has_hard_rules_section(self, name):
        assert "## 反幻觉硬规则" in _load(f"{name}.md")

    def test_mandates_data_sufficiency_declaration(self, name):
        assert "数据不足" in _load(f"{name}.md")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_contracts.py -v`
Expected: FAIL（12 个断言：每个分析师缺 "## 分析方法论" 与 "## 反幻觉硬规则" 与 "数据不足"）

- [ ] **Step 3: Write minimal implementation**

对 4 个文件各追加两段。通用模板（正文按各角色微调）：

**fundamental_analyst.md** 追加：

```markdown
## 分析方法论

- 盈利能力：ROE 高于 15% 且毛利率稳定/上行通常为优质信号，与同业对比判断相对强弱
- 偿债能力：负债率 60% 以下、流动比率大于 1.5、利息保障倍数大于 3 为健康区间的参考
- 现金流：经营现金流/净利润 大于 1 说明利润含金量高，长期低于 0.8 需警惕
- 估值：PE/PB 与同业及自身历史分位对比，判断贵贱，GARP 关注 PEG 是否合理
- 趋势：单季数据波动大，结论优先基于多期趋势与同业对比，不基于单点值

## 反幻觉硬规则

- 仅使用「输入」部分提供的数据进行推理，不得用模型自身记忆中的数值填补
- 把输入数据的最新报告日期视为「现在」，不得使用该日期之后的知识
- 不得编造不存在的指标值、同比数或事件
- 数据不足或缺失时，明确写出「数据不足」并说明影响，不得假装有数据
```

**macro_analyst.md** 追加：

```markdown
## 分析方法论

- CPI：同比上升 3% 以上为通胀压力参考线，负值需警惕通缩；区分食品/核心项影响
- PMI：以 50 为荣枯线——50 上方制造业扩张，下方收缩；关注连续 3 期方向
- M2：增速高于 GDP 增速+CPI 时流动性偏宽松，反之偏紧
- LPR：降息利好的高负债行业排序 > 银行股利空，升息反之；结合行业属性判断

## 反幻觉硬规则

- 仅使用「输入」部分提供的宏观数据进行推理，不得用模型自身记忆中的数值填补
- 把输入数据的最新日期视为「现在」，不得使用该日期之后的知识
- 不得编造不存在的指标值或事件
- 数据不足或缺失时，明确写出「数据不足」并说明影响，不得假装有数据
```

**technical_analyst.md** 追加：

```markdown
## 分析方法论

- 趋势：MA5/10/20 多头排列（短期在上）为上升趋势参考；MA20/60 关系判断中期方向
- 动量：RSI 高于 70 为超买、低于 30 为超卖；高位顶背离、低位底背离是反转参考
- 波动：BOLL 上/中/下轨收口后开口方向指示趋势启动；触及上轨不必然反转
- 交叉：MACD 金叉/死叉结合零轴位置判断强弱；KDJ 在震荡市更灵敏，趋势市易失真
- 所有判断必须基于输入行情的具体数值，不得用记忆中的历史行情补图

## 反幻觉硬规则

- 仅使用「输入」部分提供的 K 线和技术指标数据进行推理
- 把输入数据的最新日期视为「现在」，不得使用该日期之后的知识
- 不得编造不存在的指标值或价格
- 数据不足或缺失时，明确写出「数据不足」并说明影响，不得假装有数据
```

**sentiment_analyst.md** 追加：

```markdown
## 分析方法论

- 情感倾向：按新闻标题/正文关键词与事件性质归类正/负/中性，给出数量占比
- 重大事件：并购、高管变动、政策、产品发布按影响程度分级（强烈/中等/轻微）
- 趋势：比较近 7 天与之前时段的正面/负面新闻比例变化
- 风险信号：负面新闻集中度、监管风险、连续利空为高风险信号
- 新闻数据缺失时必须标注「新闻数据暂不可用」，不得凭空编造舆情

## 反幻觉硬规则

- 仅使用「输入」部分提供的新闻与事件数据进行推理
- 把输入数据的最新日期视为「现在」，不得使用该日期之后的知识
- 不得编造不存在的新闻、事件或观点
- 数据不足或缺失时，明确写出「数据不足」并说明影响，不得假装有数据
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_contracts.py -v`
Expected: PASS（12 passed）

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_contracts.py src/finance_agent/prompts/fundamental_analyst.md src/finance_agent/prompts/macro_analyst.md src/finance_agent/prompts/technical_analyst.md src/finance_agent/prompts/sentiment_analyst.md
git commit -m "feat(prompts): 分析师提示词补齐分析方法论+反幻觉硬规则 (enhance-agent-prompt-quality)"
```

---

### Task 2: 辩论者提示词 — 对抗性辩论指令

**Files:**
- Modify: `src/finance_agent/prompts/bull_debater.md`
- Modify: `src/finance_agent/prompts/bear_debater.md`
- Modify: `src/finance_agent/prompts/risk_debater.md`
- Modify: `tests/test_prompt_contracts.py`

**Interfaces:**
- Consumes: `_load` from Task 1
- Produces: 3 个辩论者 .md 追加"## 辩论纪律"段（含"引用-反驳"指令）

- [ ] **Step 1: Write the failing test**

在 `tests/test_prompt_contracts.py` 追加：

```python
DEBATERS = ["bull_debater", "bear_debater", "risk_debater"]


@pytest.mark.parametrize("name", DEBATERS)
class TestDebaterAdversarialInstruction:
    def test_has_debate_discipline_section(self, name):
        assert "## 辩论纪律" in _load(f"{name}.md")

    def test_mandates_refute_opponent(self, name):
        text = _load(f"{name}.md")
        assert "反驳" in text
        assert "论点" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_contracts.py::TestDebaterAdversarialInstruction -v`
Expected: FAIL（6 个断言）

- [ ] **Step 3: Write minimal implementation**

对 3 个文件各追加一段（risk_debater 保留 `{role}`/`{perspective}` 占位机制不变）：

```markdown
## 辩论纪律

- 必须针对对方上一轮论点逐条回应：先引用对方观点（原话或要点），再给出反驳或支持
- 引用具体数据或分析师结论支撑论述，不得空泛表态
- 若存在辩论历史，论述必须与历史衔接，不得重复已说过的内容
- 对方论据有漏洞、或过度乐观/悲观时，明确指出并给出理由
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_contracts.py::TestDebaterAdversarialInstruction -v`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_contracts.py src/finance_agent/prompts/bull_debater.md src/finance_agent/prompts/bear_debater.md src/finance_agent/prompts/risk_debater.md
git commit -m "feat(prompts): 辩论者提示词补齐对抗性辩论指令 (enhance-agent-prompt-quality)"
```

---

### Task 3: 决策层提示词 — 语义契约

**Files:**
- Modify: `src/finance_agent/prompts/trader.md`
- Modify: `src/finance_agent/prompts/risk_judge.md`
- Modify: `src/finance_agent/prompts/fund_manager.md`
- Modify: `tests/test_prompt_contracts.py`

**Interfaces:**
- Consumes: `_load` from Task 1
- Produces: trader/risk_judge 追加"## 决策语义"段（保留 evidence_refs 段），fund_manager 追加"## 决策语义"段

- [ ] **Step 1: Write the failing test**

在 `tests/test_prompt_contracts.py` 追加：

```python
DECISION_PROMPTS = ["trader", "risk_judge", "fund_manager"]


@pytest.mark.parametrize("name", DECISION_PROMPTS)
class TestDecisionSemantics:
    def test_has_semantics_section(self, name):
        assert "## 决策语义" in _load(f"{name}.md")


class TestTraderSemantics:
    def test_position_size_defined(self):
        text = _load("trader.md")
        assert "light" in text
        assert "moderate" in text
        assert "heavy" in text

    def test_confidence_anchored(self):
        assert "0.7" in _load("trader.md")


class TestRiskJudgeSemantics:
    def test_balanced_evidence_guidance(self):
        assert "均衡" in _load("risk_judge.md")


class TestFundManagerSemantics:
    def test_decision_options_defined(self):
        text = _load("fund_manager.md")
        assert "approve" in text
        assert "reject" in text
        assert "return" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_contracts.py::TestDecisionSemantics tests/test_prompt_contracts.py::TestTraderSemantics tests/test_prompt_contracts.py::TestRiskJudgeSemantics tests/test_prompt_contracts.py::TestFundManagerSemantics -v`
Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

**trader.md** 追加（保留现有 evidence_refs 段）：

```markdown
## 决策语义

- buy：强信念建仓/加仓；sell：强信念退出/减仓；hold：维持现有仓位；watch：观望，等待更多信号
- position_size 档位：light=试探性仓位（如总资金 10-20%）、moderate=标准仓位（30-50%）、heavy=重仓（50% 以上）
- confidence 锚点：≥0.7 高置信（多源一致且关键数据明确）；0.4-0.7 中等（存在分歧或数据部分缺失）；<0.4 低置信（证据不足，应倾向 watch）
```

**risk_judge.md** 追加（保留现有 evidence_refs 段）：

```markdown
## 决策语义

- buy/sell/hold/watch 含义与 Trader 阶段一致；你的职责是综合风控辩论后确认或修正
- 当多空/风险论据证据均衡时，倾向 hold/watch 而非强行买卖
- 采纳 trader 方案中的论据时须基于风险辩论后仍成立的证据；被风险辩论推翻的论据不得沿用
- confidence 锚点：≥0.7 高置信、0.4-0.7 中等、<0.4 低置信
```

**fund_manager.md** 追加：

```markdown
## 决策语义

- approve：批准执行——决策与风控结论一致、论据充分
- reject：拒绝——存在明确未处理的风险或论据矛盾，直接终止
- return：退回 Trader 重新评估——存在可修正的缺陷（最多 1 次），退回理由需具体
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_contracts.py -v`
Expected: PASS（此前全部 + 新增断言通过）

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_contracts.py src/finance_agent/prompts/trader.md src/finance_agent/prompts/risk_judge.md src/finance_agent/prompts/fund_manager.md
git commit -m "feat(prompts): 决策层提示词补齐语义契约 (enhance-agent-prompt-quality)"
```

---

### Task 4: research_manager 评级表态 + deep_mode/report 摘要约束

**Files:**
- Modify: `src/finance_agent/prompts/research_manager.md`
- Modify: `src/finance_agent/prompts/deep_mode.md`
- Modify: `src/finance_agent/nodes/report.py:178-180`（摘要 system prompt）
- Modify: `tests/test_prompt_contracts.py`

**Interfaces:**
- Consumes: `_load` from Task 1；`report.py:178` 现有 `system = (...)` 字符串
- Produces: research_manager 追加"## 评级表态"段；deep_mode 追加"## 输出约束"段；report.py 摘要 system prompt 追加"仅基于所提供材料"约束

- [ ] **Step 1: Write the failing test**

在 `tests/test_prompt_contracts.py` 追加：

```python
class TestResearchManagerStance:
    def test_has_stance_section(self):
        assert "## 评级表态" in _load("research_manager.md")

    def test_mandates_direction(self):
        text = _load("research_manager.md")
        assert "看多" in text
        assert "看空" in text
        assert "中性" in text


class TestDeepModeOutputConstraint:
    def test_has_output_constraint_section(self):
        assert "## 输出约束" in _load("deep_mode.md")

    def test_bounded_to_tool_output(self):
        assert "工具输出" in _load("deep_mode.md")


class TestReportSummaryGrounding:
    def test_mandates_material_only(self):
        src = Path(__file__).resolve().parents[1] / "src/finance_agent/nodes/report.py"
        text = src.read_text(encoding="utf-8")
        assert "仅基于" in text
        assert "不得引入" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_contracts.py::TestResearchManagerStance tests/test_prompt_contracts.py::TestDeepModeOutputConstraint tests/test_prompt_contracts.py::TestReportSummaryGrounding -v`
Expected: FAIL（5 个断言失败；deep_mode 已含"不得引入"不在此类断言中）

- [ ] **Step 3: Write minimal implementation**

**research_manager.md**：保留第一行，追加：

```markdown

## 评级表态

- 必须给出明确的评级倾向：看多 / 看空 / 中性，不得回避表态
- 先概括多空双方核心理由，再给出你的判断与核心依据（引用辩论中的具体论据，不得泛泛而谈）
- 若多空证据均衡或信息不足，须说明取舍理由与依据，而不是含糊其辞
```

**deep_mode.md** 追加（文件末尾）：

```markdown
## 输出约束

- 摘要只能引用 run_deep_analysis 工具输出中的内容，不得补充工具未提供的数值或结论
```

**report.py**：第 178-180 行 `system = (...)` 改为：

```python
    system = (
        "你是投研报告编辑。根据用户关注点和各层分析产出，写一段 150-200 字的研究聚焦摘要，"
        "紧扣用户关注点组织语言，点出最关键的结论与数据。纯文本，不使用 emoji，不输出标题。"
        "内容仅基于所提供材料中的数据组织，不得引入材料外的数值或推测。"
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_contracts.py -v`
Expected: PASS（全部断言通过）

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_contracts.py src/finance_agent/prompts/research_manager.md src/finance_agent/prompts/deep_mode.md src/finance_agent/nodes/report.py
git commit -m "feat(prompts): research_manager 评级表态 + deep_mode/report 摘要仅基于输入 (enhance-agent-prompt-quality)"
```

---

### Task 5: 硬编码 prompt 收敛 — 删除 nlp.py 冗余解析 + REACT_SYSTEM_PROMPT 死代码

**Files:**
- Delete: `src/finance_agent/nlp.py`
- Modify: `src/finance_agent/react_agent.py:98-139`（删除 REACT_SYSTEM_PROMPT 常量）
- Delete: `tests/llm/test_legacy_migration.py` 中 `_NLP_CT` 常量与 `TestNlpMigration` 类（第 18、24-79 行附近）
- Modify: `tests/test_prompt_contracts.py`

**Interfaces:**
- Consumes: 已确认事实——`src/` 生产代码无 `finance_agent.nlp` import；`REACT_SYSTEM_PROMPT` 在 src/tests 中仅定义无引用；`api.py` 不引用 nlp/resolve_stock
- Produces: 股票解析 LLM 提示词仅存在于 react_agent.py（`_search_with_llm_reasoning`）；nlp.py 与 REACT_SYSTEM_PROMPT 消失

- [ ] **Step 1: Write the failing test**

在 `tests/test_prompt_contracts.py` 追加（断言收敛后的单一事实）：

```python
SRC_DIR = Path(__file__).resolve().parents[1] / "src/finance_agent"


class TestStockParsingConvergence:
    def test_stock_parsing_prompt_lives_only_in_react_agent(self):
        # 生产代码中「你是A股股票代码解析助手」只允许出现在 react_agent.py 一处
        hits = []
        for py in SRC_DIR.rglob("*.py"):
            if "finance_agent.nlp" in py.read_text(encoding="utf-8"):
                hits.append(py)
        assert hits == [], f"nlp.py 仍被引用: {hits}"

    def test_react_system_prompt_removed(self):
        ra = (SRC_DIR / "react_agent.py").read_text(encoding="utf-8")
        assert "REACT_SYSTEM_PROMPT" not in ra
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_contracts.py::TestStockParsingConvergence -v`
Expected: FAIL（nlp.py 尚在且被 legacy 测试引用；REACT_SYSTEM_PROMPT 尚存）

- [ ] **Step 3: Write minimal implementation**

3a. 删除 `src/finance_agent/nlp.py`（整个文件；`app_search` 等公共能力在 software_agent 内部已由 `react_agent.search_stock_tool` 覆盖，见其四级降级 STEP 2a/2b/2c/3/4）。

3b. `src/finance_agent/react_agent.py` 删除第 96-139 行区域（`# ── ReAct system prompt ──` 注释 + `REACT_SYSTEM_PROMPT = """..."""` 常量；保留 `REACT_TOOLS` 与 `search_stock_tool` 及以下实现）：

```python
# （删除前）
REACT_TOOLS = [SEARCH_STOCK_TOOL, DEEP_ANALYSIS_TOOL, WEB_SEARCH_TOOL]

# ── ReAct system prompt ──
REACT_SYSTEM_PROMPT = """你是一个专业的A股投研分析助手，负责理解用户的分析需求并调用合适的工具完成任务。
...

# ── Stock search tool implementation ──
def search_stock_tool(query: str, api_key: str | None = None) -> dict:
```

```python
# （删除后）
REACT_TOOLS = [SEARCH_STOCK_TOOL, DEEP_ANALYSIS_TOOL, WEB_SEARCH_TOOL]

# ── Stock search tool implementation ──
def search_stock_tool(query: str, api_key: str | None = None) -> dict:
```

3c. `tests/llm/test_legacy_migration.py`：删除 `_NLP_CT = "finance_agent.nlp.complete_text"` 一行与整个 `class TestNlpMigration:`（其 3 个测试）及其引用 `from finance_agent.nlp import _resolve_with_llm`。保留 TestReactAgentMigration / TestWebFetcherMigration / TestReportNodeMigration。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_contracts.py tests/llm/test_legacy_migration.py -v`
Expected: PASS（收敛断言通过，legacy 迁移测试其余类仍通过）

- [ ] **Step 5: Commit**

```bash
git add -A src/finance_agent/nlp.py src/finance_agent/react_agent.py tests/llm/test_legacy_migration.py tests/test_prompt_contracts.py
git commit -m "refactor(prompts): 收敛股票解析单一实现 + 移除 REACT_SYSTEM_PROMPT 死代码 (enhance-agent-prompt-quality)"
```

---

### Task 6: 全量验证

**Files:**
- 无新文件；运行验证命令

**Interfaces:**
- Consumes: Task 1-5 全部改动
- Produces: 通过证据（测试输出、ruff/mypy 输出、人工抽查记录）

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest`
Expected: 0 failures（全量回测，确认无回归；合约测试断言全部通过）

- [ ] **Step 2: Run lint**

Run: `uv run ruff check src tests`
Expected: All checks passed（仅任务改动，无新增告警）

- [ ] **Step 3: Run type check**

Run: `uv run mypy`
Expected: Success（无新增错误）

- [ ] **Step 4: Manual spot-check（人工验证）**

触发一份深度分析报告（`uv run uvicorn finance_agent.api:app --port 8000` + 前端或直连 API），抽查：
- 输出 JSON schema 与改动前一致（AnalystReport/TradeDecision/DebateMessage 结构未变）
- trader reasoning 每条例据有对应 evidence_ref，且数值与来源报告一致
- 辩论内容出现"针对对方论点"的回应痕迹而非各自复述
- 摘要（聚焦摘要）无材料外数值

记录验证结果到 `tests/validation/2026-08-25-enhance-agent-prompt-quality-validation.md`（模板参照 `docs/project-workflow.md` §5 人工验证报告）。

- [ ] **Step 5: Commit validation record**

```bash
git add tests/validation/2026-08-25-enhance-agent-prompt-quality-validation.md
git commit -m "docs(validation): enhance-agent-prompt-quality 人工验证报告"
```

---

（可选，Langfuse 启用时）**Task 7: Langfuse prompt 版本发布**

如果 `load_prompt_with_meta` 实际从 Langfuse production label 拉取（配置启用），需为改动的 10 个 prompt 名发布新 production 版本使线上生效；未启用则跳过（本地文件为权威，test_prompt_contracts.py 已覆盖本地基线）。