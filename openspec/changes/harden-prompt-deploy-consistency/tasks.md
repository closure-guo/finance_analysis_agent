# Tasks: harden-prompt-deploy-consistency

## 1. 发布脚本迁移

- [x] 1.1 `git mv tests/scripts/import_prompts_to_langfuse.py scripts/deploy_prompts.py`；docstring 更新为正式部署入口说明，参数（--dry-run/--labels/--exclude）与幂等语义不变
- [x] 1.2 文档引用同步（计划文件 docs/ 内旧路径 → scripts/deploy_prompts.py）；确认全仓无对 tests/scripts/import_prompts_to_langfuse 的代码引用残留

## 2. eval 前置版本一致性门禁

- [x] 2.1 `evals/run.py` 新增 `_verify_prompt_sync(client) -> list[str]`：遍历 _PROMPT_NAMES，Langfuse production text（`\r\n`→`\n` 归一化）vs 本地 .md（同类归一化）逐字比对，返回不一致列表
- [x] 2.2 main() 在 `_collect_prompt_versions` 后调用：list 非空 → sys.exit 非零并列出差异 prompt + 提示 `scripts/deploy_prompts.py`；一致 → 放行
- [x] 2.3 单测：mock get_prompt 返回与本地不同文本 → 拒绝；相同 → 放行；归一化（CRLF vs LF 不误报）

## 3. AGENTS.md 权威源声明

- [x] 3.1 AGENTS.md 测试约束区补：「本地 prompts/*.md（git 跟踪）是唯一权威源，Langfuse 为部署产物；改 prompt 后必须用 scripts/deploy_prompts.py 发布」

## 4. 验证

- [x] 4.1 `uv run pytest`（非 live 全量）通过；`uv run ruff check` + `uv run mypy` 无新增
- [x] 4.2 真机验证：临时改一个 .md 不发布 → eval 被拦（非零退出 + 差异列表）；恢复并 deploy → 放行；验证记录落 tests/validation/
- [x] 4.3 `openspec validate --all --strict` 通过