# Declare Technical Context Array Order — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除第四类契约疾病——在技术指标 context 与分析师 prompt 中声明「序列为时间正序（旧→新），列表末尾为最新一期」，消除 LLM 期次错位（incident 022）。

**Architecture:** 两处文本锚定（`analysts.py` 的 context 注记 + `technical_analyst.md` 反幻觉规则），校验器 `citation.py` 零改动；prompt 改动后须经 `scripts/deploy_prompts.py` 发布（spec prompt-deploy-consistency 门禁）。

**Tech Stack:** Python / FastAPI 后端；`deploy_prompts.py` CLI。

## Global Constraints

- 校验器 `src/finance_agent/citation.py` 的容差语义与三态契约**零改动**（冻结区）。
- prompt 权威源为 `src/finance_agent/prompts/*.md`（git 跟踪）；修改后必须执行 `uv run python scripts/deploy_prompts.py` 发布，否则 eval 门禁拒绝运行。
- context 注记语句必须保持「技术指标数据（…）：\n{json}」的既有拼装结构（`tests/nodes/test_analysts.py` 依赖该分割解析 json）。
- 全量验证：`uv run pytest -m "not live"` / `uv run ruff check` / `uv run mypy`（本 delta 文件范围）。

---

### Task 1: Context 明示数组方向（TDD）

**Files:**
- Modify: `src/finance_agent/nodes/analysts.py`（`_build_technical_context` 的 note 文本，约 193-196 行）
- Test: `tests/nodes/test_analysts.py`（TestTechnicalContext 类内新增）

**Interfaces:**
- Consumes: `_build_technical_context(state: dict) -> str`（既有）
- Produces: `_build_technical_context` 返回的 context 字符串中含「时间正序」与「末尾」字样

- [ ] **Step 1: Write the failing test**

在 `tests/nodes/test_analysts.py` 末尾追加：

```python
class TestTechnicalContextArrayOrder:
    def test_context_declares_ascending_order_tail_latest(self):
        """序列数组为时间正序（旧→新），末尾为最新一期（incident 022 第四类疾病）。"""
        from finance_agent.nodes.analysts import _build_technical_context

        ctx = _build_technical_context({"stock_name": "X", "stock_code": "1"})
        assert "时间正序" in ctx
        assert "末尾" in ctx and "最新" in ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/nodes/test_analysts.py::TestTechnicalContextArrayOrder -v`
Expected: FAIL（当前 note 无方向声明）

- [ ] **Step 3: Implement the context note**

`src/finance_agent/nodes/analysts.py` 中 `_build_technical_context` 的 note 段改为：

```python
note = f"各序列为最近 {_TECHNICAL_CONTEXT_WINDOW} 期，更早历史已省略；序列为时间正序（旧→新），列表末尾为最新一期；" if did_trim else "序列为时间正序（旧→新），列表末尾为最新一期；"
```

（未裁剪时同样声明方向，保持注记恒定。）

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/nodes/test_analysts.py -v`
Expected: PASS（含新增用例与既有 context 解析用例）

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/nodes/analysts.py tests/nodes/test_analysts.py
git commit -m "fix(analysts): 技术指标 context 声明数组方向（正序，末尾=最新）— incident 022 第四类疾病"
```

### Task 2: Prompt 反幻觉自证规则（TDD）

**Files:**
- Modify: `src/finance_agent/prompts/technical_analyst.md`
- Test: `tests/test_prompt_contracts.py`（TestCycleFitMethodology 后新增类）

**Interfaces:**
- Consumes: 无（纯文本契约）
- Produces: prompt 文本含「序列尾部」「末尾」自证要求；`deploy_prompts.py` 可发布

- [ ] **Step 1: Write the failing test**

`tests/test_prompt_contracts.py` 末尾追加：

```python
class TestTechnicalArrayOrderContract:
    """incident 022：引用 -1 前须核对序列尾部（正序，末尾=最新）。"""

    def test_technical_prompt_mandates_tail_verification(self):
        text = _load("technical_analyst.md")
        assert "序列尾部" in text or "末尾" in text
        assert "正序" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompt_contracts.py::TestTechnicalArrayOrderContract -v`
Expected: FAIL

- [ ] **Step 3: Implement the prompt rule**

在 `src/finance_agent/prompts/technical_analyst.md` 的 `## 反幻觉硬规则` 段追加一行：

```markdown
- 引用最新一期（-1）前先核对序列尾部：输入序列为时间正序（旧→新），列表末尾为最新一期；不得把展示首元素或记忆中的历史行情当作最新值
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prompt_contracts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/finance_agent/prompts/technical_analyst.md tests/test_prompt_contracts.py
git commit -m "docs(prompts): 技术分析师反幻觉规则增加序列尾部自证 — incident 022"
```

### Task 3: Prompt 发布 + 全量门禁

**Files:**
- 无代码改动；执行发布脚本

- [ ] **Step 1: 发布 prompt**

Run: `uv run python scripts/deploy_prompts.py`
Expected: 输出中包含 technical_analyst 且 OK/更新成功

- [ ] **Step 2: 全量验证**

Run: `uv run pytest -m "not live" -q`
Expected: 全绿（新增用例 + 存量 1511 基线无回归）
Run: `uv run ruff check src/finance_agent/nodes/analysts.py tests/nodes/test_analysts.py tests/test_prompt_contracts.py`
Expected: 全绿
Run: `uv run mypy src/finance_agent/nodes/analysts.py`
Expected: 零错误

- [ ] **Step 3: Commit 发布产物（如有）**

```bash
git add -A
git commit -m "chore(prompts): 发布 technical_analyst v（方向声明）到 Langfuse"
```

### Task 4: 冒烟回归（live，可选人工）

- [ ] 趋势异动股深跑 1 只（如中际旭创 300308），确认技术类 claim 已按负索引引用且 FAIL 率较 incident 022 的 54% 显著回落
- [ ] 验收数据记入 delta tasks.md 回填（如机器不可复现，标为人工环节待办）