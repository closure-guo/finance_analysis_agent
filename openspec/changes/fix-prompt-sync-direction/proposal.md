# Proposal: fix-prompt-sync-direction

## Why

2026-10-05 实证事故（issue #228）：Langfuse production 的 bear_debater/risk_judge/trader 被人为**回退到历史版本**（低于已部署内容），两个方向防护脚本都分不清「Langfuse 领先（UI 独有编辑）」与「Langfuse 回退/落后（命中仓库历史版本，无 UI 独有内容）」：

1. `deploy_prompts` 预检判别式只有「remote==HEAD 放行 / remote≠HEAD 且 ≠local 一律当 UI 编辑拒绝」，回退场景被误拒；
2. 按预检提示跑 `sync_prompts --once` 收编，把回退内容写回仓库并自动提交——**回退了仓库权威源**的三段关键内容（论据期次新鲜度 / sell_type 分型×2），prompt 合同测试转红。

事故已人工修复（陈旧性证明后重推权威版），本 change 把「方向判别」做成代码级防护，杜绝复现。

## What Changes

- **历史版本命中判定**（新共享模块 `scripts/prompt_history.py`）：remote 内容与该文件 git 历史全部已提交版本（CRLF 归一）比对，命中即判「Langfuse 回退/落后（纯陈旧，无 UI 独有内容）」。
- **`sync_prompts` 方向防护**：`collect` 判定前加历史命中检查——remote 命中历史版本 → 新状态 `rollback`，不写回不提交，提示走 `deploy_prompts` 发布覆盖；仅当 remote 为 UI 独有内容（不命中任何历史版本）才收编。
- **`deploy_prompts` 预检区分落后**：remote ≠ local 且 ≠ HEAD 时查历史——命中 → 放行并在输出标注「Langfuse 落后/回退，发布将覆盖」；不命中 → 维持拒绝（真 UI 编辑）。
- **`--force` 显式覆盖通道**：现有 `--force` 只绕过「同内容重发布跳过」；扩展为同时绕过预检的 UI 编辑拦截（逐项打印被覆盖警告），不可达（拉取失败）仍保守拒绝。
- **.env 修复**（本机配置，gitignore 不入库）：`LANGFUSE_HOST` 取消注释指向 `http://localhost:3000`——SDK 缺省打 cloud.langfuse.com 致写操作 401。

不改变 Langfuse 优先的加载机制，不改变任何 prompt 内容。

## Capabilities

- `prompt-deploy-consistency`：预检与收编两个 Requirement 的方向判别细化（MODIFIED）。

## Impact

- `scripts/prompt_history.py`（新增）、`scripts/deploy_prompts.py`、`scripts/sync_prompts.py`
- `tests/test_deploy_preflight.py`、`tests/test_sync_prompts.py`、新增 `tests/test_prompt_history.py`
- 本机 `.env`（LANGFUSE_HOST 取消注释，已完成）
- 风险：`git log` 历史扫描对长历史文件的成本——限 rev-list 条数 + 命中即短路；无 git 环境退化为现行保守语义（任何差异拒绝）。
