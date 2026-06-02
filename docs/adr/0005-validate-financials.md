# ADR-0005: Cross-Validation Before Metrics Computation

## Status: Accepted

## Context

系统从 AKShare 拉取三大报表后，直接进入指标计算（compute_metrics），没有任何数据质量校验。存在以下风险：

- AKShare 返回数据可能列错位、字段缺失、合并/母公司报表混淆
- 如果原始报表数据不一致，20 个指标、杜邦分解、红黄绿灯评分、健康度评级全部被污染
- LLM 基于错误数据生成"看起来专业"的报告，用户无法识别

现有 metrics 模块（solvency、profitability、efficiency、cashflow、dupont）全部假设数据正确，没有任何模块做数据质量校验。

## Decision

在 compute_metrics 之前插入 `validate_financials` 节点，实现 4 条勾稽校验规则：

### 规则与分级

| #   | 规则               | 公式                                                    | 级别   | 失败处理          |
| --- | ------------------ | ------------------------------------------------------- | ------ | ----------------- |
| 1   | 试算平衡           | 资产总计 = 负债合计 + 所有者权益合计                    | 硬等式 | FAIL → 短路到 END |
| 2   | 利润表内部勾稽     | 净利润 ≈ 利润总额 - 所得税费用                          | 软等式 | warning，继续     |
| 3   | 现金流量表内部勾稽 | 经营净现金流 + 投资净现金流 + 筹资净现金流 = 现金净变动 | 软等式 | warning，继续     |
| 4   | 留存收益勾稽       | 期末未分配利润 = 期初未分配利润 + 净利润 - 分红         | 软等式 | warning，继续     |

### 节点位置

```
check_cache → [fetch_data →] validate_financials → [PASS → compute_metrics | FAIL → END]
```

放在 compute_metrics 之前的原因：

- 四条规则全部只读原始三张表，不依赖任何衍生计算
- 先验数据再算指标，逻辑上更正确
- 两条路径（HIT/MISS）都在此点汇聚，校验覆盖所有数据来源

### 阈值设计

- 规则 1：相对误差 < 0.01%（浮点舍入容差）
- 规则 2-4：百分比 + 绝对值兜底，取宽松者。`max(基准值 × 5%, 固定最小值)`
- 绝对值兜底防止小公司误杀（基准值很小时百分比阈值过严）

### 终止机制

使用条件边（与 cache HIT/MISS 同模式），不修改 compute_metrics：

```python
def after_validate(state):
    if state["validation_result"] == "FAIL":
        return "__end__"
    return "compute_metrics"
```

### State 字段

- `validation_result: str` — "PASS" | "FAIL"（条件边读取，复用 cache_result 模式）
- `validation_warnings: list[str]` — 软规则告警（LLM 生成报告时可引用）

## Consequences

- 新增 1 个节点 + 1 个纯函数模块（`metrics/validate.py`），图从 11 节点变为 12 节点
- compute_metrics 无需任何修改
- 试算平衡失败时用户看到明确错误信息而非错误报告
- 软规则告警会在 LLM 上下文中体现，报告可提及数据偏差
- 阈值硬编码在 `metrics/validate.py`（与 traffic_light.py 风格一致）
