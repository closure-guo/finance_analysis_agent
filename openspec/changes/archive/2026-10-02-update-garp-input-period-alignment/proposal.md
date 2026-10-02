# Proposal: update-garp-input-period-alignment

## Why

第三轮评审（2026-10-02 拓荆 688072 第三版报告）发现：报告正文已按最新期次成对标注负债率（「2025年64.11%（黄灯），但2026中报已降至47.85%」），但 GARP 判定仍挂年报口径——`GARP检验不通过（负债率≥60%）` 引用的是 64.11%。规则引擎判定与正文期次自相矛盾：负债率是**时点值**（最新披露期才反映当前偿债状态），且中报定增到账后 47.85% 已低于 60% 阈值，该 failure 项不该再出现。根因：`_try_garp` 的 debt_ratio 取 `latest_year`（最新年报）键，spec 从未规定 GARP 输入期次（快照通道 analyst-data-sources 只覆盖 LLM 上下文，valuation-signal-integrity 只覆盖缺失分桶与 PE_ttm 推导）。

## What Changes

- **负债率输入期次对齐**：GARP 的 debt_ratio SHALL 优先取 `latest_period_snapshot.资产负债率`（最新披露报告期期末值——时点指标用最新时点）；快照缺失/字段缺失时回落年报口径并标注期次
- **期次来源标注**：GARP details SHALL 栰注负债率与 ROE 的期次来源（`负债率_期次`/`ROE_期次`），可观测、可对账
- **ROE 保持全年口径（显式声明）**：ROE>15% 阈值是全年化语义，半年度累计 ROE 与年报不可直接比较——ROE 维持 `latest_year` 取值，但 details 标注期次，正文引用时口径可见

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `valuation-signal-integrity`: 「估值输入缺失诚实分桶」requirement 同级新增 GARP 输入期次对齐要求（负债率最新披露期优先 + 期次标注 + ROE 全年口径显式化）

## Impact

- `src/finance_agent/nodes/compute.py`：`_try_garp` 新增 `latest_period_snapshot` 参数，负债率取数优先级改为「快照 → 年报回落」；details 增期次键
- `tests/nodes/test_compute_valuation.py`：新增期次对齐用例（快照有值/快照缺失回落/期次标注）
- 报告正文无需改动：GARP 结果进 LLM context，判定理由更新后叙述自然跟随
- 非交互类变更 → 不适用 E2E 门禁
