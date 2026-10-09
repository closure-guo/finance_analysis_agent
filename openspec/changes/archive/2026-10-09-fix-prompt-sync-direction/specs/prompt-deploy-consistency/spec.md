# Delta for Prompt Deploy Consistency

## MODIFIED Requirements

### Requirement: 发布脚本为正式部署工具

prompt 发布脚本 MUST 存在于正式脚本目录 `scripts/`（而非 tests/），作为"本地 .md → Langfuse production"的唯一发布入口。发布前 MUST 执行预检（pre-flight），按方向三分支判别（CRLF/LF 行尾差异不影响判定）：

- **一致**：Langfuse production == 本地 `.md` → 放行（主循环跳过同内容重发布，防版本噪声）；
- **本地领先 / Langfuse 落后**：remote == HEAD，或 remote 命中该文件 git 历史任一已提交版本（纯陈旧/回退、无 UI 独有内容）→ 放行；命中历史但 ≠ HEAD 时 MUST 在输出标注「Langfuse 落后/回退，发布将覆盖」；
- **Langfuse 领先**：remote 既不 == 本地也不命中任何历史版本（UI 独有编辑未收编）→ MUST 拒绝发布，错误信息列出不一致的 prompt 名并提示先执行 `scripts/sync_prompts.py --once` 收编——防止本地盲推覆盖 Langfuse UI 编辑（production 标签被 deploy 抢走的事故模式）。

`--force` 显式覆盖通道 MUST 存在：携带时绕过「Langfuse 领先」拦截并逐项打印被覆盖 prompt 的警告；拉取失败（网络/凭证）不属于可覆盖项，仍 MUST 保守拒绝。HEAD 内容未知（未跟踪/无 git）时按保守语义处理：历史版本集为空，任何 remote ≠ local 的差异一律拒绝。

(Previously: prompt 发布脚本 MUST 存在于正式脚本目录 `scripts/`（而非 tests/），作为"本地 .md → Langfuse production"的唯一发布入口。发布前 MUST 执行预检（pre-flight）：任一 prompt 的 Langfuse production 当前内容与本地 `.md` 不一致（CRLF/LF 行尾差异不影响判定）时 MUST 拒绝发布，并提示先执行 `scripts/sync_prompts.py --once` 收编 Langfuse 侧变更——防止本地盲推覆盖 Langfuse UI 编辑（production 标签被 deploy 抢走的事故模式）。预检不可用（Langfuse 不可达）时按现有拉取失败语义保守处理。)

#### Scenario: 发布入口在 scripts 目录

- **WHEN** 仓库被检出
- **THEN** `scripts/deploy_prompts.py` 存在
- **AND** `tests/scripts/import_prompts_to_langfuse.py` 不再存在

#### Scenario: 发布命令幂等可用

- **WHEN** 执行 `uv run python scripts/deploy_prompts.py --dry-run`
- **THEN** 打印将导入的 prompt 文件清单而不实际调用 Langfuse
- **AND** 支持 --labels（默认 production）与 --exclude 参数

#### Scenario: Langfuse 领先时拒绝发布

- **GIVEN** 某 prompt 的 Langfuse production 内容 ≠ 本地 .md，且不命中该文件任何 git 历史已提交版本（UI 独有编辑未收编）
- **WHEN** 执行 `uv run python scripts/deploy_prompts.py`
- **THEN** 进程以非零退出码终止，不发布任何 prompt
- **AND** 错误信息列出不一致的 prompt 名
- **AND** 提示先执行 `uv run python scripts/sync_prompts.py --once` 收编

#### Scenario: Langfuse 回退/落后时放行并标注

- **GIVEN** 某 prompt 的 Langfuse production 内容 ≠ 本地 .md，但 == 该文件某一 git 历史已提交版本（回退或纯陈旧，无 UI 独有内容）
- **WHEN** 执行 `uv run python scripts/deploy_prompts.py`
- **THEN** 预检放行，正常发布
- **AND** 输出标注该 prompt 为「Langfuse 落后/回退，发布将覆盖」

#### Scenario: --force 显式覆盖 UI 编辑

- **GIVEN** 某 prompt 的 Langfuse production 含 UI 独有内容（预检判定 Langfuse 领先）
- **WHEN** 执行 `uv run python scripts/deploy_prompts.py --force`
- **THEN** 逐项打印「将被覆盖」警告后继续发布
- **AND** 拉取失败的 prompt 不在覆盖之列，仍按不可达保守拒绝

#### Scenario: 一致时正常发布

- **GIVEN** 全部 prompt 的 Langfuse production 与本地 .md 一致（或 Langfuse 为空/首次部署）
- **WHEN** 执行发布
- **THEN** 正常创建新版本并打 production 标签

### Requirement: Langfuse 变更自动回写收编

系统 SHALL 提供收编脚本 `scripts/sync_prompts.py`（`--watch` 守护模式 / `--once` 单次模式 / `--dry-run`）：检测每个 prompt 的 Langfuse production 内容与本地 `.md` 不一致（CRLF/LF 归一比对，口径同 eval 门禁）时，先做**方向判别**——remote 命中该文件 git 历史任一已提交版本（Langfuse 回退/落后，无 UI 独有内容）时 MUST 不写回不提交，标注为回退并提示改用 `deploy_prompts.py` 发布覆盖，且进程以非零退出码结束；仅当 remote 为 UI 独有内容（不命中任何历史版本）时才收编：将 Langfuse 内容写回本地 `.md` 并以 git 提交（仅暂存发生变化的 prompt 文件，提交信息注明来源 prompt 名与版本）。本地 prompt 文件存在**未提交的手工改动**时 MUST 不覆盖、仅告警并要求人工裁决（冲突保护）。回写守护设计为在 git 仓库所在宿主机运行（容器内 .md 为镜像层，回写不持久）。

(背景: 发布原为单向 本地→Langfuse，UI 编辑不在 git，下次 deploy 即被覆盖——用户实际遭遇 deep_mode v2 被 deploy 抢走 production。2026-10-05 又实证反方向事故：Langfuse 被回退到历史版本，sync 把回退内容当 UI 编辑收编进仓库（issue #228）。)

(Previously: 系统 SHALL 提供收编脚本 `scripts/sync_prompts.py`（`--watch` 守护模式 / `--once` 单次模式 / `--dry-run`）：检测每个 prompt 的 Langfuse production 内容与本地 `.md` 不一致（CRLF/LF 归一比对，口径同 eval 门禁）时，将 Langfuse 内容写回本地 `.md` 并以 git 提交（仅暂存发生变化的 prompt 文件，提交信息注明来源 prompt 名与版本）。本地 prompt 文件存在**未提交的手工改动**时 MUST 不覆盖、仅告警并要求人工裁决（冲突保护）。回写守护设计为在 git 仓库所在宿主机运行（容器内 .md 为镜像层，回写不持久）。)

#### Scenario: 检测到 UI 编辑并自动收编

- **GIVEN** 用户在 Langfuse UI 编辑某 prompt 并设为 production（内容不命中任何 git 历史版本），本地 .md 为旧内容且无未提交改动
- **WHEN** 运行 `sync_prompts.py --once`（或守护周期到达）
- **THEN** 本地 .md 被写回 production 内容
- **AND** 产生仅含该 prompt 文件的 git 提交
- **AND** 提交信息注明 prompt 名与收编来源版本

#### Scenario: Langfuse 回退到历史版本时拒绝收编

- **GIVEN** 某 prompt 的 Langfuse production 内容 == 该文件某一 git 历史已提交版本（回退/纯陈旧），本地 .md 为较新内容
- **WHEN** 运行 `sync_prompts.py --once`
- **THEN** 不写回本地文件、不产生提交
- **AND** 输出标注该 prompt 为「Langfuse 回退/落后」并提示改用 `scripts/deploy_prompts.py` 发布覆盖
- **AND** 进程以非零退出码结束

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
