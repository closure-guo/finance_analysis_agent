# Proposal: harden-prompt-deploy-consistency

## Why

ADR-0016 定义了"Langfuse production 优先、本地 prompts/*.md 兜底"的双源加载机制，但实现存在三处缺陷（实测踩坑）：

1. **静默漂移**：契约测试读本地 .md，真实运行读 Langfuse，二者可长期不一致且无任何机制发现——2026-08-25 曾发生 Langfuse 停留在 ver=1（连 evidence_refs 都没有）而本地已是新版，两轮 eval 全测旧 prompt 跑完才发现。
2. **发布非显式部署**：发布脚本 `tests/scripts/import_prompts_to_langfuse.py` 位于测试目录，不属部署流水线，无门禁强制"改完 .md 必须发布"，漂移成为常态而非异常。
3. **eval 无版本一致性校验**：`evals/run.py` 的 `prompt_versions` 仅记录实际版本，不校验"Langfuse production 版本 == 本地文件"，测错版本无法在运行前拦截。

## What Changes

- **发布脚本成为正式部署工具**：`tests/scripts/import_prompts_to_langfuse.py` 迁移为 `scripts/deploy_prompts.py`（保留原有 --dry-run/--labels/--exclude 参数与幂等语义），删除原测试目录副本；文档引用同步更新。
- **eval 前置版本校验门禁**：`evals/run.py` 在 run_experiment 之前校验每个 prompt 的 Langfuse production 版本与本地 .md 一致；任一不一致 → 明确报错列出差异项并拒绝运行（提示先 deploy），不再静默带病跑。
- **权威源声明**：在 AGENTS.md 测试约束区补一句"本地 prompts/*.md（git 跟踪）是唯一权威源，Langfuse 是部署产物；改 prompt 必须同步发布（scripts/deploy_prompts.py）"。

不改变加载机制本身（仍 Langfuse 优先），不改变 prompt 内容。

## Capabilities

- **New Capabilities**: `prompt-deploy-consistency`（发布工具 + eval 门禁 + 权威源声明）
- **Modified Capabilities**: 无（agent-prompt-contracts 本 delta 不涉及提示词行为变更；加载机制行为不变）

## Impact

- 代码：`scripts/deploy_prompts.py`（新，内容≈现有 tests/scripts 版）；`tests/scripts/import_prompts_to_langfuse.py`（删）；`evals/run.py`（main 加门禁 + helper）；`AGENTS.md`（测试约束区加一行）
- 行为：eval 前漂移显式拦截；发布入口正式化
- 测试：新门禁单测（mock get_prompt 返回与本地不同内容 → 拒绝；一致 → 放行）
- 无第三方依赖新增