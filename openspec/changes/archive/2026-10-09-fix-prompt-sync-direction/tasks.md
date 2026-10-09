# Tasks: fix-prompt-sync-direction

## 1. 历史版本命中判定（新共享模块）

- [x] 1.1 `scripts/prompt_history.py`：`match_historical_content(repo_root, rel_path, text, *, limit=300) -> str | None`——`git log --format=%H -n <limit> -- <path>` 枚举版本，逐版本 `git show <sha>:<path>` CRLF 归一比对，命中返回 sha（命中即短路）；文件无 git 历史返回 None
- [x] 1.2 `tests/test_prompt_history.py`：tmp git 仓库实证——命中旧版本返回 sha / 命中 HEAD 返回 sha / 未命中（UI 独有）返回 None / 未跟踪文件返回 None / CRLF 归一命中

## 2. sync_prompts 方向防护

- [x] 2.1 `plan_actions` 增加 `repo_root` 关键字参数；local≠remote 时先查历史：命中 → `Action.status="rollback"`（记 matched sha）；未命中 → 维持 `collect`
- [x] 2.2 `apply_actions` 处理 `rollback`：不写回不提交，打印「Langfuse 回退/落后，不收编，请用 deploy_prompts 发布覆盖」；返回值扩展为 `(exit_code, conflicts, rollbacks)`，rollbacks 非空 → exit 1；既有调用点与测试同步更新
- [x] 2.3 新测试：remote==历史版本 → 拒收编+文件未动+无新 commit+exit 1+提示含 deploy；dry-run 对 rollback 同样不落盘

## 3. deploy_prompts 预检区分落后 + --force

- [x] 3.1 `precheck` 增加 `history` 参数（name → 历史内容集合）；remote≠local 且 ≠HEAD 时：命中历史 → 归入新返回项 `stale`（放行）；不命中 → 维持 `mismatched`（拒绝）。返回值扩展为 `(mismatched, unreachable, identical, stale)`；既有测试同步更新
- [x] 3.2 main()：stale 非空 → 逐项打印「Langfuse 落后/回退，发布将覆盖」后继续；`--force` 时 mismatched 不拦截但逐项打印「将被覆盖」警告，unreachable 仍拒绝；docstring 与 --force help 文案更新
- [x] 3.3 新测试：remote==旧版本 → 放行且列入 stale；remote==HEAD → 放行不列 stale；UI 独有 → 拒绝；--force 绕过 mismatched、不绕 unreachable

## 4. 本机配置（无代码，gitignore）

- [x] 4.1 `.env` 取消 `LANGFUSE_HOST` 注释指向 `http://localhost:3000`（dotenv 解析验证过；compose 后端容器 LANGFUSE_HOST 硬编码 `http://langfuse-web:3000` 不受影响）

## 5. 验证

- [x] 5.1 定向测试：`tests/test_prompt_history.py tests/test_sync_prompts.py tests/test_deploy_preflight.py` 全绿
- [x] 5.2 `uv run ruff check` + `ruff format --check` 绿
- [x] 5.3 真实 Langfuse 冒烟：`deploy_prompts --dry-run` 与 `sync_prompts --dry-run` 对本机 Langfuse（localhost:3000）跑通（只读不写）
- [x] 5.4 全量套件绿（防脚本签名变更波及其它调用点）
