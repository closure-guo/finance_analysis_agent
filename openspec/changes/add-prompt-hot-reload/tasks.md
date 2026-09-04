# Tasks: add-prompt-hot-reload

## 1. loader TTL 热更新

- [ ] 1.1 `prompts/loader.py`：`@lru_cache` 替换为 TTL 进程内缓存（默认 30s，`PROMPT_CACHE_TTL` 环境变量可覆盖），`load_prompt` / `load_prompt_with_meta` 签名不变，兜底结果同样缓存、TTL 后重试 Langfuse
- [ ] 1.2 TTL 行为单测（短 TTL：production 切换后生效、TTL 内用缓存、拉取失败回退且恢复后跟随、版本元数据随动）

## 2. sync_prompts 收编脚本

- [ ] 2.1 `scripts/sync_prompts.py`：--once/--watch/--dry-run/--interval；比对口径与 eval 门禁归一一致；写回 + 仅暂存变化 prompt 文件的 git 提交（提交信息含 prompt 名与版本）
- [ ] 2.2 单测：UI 编辑收编、本地未提交改动冲突保护（不覆盖+非零退出）、一致时空操作、dry-run 不落盘

## 3. deploy 预检护栏

- [ ] 3.1 `scripts/deploy_prompts.py` 增加 pre-flight：production ≠ 本地时拒绝发布（非零退出+列出不一致项+提示 sync_prompts --once）；Langfuse 不可达保守拒绝；--dry-run 语义保留
- [ ] 3.2 单测：Langfuse 领先拒绝、一致放行、不可达拒绝

## 4. 验收

- [ ] 4.1 `uv run pytest`（门禁 `-m "not live"`）全绿；`uv run ruff check` + `mypy`（改动文件）无新增错误
- [ ] 4.2 端到端演练记录：deep_mode 合并稿走完整链（收编回写本地 → deploy 预检通过发布 → Langfuse 出新版本 production → 本地与 production 逐字一致 → eval 门禁放行验证）
- [ ] 4.3 非交互类变更确认（无前端/SSE/会话流），E2E 门禁不适用；人工验证报告落 `tests/validation/`
