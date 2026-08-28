# Prompt Deploy Consistency

## Purpose

定义提示词"本地权威源 → Langfuse 部署产物"的一致性契约。ADR-0016 的加载机制（Langfuse 优先、本地兜底）在实现上曾出现静默漂移：Langfuse 停留旧版本而本地已是新版，两轮 eval 全测旧 prompt 跑完才发现。本 capability 通过"发布工具正式化 + eval 前置版本一致性门禁 + 权威源声明"把漂移从静默变为显式拦截。

## Requirements

### Requirement: 发布脚本为正式部署工具

prompt 发布脚本 MUST 存在于正式脚本目录 `scripts/`（而非 tests/），作为"本地 .md → Langfuse production"的唯一发布入口。

#### Scenario: 发布入口在 scripts 目录

- **WHEN** 仓库被检出
- **THEN** `scripts/deploy_prompts.py` 存在
- **AND** `tests/scripts/import_prompts_to_langfuse.py` 不再存在

#### Scenario: 发布命令幂等可用

- **WHEN** 执行 `uv run python scripts/deploy_prompts.py --dry-run`
- **THEN** 打印将导入的 prompt 文件清单而不实际调用 Langfuse
- **AND** 支持 --labels（默认 production）与 --exclude 参数

### Requirement: eval 前置版本一致性门禁

`evals.run` 模块 MUST 在 run_experiment 执行前校验每个 prompt 的 Langfuse 当前版本（运行时将加载的版本）与本地 `prompts/*.md` 内容一致；任一不一致 MUST 拒绝运行并列出差异项。

#### Scenario: 版本一致时放行

- **GIVEN** Langfuse 上每个 prompt 的文本与本地对应 .md 逐字一致（CRLF/LF 行尾差异不影响判定）
- **WHEN** 运行 `uv run python -m evals.run "<实验名>"`
- **THEN** 实验正常执行（门禁通过）

#### Scenario: 版本不一致时拒绝

- **GIVEN** 至少一个 prompt 的 Langfuse 文本与本地 .md 不一致（如本地已改未发布）
- **WHEN** 运行 `uv run python -m evals.run "<实验名>"`
- **THEN** 进程以非零退出码终止
- **AND** 错误信息列出每个不一致的 prompt 名
- **AND** 提示先执行 `scripts/deploy_prompts.py` 发布

#### Scenario: Langfuse 拉取失败时保守拦截

- **GIVEN** 至少一个 prompt 的 get_prompt 调用抛异常（网络/凭证问题）
- **WHEN** 运行 eval
- **THEN** 该 prompt 被标记为不一致（名称附"拉取失败"标注）
- **AND** 全部为拉取失败时提示检查 Langfuse 连通性/凭证

#### Scenario: 未配置 Langfuse 时门禁跳过

- **GIVEN** Langfuse 未配置（无 key 或不可达）
- **WHEN** 运行 eval
- **THEN** 沿用现有行为（显式报错退出，见 spec「实验回归工作流」Scenario「无 Langfuse 时显式报错」）

### Requirement: AGENTS.md 权威源声明

AGENTS.md 测试约束区 MUST 声明：本地 `prompts/*.md`（git 跟踪）是提示词唯一权威源，Langfuse 是部署产物快照；修改提示词后必须同步发布。

#### Scenario: 文档声明存在

- **WHEN** 阅读 AGENTS.md 测试约束区
- **THEN** 找到"本地 prompts/*.md 是唯一权威源，Langfuse 为部署产物；改 prompt 后须用 scripts/deploy_prompts.py 发布"类表述
- **AND** 表述中指明发布命令路径