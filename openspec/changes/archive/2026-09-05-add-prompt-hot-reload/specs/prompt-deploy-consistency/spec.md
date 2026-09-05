# Delta for prompt-deploy-consistency

## MODIFIED Requirements

### Requirement: 发布脚本为正式部署工具

prompt 发布脚本 MUST 存在于正式脚本目录 `scripts/`（而非 tests/），作为"本地 .md → Langfuse production"的唯一发布入口。发布前 MUST 执行预检（pre-flight）：任一 prompt 的 Langfuse production 当前内容与本地 `.md` 不一致（CRLF/LF 行尾差异不影响判定）时 MUST 拒绝发布，并提示先执行 `scripts/sync_prompts.py --once` 收编 Langfuse 侧变更——防止本地盲推覆盖 Langfuse UI 编辑（production 标签被 deploy 抢走的事故模式）。预检不可用（Langfuse 不可达）时按现有拉取失败语义保守处理。
(Previously: prompt 发布脚本 MUST 存在于正式脚本目录 `scripts/`（而非 tests/），作为"本地 .md → Langfuse production"的唯一发布入口。无预检要求。)

#### Scenario: 发布入口在 scripts 目录

- **WHEN** 仓库被检出
- **THEN** `scripts/deploy_prompts.py` 存在
- **AND** `tests/scripts/import_prompts_to_langfuse.py` 不再存在

#### Scenario: 发布命令幂等可用

- **WHEN** 执行 `uv run python scripts/deploy_prompts.py --dry-run`
- **THEN** 打印将导入的 prompt 文件清单而不实际调用 Langfuse
- **AND** 支持 --labels（默认 production）与 --exclude 参数

#### Scenario: Langfuse 领先时拒绝发布

- **GIVEN** 某 prompt 的 Langfuse production 内容 ≠ 本地 .md（UI 已编辑未收编）
- **WHEN** 执行 `uv run python scripts/deploy_prompts.py`
- **THEN** 进程以非零退出码终止，不发布任何 prompt
- **AND** 错误信息列出不一致的 prompt 名
- **AND** 提示先执行 `uv run python scripts/sync_prompts.py --once` 收编

#### Scenario: 一致时正常发布

- **GIVEN** 全部 prompt 的 Langfuse production 与本地 .md 一致（或 Langfuse 为空/首次部署）
- **WHEN** 执行发布
- **THEN** 正常创建新版本并打 production 标签

## ADDED Requirements

### Requirement: prompt 热更新（TTL 加载）

`prompts/loader.py` MUST 以带 TTL 的进程内缓存加载 prompt（默认 30 秒）：缓存过期后重新从 Langfuse production 拉取，使 production 标签/版本变更在最迟 TTL 时长后对后续请求生效，无需重启进程。`load_prompt` / `load_prompt_with_meta` 的签名与返回结构 MUST 保持不变；`prompt_version` MUST 反映当前实际加载的版本。Langfuse 拉取失败时沿用本地兜底语义（WARN + 本地 .md），兜底结果同样参与缓存。
(背景: 原实现为 @lru_cache 进程内永久缓存，换版本需重启进程。)

#### Scenario: production 切换后 TTL 内生效

- **GIVEN** 进程已加载某 prompt 的 v1（production 标签当时指向 v1）
- **WHEN** Langfuse UI 将 production 切到 v2，且等待超过 TTL 时长
- **THEN** 后续 `load_prompt` 返回 v2 内容
- **AND** `load_prompt_with_meta().prompt_version` 为 2

#### Scenario: TTL 内仍用缓存

- **GIVEN** 刚加载过某 prompt（距上次拉取 < TTL）
- **WHEN** Langfuse 侧立即切换 production
- **THEN** TTL 窗口内 `load_prompt` 仍返回旧版本内容（可接受的收敛延迟）

#### Scenario: 拉取失败回退本地

- **GIVEN** Langfuse 不可达
- **WHEN** 缓存过期后加载 prompt
- **THEN** 回退本地 .md 内容并记 WARN
- **AND** 不抛异常中断调用方

### Requirement: Langfuse 变更自动回写收编

系统 SHALL 提供收编脚本 `scripts/sync_prompts.py`（`--watch` 守护模式 / `--once` 单次模式 / `--dry-run`）：检测每个 prompt 的 Langfuse production 内容与本地 `.md` 不一致（CRLF/LF 归一比对，口径同 eval 门禁）时，将 Langfuse 内容写回本地 `.md` 并以 git 提交（仅暂存发生变化的 prompt 文件，提交信息注明来源 prompt 名与版本）。本地 prompt 文件存在**未提交的手工改动**时 MUST 不覆盖、仅告警并要求人工裁决（冲突保护）。回写守护设计为在 git 仓库所在宿主机运行（容器内 .md 为镜像层，回写不持久）。
(背景: 发布原为单向 本地→Langfuse，UI 编辑不在 git，下次 deploy 即被覆盖——用户实际遭遇 deep_mode v2 被 deploy 抢走 production。)

#### Scenario: 检测到 UI 编辑并自动收编

- **GIVEN** 用户在 Langfuse UI 编辑某 prompt 并设为 production，本地 .md 为旧内容且无未提交改动
- **WHEN** 运行 `sync_prompts.py --once`（或守护周期到达）
- **THEN** 本地 .md 被写回 production 内容
- **AND** 产生仅含该 prompt 文件的 git 提交
- **AND** 提交信息注明 prompt 名与收编来源版本

#### Scenario: 本地有未提交改动时冲突保护

- **GIVEN** 本地某 prompt .md 有未提交的手工编辑，Langfuse production 亦为不同内容
- **WHEN** 运行收编
- **THEN** 不覆盖本地文件
- **AND** 告警列出冲突 prompt 名并要求人工裁决

#### Scenario: 一致时空操作

- **GIVEN** 全部 prompt 的 production 与本地一致
- **WHEN** 运行收编
- **THEN** 不写文件、不产生提交，输出一致报告

#### Scenario: 干跑只报告不落盘

- **WHEN** 运行 `sync_prompts.py --dry-run`
- **THEN** 仅打印将收编的 prompt 清单与差异摘要，不写文件、不提交
