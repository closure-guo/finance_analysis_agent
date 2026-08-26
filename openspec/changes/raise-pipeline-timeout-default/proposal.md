# Proposal: raise-pipeline-timeout-default

## Why

墙钟超时（`PIPELINE_TIMEOUT_SECONDS`，ReAct 与 fast path 均按管线启动起算的
全局预算）默认 600s 与当前 LLM 端点（方舟 GLM-5.3）的耗时方差不匹配——实测
同一节点的单次生成耗时在 3.7~15.7 分钟之间浮动，四分析师并行时 R1 单轮即可
达 ~16 分钟，R1+R2 合法双轮最坏 ~32 分钟。默认 600s 会把「合理但偏慢」的
分析误判为超时（2026-08-26 天力锂能 301152 复现；601700 亦曾触发）。超时
本身按设计和正确工作（研判超时原因、置 failed、Agent 转述），但默认值应匹配
合法执行包络而非紧贴最坏单轮。

## What Changes

- 默认预算 600s（10 分钟）→ 2400s（40 分钟），覆盖合法 R1+R2 双轮最坏包络
  并留余量；环境变量 `PIPELINE_TIMEOUT_SECONDS` 仍可覆盖，语义不变
  （自管线启动起算的全局墙钟预算，耗尽即终止并置 failed + failure_reason）。
- 复盘追加（2026-08-26 晚）：2400s 默认下汉森制药仍两度误伤（端点单次生成
  12~16 分钟），用户决策在本部署显式禁用超时——`PIPELINE_TIMEOUT_SECONDS=0`
  表示不限时长（不判 failed、不终止），默认安全网仅在未禁用时生效；
  docker-compose 后端环境置 0 落地该决策。

## Capabilities

- **Modified Capabilities**: `pipeline-events`（管线超时与中断检测的默认值）
- **New Capabilities**: 无

## Impact

- `src/finance_agent/pipeline_runner.py`、`src/finance_agent/agent_factory.py`
  默认值常量化（共享 `PIPELINE_TIMEOUT_DEFAULT_SECONDS`）
- 既有 600s 部署如需收紧，仍可用环境变量覆盖，不破坏私有化配置