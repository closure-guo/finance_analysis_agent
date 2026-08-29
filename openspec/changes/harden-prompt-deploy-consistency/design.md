# Design: harden-prompt-deploy-consistency

## Context

ADR-0016 的"Langfuse 优先、本地兜底"加载机制本身有正当动机（在线可调、eval 闭环、多环境），但实现把"谁权威"留成模糊地带，且发布无门禁——2026-08-25 实测 Langfuse 停留在 ver=1（无 evidence_refs）而本地已是新版，两轮 eval 全测旧 prompt。本 delta 不推翻加载机制，而是把"权威源"与"发布门禁"显式化：**Git 里的本地 .md 是唯一权威源，Langfuse 只是部署产物快照**。

## Goals / Non-Goals

**Goals**
- 发布脚本从 tests/ 提为 scripts/deploy_prompts.py（正式部署入口）
- eval 前置校验：Langfuse production 版本 vs 本地 .md 逐字一致，不一致拒绝跑
- AGENTS.md 声明权威源 + 发布约定

**Non-Goals**
- 不改变加载机制（仍 Langfuse 优先，改动过大且破坏 eval 闭环）
- 不把 Langfuse 反转为唯一权威（破坏"测试不依赖外部服务"现状）
- 不自动发布（发布仍是显式动作，只是加门禁强制）

## Decisions

### D1: 迁移而非新建（git mv 保历史）

`tests/scripts/import_prompts_to_langfuse.py` → `scripts/deploy_prompts.py` 用 `git mv`（保留文件历史），函数/参数不动，仅更新 docstring 指向正式位置。docs 引用同步改。

### D2: 门禁 = 逐字文本比对，而非版本号比对

校验 Langfuse production 返回的 text 与本地 .md 文本逐字节一致，**不比对版本号**——版本号不可靠（同一 prompt 可能被反复 create 出多个版本，production label 才指向当前；且 get_prompt 缓存可能滞后）。文本一致即认为已同步。

- 备选：比对 prompt_version。否决：version 是数据库自增，不携带内容语义；且 load_prompt_with_meta 的 Langfuse 版本可能因缓存/标签指向不一致产生误报。

### D3: 门禁失败 = 拒绝运行（非 WARN）

eval 是"产出可对比分数"的严肃流程，测错版本比拒绝更有害（浪费 1 小时 + 污染基线表）。故不一致时 sys.exit 非零，列出差异 prompt 名并指向发布命令。

### D4: 门禁实现为其独立 helper，可单测

`evals/run.py` 新增 `_verify_prompt_sync(client) -> list[str]`（返回不一致的 prompt 名列表；用本地文件文本对照 `client.get_prompt(name)` 文本）。main() 在 `prompt_versions` 收集后调用，非空则退出。测试 mock `client.get_prompt` 与局部文件（tmp 修改）断言两种情况。

## Risks / Trade-offs

- [Langfuse 短暂不可达时 eval 被误拦] → 门禁与 run_experiment 同依赖 Langfuse；不可达时现有"无 Langfuse 显式报错"已覆盖，门禁不改变该语义（D2 的 get_prompt 失败同样走报错）
- [文本比对含空白/换行差异误报（CRLF/LF）] → 比对前统一 `\r\n`→`\n` 归一化；发布脚本写入 Langfuse 的 text 与本地文件同源，仅行尾可能因平台差异不同
- [scripts/ 目录当前 untracked] → `scripts/` 含两个既有 eval 辅助脚本（evals_gated_run.py/observe_langfuse_experiments.py，从未跟踪）。本 delta 只把 deploy_prompts.py 加入 git，**不**顺手跟踪其余两个（YAGNI，避免范围外变更）；git add 时精确 pathspec

## Migration Plan

1. `git mv tests/scripts/import_prompts_to_langfuse.py scripts/deploy_prompts.py`（更新 docstring；保持 --dry-run/--labels/--exclude）
2. `evals/run.py` 加 `_verify_prompt_sync` helper + main 调用 + 单测
3. AGENTS.md 测试约束区补权威源声明
4. 契约/单测全绿 + ruff/mypy
5. 真机验证：故意改一个本地 .md 不发布 → eval 被拦；deploy 后再跑 → 放行
6. sync + archive

## Open Questions

- 门禁是否要包含 quick/deep/follow_up 三个模式 prompt？——包含（它们也在 _PROMPT_NAMES 里，且同属本地权威源），无例外。