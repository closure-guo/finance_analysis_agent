# hosted evaluator 模板快照（enable-hosted-evaluator 降级治理）

> 背景（2026-09-04 取证）：自托管 Langfuse 3.205.1 无 evaluator 公共 API，
> managed evaluator 仅能 UI 配置、无法脚本化/版本化。本文件是模板的**手工快照**：
> 每次在 Langfuse UI 修改 evaluator 配置后，回填此文件（等效 prompt-deploy 纪律）。

## 状态

- [ ] 尚未在 UI 配置 evaluator（采样率默认建议 10%，维度对齐离线四维：
      report_relevance / debate_quality / decision_grounding / consistency）

## 快照（配置后回填）

```yaml
# name: <evaluator 名>
# configId: <UI 中的 config id，轮询脚本 --config-id 用>
# 采样率: 10%
# 模板（prompt）:
#   <在此粘贴 UI 中的 judge 模板全文>
# 模型: <judge 使用的模型>
```

## 口径对齐

- hosted 分数与离线 judge 对同一 trace 的打分 MAE 阈值 ≤ 1.0
- 超阈值 → 统一口径（以人工校准结论为准，见 add-judge-human-calibration）
