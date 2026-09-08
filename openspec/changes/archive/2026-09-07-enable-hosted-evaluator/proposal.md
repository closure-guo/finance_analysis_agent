# Proposal: enable-hosted-evaluator

## Why

Langfuse 平台自带的 LLM-as-a-judge evaluator 可以在 trace 到达时近实时打分，目前完全未启用——所有评分都靠离线评测脚本跑，意味着生产流量的真实质量没有任何在线监控。离线评测（固定样本集）与在线评估（真实流量）是互补关系，缺后者就无法发现「样本集没覆盖到的真实劣化」。

## What Changes

- 启用 Langfuse managed evaluator：对生产 trace 配置采样率（如 10%）+ judge 模板，维度对齐离线评测口径
- 分数回流：hosted 评分与离线评分入同一分数命名空间，看板可分来源对比
- 口径对齐验证：抽样比对 hosted vs 离线 judge 对同一 trace 的打分差异（防止两套裁判各说各话）
- 告警：hosted 均分跌破阈值时告警（Langfuse webhook 或轮询脚本）
- 治理：evaluator 配置纳入版本管理（模板即 prompt，走 prompt-deploy-consistency 同类纪律）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `agent-evaluation-suite`: 新增在线评估回路（hosted evaluator 配置、口径对齐验证、告警）

## Impact

- 依赖：Langfuse 部署版本需支持 managed evaluator（需先确认自托管版本能力，不支持则降级为轮询脚本方案）
- 成本：在线 judge 调用按采样率产生额外 LLM 费用——采样率配置化
- 与 add-judge-human-calibration 协同：hosted judge 也纳入人工校准范围
