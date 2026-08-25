# Harden Prompt Deploy Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 prompt 发布脚本提为正式部署工具，给 eval 加"Langfuse production 版本 vs 本地 .md 一致性"前置门禁，并在 AGENTS.md 声明权威源。

**Architecture:** `git mv` 发布脚本到 `scripts/deploy_prompts.py`（逻辑不变）；`evals/run.py` 新增 `_verify_prompt_sync(client)` helper（逐字文本比对，CRLF 归一化），main() 在 `_collect_prompt_versions` 后调用，不一致 sys.exit 并列出差异；AGENTS.md 测试约束区补一行权威源声明。加载机制不变（仍 Langfuse 优先）。

**Tech Stack:** Python 3.14、pytest、ruff、mypy、Langfuse SDK、git mv。

## Global Constraints

- 工作目录: `D:\WorkSpace\finance_analysis_agent`（执行时 worktree），main HEAD `f82cd12`
- 测试命令: `uv run pytest <path> -v`；Lint: `uv run ruff check src tests`；类型: `uv run mypy src`
- **文本比对逐字节（CRLF→LF 归一化后）**，不比版本号（design D2）
- 门禁失败 = 非零退出 + 列出不一致 prompt 名 + 提示 `scripts/deploy_prompts.py`（design D3）
- `_PROMPT_NAMES` 已存在于 evals/run.py（14 个名称，含 3 个模式 prompt）
- scripts/ 目录含两个 untracked 旧脚本（evals_gated_run.py/observe_langfuse_experiments.py）——**不准顺手跟踪**，git add 用精确 pathspec
- 不改变加载机制、不改变 prompt 内容、不改变 run_experiment 流程
- 中文 prompt 文件 UTF-8 读取

---

### Task 1: 迁移发布脚本为 scripts/deploy_prompts.py

**Files:**
- Rename: `tests/scripts/import_prompts_to_langfuse.py` → `scripts/deploy_prompts.py`（git mv）
- Modify: `scripts/deploy_prompts.py` docstring（前几行）

**Interfaces:**
- Consumes: 无（纯文件迁移 + docstring）
- Produces: `scripts/deploy_prompts.py`（可执行：`uv run python scripts/deploy_prompts.py [--dry-run] [--labels ...] [--exclude ...]`）

- [ ] **Step 1: git mv（无失败测试——文件迁移本身）**

```bash
cd /d/WorkSpace/finance_analysis_agent && git mv tests/scripts/import_prompts_to_langfuse.py scripts/deploy_prompts.py
```

- [ ] **Step 2: 更新 docstring 前几行**

把文件头 docstring（`"""批量导入本地 prompts/*.md 到 Langfuse（ADR-0016）。` 附近的用途说明）改为正式部署入口表述，保留参数说明。内容参考：

```python
"""批量部署本地 prompts/*.md 到 Langfuse production label（ADR-0016）。

正式部署入口：本地 .md（git 跟踪）是提示词唯一权威源，Langfuse 为部署产物。
修改 prompt 后必须执行本脚本发布，否则 eval 门禁（_verify_prompt_sync）会拒绝运行。

用法：
    uv run python scripts/deploy_prompts.py
    uv run python scripts/deploy_prompts.py --dry-run
    uv run python scripts/deploy_prompts.py --exclude quick_mode
```

- [ ] **Step 3: 确认无代码引用残留 + 验证脚本可运行**

```bash
cd /d/WorkSpace/finance_analysis_agent && grep -rn "import_prompts_to_langfuse" --include="*.py" --include="*.md" --include="*.toml" . | grep -v ".venv" | grep -v "2026-08-25-update-agent-prompt-cycle-fit.md" || echo "无引用残留"
uv run python scripts/deploy_prompts.py --dry-run
```

Expected: `--dry-run` 打印 14 个文件清单不实际导入。

- [ ] **Step 4: Commit**

```bash
git add scripts/deploy_prompts.py tests/scripts/import_prompts_to_langfuse.py
git commit -m "chore(prompts): 发布脚本迁移为 scripts/deploy_prompts.py 正式部署入口 (harden-prompt-deploy-consistency)"
```

---

### Task 2: eval 前置版本一致性门禁

**Files:**
- Modify: `evals/run.py`（新增 `_verify_prompt_sync` helper + main() 调用）
- Test: `tests/evals/test_run.py`（追加 `TestVerifyPromptSync` 类）

**Interfaces:**
- Consumes: `evals.run._PROMPT_NAMES`（14 个）+ `_collect_prompt_versions`；`finance_agent.prompts` 本地目录
- Produces: `_verify_prompt_sync(client) -> list[str]`（不一致的 prompt 名列表）；main() 在 prompt_versions 打印后调用

**helper 契约**：
```python
def _verify_prompt_sync(client) -> list[str]:
    """校验 Langfuse production prompt 与本地 .md 一致（CRLF 归一化逐字比对）。

    返回不一致的 prompt 名列表；空列表 = 全部一致。
    """
    from pathlib import Path
    prompts_dir = Path(__file__).resolve().parents[1] / "prompts"
    mismatched: list[str] = []
    for name in _PROMPT_NAMES:
        local = (prompts_dir / f"{name}.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        try:
            remote = str(getattr(client.get_prompt(name), "prompt", "")).replace("\r\n", "\n")
        except Exception:
            mismatched.append(f"{name} (Langfuse 拉取失败)")
            continue
        if local != remote:
            mismatched.append(name)
    return mismatched
```

`main()` 在 `print("prompt_versions:", ...)` 之后插入：

```python
    mismatched = _verify_prompt_sync(client)
    if mismatched:
        sys.exit(
            "错误: 以下 prompt 的 Langfuse production 版本与本地 .md 不一致，"
            "拒绝运行实验（防测错版本）:\n  - "
            + "\n  - ".join(mismatched)
            + "\n请先执行 `uv run python scripts/deploy_prompts.py` 发布后再运行。"
        )
```

- [ ] **Step 1: Write the failing test**

`tests/evals/test_run.py` 追加：

```python
class TestVerifyPromptSync:
    """eval 前置门禁：Langfuse production vs 本地 .md 一致性校验。"""

    def _mock_client(self, texts: dict[str, str]):
        client = MagicMock()
        def fake_get(name):
            p = MagicMock()
            p.prompt = texts.get(name, "")
            return p
        client.get_prompt.side_effect = fake_get
        return client

    def test_all_consistent_returns_empty(self):
        from evals import run
        import evals.run as run_mod
        local = {n: (Path(__file__).resolve().parents[1] / "src/finance_agent/prompts" / f"{n}.md").read_text(encoding="utf-8") for n in run._PROMPT_NAMES}
        client = self._mock_client(local)
        assert run._verify_prompt_sync(client) == []

    def test_mismatch_lists_differing_prompt(self):
        from evals import run
        texts = {n: "x" for n in run._PROMPT_NAMES}  # 全部与本地不同
        client = self._mock_client(texts)
        result = run._verify_prompt_sync(client)
        assert len(result) == len(run._PROMPT_NAMES)
        assert run._PROMPT_NAMES[0] in result
```

> 注意 `Path` 需 import。测试 `test_all_consistent_returns_empty` 中本地路径用 `parents[1]`（tests/evals → 仓库根 → src/.../prompts）计算；与实现里 `parents[1]`（evals/ → 仓库根）不同——以能读到真实文件为准，可写死绝对路径 `Path(__file__).resolve().parents[2] / "src/finance_agent/prompts"`（tests/evals/test_run.py → parents[2] = 仓库根）。

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/evals/test_run.py::TestVerifyPromptSync -v`
Expected: FAIL（`_verify_prompt_sync` 不存在 → AttributeError）

- [ ] **Step 3: Write minimal implementation**

按上述 helper 契约 + main() 插入实现（插入位置：`evals/run.py` 的 `_collect_prompt_versions` 函数之后、`main` 之前加 helper；main 里 prompt_versions 打印后加调用）。

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/evals/test_run.py -v`
Expected: PASS（新 2 用例 + 既有用例）

- [ ] **Step 5: Commit**

```bash
git add evals/run.py tests/evals/test_run.py
git commit -m "feat(evals): eval 前置 prompt 版本一致性门禁 (harden-prompt-deploy-consistency)"
```

---

### Task 3: AGENTS.md 权威源声明

**Files:**
- Modify: `AGENTS.md`（测试约束区）

**Interfaces:**
- Consumes: 无
- Produces: AGENTS.md 测试约束区补一条

- [ ] **Step 1: Write the failing test**

无代码测试——文档契约由人工核对 + spec「Scenario 文档声明存在」验收。直接实现。

- [ ] **Step 2: Modify AGENTS.md**

在 `## 测试约束` 区（文件末尾）追加一条：

```markdown
- 提示词权威源：`src/finance_agent/prompts/*.md`（git 跟踪）是唯一权威源，Langfuse 为部署产物快照；修改 prompt 后必须执行 `uv run python scripts/deploy_prompts.py` 发布，否则 eval 门禁拒绝运行（见 openspec specs/prompt-deploy-consistency）
```

- [ ] **Step 3: Verify**

```bash
cd /d/WorkSpace/finance_analysis_agent && grep -n "deploy_prompts" AGENTS.md
```

Expected: 命中新行。

- [ ] **Step 4: Commit**

```bash
git add AGENTS.md
git commit -m "docs(agents): 声明提示词权威源与发布约定 (harden-prompt-deploy-consistency)"
```

---

### Task 4: 全量验证

**Files:**
- 无新文件；运行验证命令

- [ ] **Step 1: Full test suite** — `uv run pytest -m "not live"` → 0 failed
- [ ] **Step 2: Lint** — `uv run ruff check src tests` → All passed
- [ ] **Step 3: Type** — `uv run mypy src` → 无新增错误（基线 69 既有）
- [ ] **Step 4: 门禁真机验证**

```bash
cd /d/WorkSpace/finance_analysis_agent
# 故意改一个本地 .md 不发布 → eval 应被拦
echo "" >> src/finance_agent/prompts/trader.md && uv run python -m evals.run "gate-test" 2>&1 | grep -E "不一致|拒绝|deploy_prompts" | head -5; git checkout src/finance_agent/prompts/trader.md
# 恢复后应放行（--help 证明无门禁报错进入参数解析即可，不真跑实验）
uv run python -m evals.run --help >/dev/null 2>&1 && echo "门禁放行路径 OK"
```

Expected: 不一致时非零退出 + 差异列表；恢复后正常。

- [ ] **Step 5: 验证记录 + Commit**

写 `tests/validation/2026-08-25-harden-prompt-deploy-consistency-validation.md`（含门禁真机验证输出），提交。