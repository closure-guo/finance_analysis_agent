# Proposal: add-fault-injection-regression-set

## Why

七轮人工评审（拓荆 688072，2026-10-04 至 10-05）暴露的故障样本目前散落在单测与评审记录里，没有统一的可执行回归集。每次改 prompt、换模型、升级校验器后，同类故障（推理泄露、报警外露、期次错位）只能靠再跑一轮人工评审兜底。把已修复故障固化为确定性零 token 回归集，评审循环的大部分质量拦截可以自动化（issue #232）。

## What Changes

- 新增 `tests/regression/fault_injection/` 回归集：三组真实故障样本 + 断言守卫拒绝
  - F1 推理泄露（v5）：英文残留/思考文本/截断样本，断言 `output_guard.validate_deliverable_text` 全拒（收编既有 incident 036 单测样本并扩充）
  - F2 报警外露（v2）：构造带 `decision_price_anomalies` 的 state 走报告渲染，断言成稿不含价位报警文案（护栏：渲染链若回退为接收 anomalies 即红）
  - F3 期次错位（v1/41.69% 撞车）：撞车 claim 样本，断言消歧校验 FAIL（依赖 add-period-key-citation-validation 落地）
- pytest marker `fault_regression` + CI 独立步骤（确定性、零 token、秒级）
- README 说明运行方式与样本来源（每样本标注故障版本与修复 PR）

## Capabilities

- **New Capabilities**: 无（挂靠 `agent-evaluation-suite` 追加回归门禁 Requirement）

## Impact

- `tests/regression/fault_injection/`（新增目录）、`pyproject.toml`（marker 注册）、`.github/workflows/ci.yml`（新步骤）
- 依赖 add-period-key-citation-validation 先落地（F3 样本）；F1/F2 独立可先行
- 已知限制：模型供应商侧变更（不经 PR 的 .env 切换）不在 CI 覆盖内
