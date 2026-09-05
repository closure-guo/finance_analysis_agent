# Proposal: add-prompt-hot-reload

## Why

当前 prompt 加载用 `@lru_cache` 进程内永久缓存——Langfuse UI 里改了 production 标签/版本，运行时**必须重启进程才生效**（loader.py 注释自认的代价）；同时发布是单向的（本地→Langfuse），UI 里的编辑不在 git，**下一次 deploy 就被静默覆盖**（用户实际遭遇：deep_mode v2 被 deploy 抢走 production）。诉求：Langfuse 改动立即生效 + 持久保存，同时不放弃「本地 git 唯一权威源」的治理模型（spec prompt-deploy-consistency 因静默漂移事故确立）。

## What Changes

- **热更新**：`prompts/loader.py` 的 `@lru_cache` 替换为 30s TTL 进程内缓存——production 标签/版本变更最迟 30 秒对后续请求生效，无需重启（含 docker 容器，runtime 直连 Langfuse）
- **自动回写收编**：新增 `scripts/sync_prompts.py`（`--watch` 守护 / `--once` 手动）：检测 Langfuse production ≠ 本地 md（CRLF/LF 归一比对，口径同 eval 门禁）→ 自动写回本地 md → 自动 git commit（仅暂存该 prompt 文件）；本地有未提交手工改动时**不覆盖只告警**（冲突保护）
- **deploy 预检护栏**：`deploy_prompts.py` 增加 pre-flight——Langfuse production 与本地不一致时拒绝执行并提示先收编，杜绝「deploy 盲推覆盖 UI 编辑」
- **eval 门禁不变**：逐字比对保留，兜底守护失效的异常态；漂移窗口从「永久」缩到「分钟级」
- 部署拓扑约束：回写守护必须在 git 仓库所在宿主机跑（容器内 md 是镜像层，回写不持久）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `prompt-deploy-consistency`: 「本地权威源 → Langfuse 部署产物」契约演进为双向闭环——加载语义（lru_cache→TTL 热更新）、发布护栏（deploy 预检）、新增收编组件（sync_prompts 守护）三条 Requirement MODIFIED/ADDED；eval 前置门禁语义不变

## Impact

- **后端**：`src/finance_agent/prompts/loader.py`（TTL 缓存改造，`load_prompt`/`load_prompt_with_meta` 签名不变）；`scripts/deploy_prompts.py`（pre-flight）
- **新脚本**：`scripts/sync_prompts.py`（回写守护，宿主机运行）
- **测试**：loader TTL 行为单测（fake clock / 短 TTL）、sync_prompts 回写与冲突保护单测、deploy 预检单测；非交互类变更（无前端/SSE/会话），E2E 门禁不适用
- **风险**：TTL 缓存与 `lru_cache` 行为差异（同进程内版本可见性变化）需测试覆盖；回写守护的 git 操作需限定暂存范围防止误提交无关文件
