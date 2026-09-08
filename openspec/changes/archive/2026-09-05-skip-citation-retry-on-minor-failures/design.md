# Design: skip-citation-retry-on-minor-failures

## Approach

`after_citation`（`routing.py`）在「PASS → render / FAIL 重试」判定前插入轻微失败分支：

```
if citation_pass:              → render          （既有）
elif fail_count <= 1 and fail_rate <= 0.05: → render + 降级标记（新增）
elif iteration_count < 3 且停滞:             → render + 降级标记（既有）
else:                        → retry          （既有）
```

fail_count / fail_rate 已在 `citation_node.py::verify_citations` 计算并随 state 传递（`citation_fail_rates`），路由侧无需新增计算。标记复用 `update_current_span` 的 WARNING 通道（与既有停滞降级一致，字段如 `citation_minor_fail_deescalated: True`）。

阈值依据（incident 022 验证数据）：汉森/茅台单点 FAIL=1（2.2%）→ 本 delta 后免重试；中际旭创 FAIL=13（54.2%）→ 仍重试。默认 `FAIL ≤ 1 且 ≤5%` 为保守下限，后续可据跑批数据调参（不设可配置项，先硬编码常量）。

## Alternatives Considered

- **方案 A：硬编码阈值（selected）**：确定性、可测试、随 spec 演进；避免配置面扩大。
- **方案 B：按 fail_rate 单阈值（≤5%）**：不选——FAIL=3/60（5%）也被免，可能放过多；双条件更贴合「单点/近零失败」语义。
- **方案 C：等停滞降级首轮生效**：不可行——停滞判定需要前一轮失败率历史，首轮天然无历史，永远保护不了首轮。

## Risks

- 轻微失败里可能混入「该拦的真幻觉」（如 1 条编造数值）。本 delta 放行后报告仍携带该 FAIL（渲染不删 claim），由 incident 020 遗留 #2（prompt 端防幻觉）另行治理——不因噎废食；
- 阈值调节随时间漂移：跑批数据积累后若发现 ≥2 条 FAIL 也值得免重试，另提 delta 调整，本 delta 用保守下限冻结。