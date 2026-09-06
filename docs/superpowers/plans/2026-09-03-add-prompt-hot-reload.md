# Add Prompt Hot Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Langfuse production 变更 30s 内生效（TTL 缓存）+ 自动回写收编（sync_prompts）+ deploy 预检护栏。

**Architecture:** loader.py 的 lru_cache 替换为共享 TTL 缓存（`_CACHE: dict[str, tuple[float, PromptInfo]]`）；新增 `scripts/sync_prompts.py`（比对口径复用 eval 门禁的 CRLF 归一，git 操作经注入的 runner 便于 tmp 仓库测试）；`deploy_prompts.py` 加 precheck 函数。

**Tech Stack:** 标准库（time/os/subprocess/argparse）+ langfuse SDK + pytest

## Global Constraints

- `load_prompt` / `load_prompt_with_meta` 签名与返回结构不变（11+ caller 零改动）
- TTL 默认 30s，环境变量 `PROMPT_CACHE_TTL` 可覆盖
- 比对口径：`.replace("\r\n", "\n")` 归一后逐字（同 evals/run.py `_verify_prompt_sync`）
- 冲突保护：目标 prompt 文件 `git status --porcelain` 非空 → 不覆盖只告警
- 收编提交只暂存变化的 prompt 文件；提交信息 `chore(prompts): 收编 Langfuse production 变更 <name> v<version>（UI 编辑回流）`
- deploy 预检：任一不一致或不可达 → 非零退出整批拒绝；prompt 在 Langfuse 不存在（404）视为首部属可发布
- 非交互类变更：无前端/SSE/会话，E2E 门禁不适用

---

### Task 1: loader TTL 热更新

**Files:**
- Modify: `src/finance_agent/prompts/loader.py`
- Modify: `tests/test_prompt_loader.py`（补 autouse 清缓存 fixture + TTL 用例）

**Interfaces:**
- Produces: 模块级 `_CACHE: dict[str, tuple[float, PromptInfo]]`、`_cache_ttl() -> float`、`_clear_cache()`、`_cached_info(name) -> PromptInfo`；`load_prompt(name) -> str` / `load_prompt_with_meta(name) -> PromptInfo` 签名不变

- [ ] Step 1: 失败测试（TTL 生效/窗口内缓存/恢复跟随/version 随动 + autouse `_clear_cache` fixture）
- [ ] Step 2: 确认失败 → Step 3: 实现（去 `@lru_cache`，`_cached_info` 包装现 `_fetch` 逻辑）→ Step 4: 全绿
- [ ] Step 5: commit `feat(prompts): loader TTL 热更新(production 30s 跟随)`

### Task 2: sync_prompts.py 收编脚本

**Files:**
- Create: `scripts/sync_prompts.py`
- Test: `tests/test_sync_prompts.py`（tmp git 仓库：`git init` + 假 client）

**Interfaces:**
- Produces: `normalize(text)`、`plan_actions(prompts_dir, client) -> list[Action]`（Action: name/path/status ∈ collect|conflict|ok|local_only）、`apply_actions(actions, repo_root, git=_git, dry_run=False) -> int`、CLI（--once/--watch/--dry-run/--interval）
- git runner 注入：`_git(args: list[str], cwd: Path) -> str`（subprocess, check=True）

- [ ] Step 1: 失败测试（UI 编辑收编+仅含该文件提交 / 本地未提交冲突保护非零 / 一致空操作 / dry-run 不落盘）→ Step 3: 实现 → Step 4: 全绿
- [ ] Step 5: commit `feat(scripts): sync_prompts 收编守护(--watch/--once/--dry-run)`

### Task 3: deploy 预检护栏

**Files:**
- Modify: `scripts/deploy_prompts.py`
- Test: `tests/test_deploy_preflight.py`

**Interfaces:**
- Produces: `precheck(client, files: list[Path], exclude: set[str]) -> tuple[list[str], list[str]]`（mismatched, unreachable）；404/not found 视为不存在（可发布）

- [ ] Step 1: 失败测试（Langfuse 领先拒绝 / 一致放行 / 不可达拒绝 / 不存在放行）→ Step 3: 实现（main 在导入前调 precheck，非空即 return 1）→ Step 4: 全绿
- [ ] Step 5: commit `feat(scripts): deploy_prompts 预检护栏(Langfuse 领先拒绝盲推)`

### Task 4: 验收

- [ ] `uv run pytest -q -m "not live"` 全绿；ruff/format 干净；mypy 改动文件无新增错误
- [ ] 端到端演练：本地改一个 prompt → deploy 预检拒绝（Langfuse 领先反例）/ sync --dry-run 报告 → 一致后发布 → 人工验证报告落 tests/validation/
