# Design: update-garp-input-period-alignment

## Approach

单点修复 `_try_garp`（nodes/compute.py）取数优先级，`calc_garp` 纯函数不动（failures 文案不变，citation-verification 的「failures 集合相等比对」契约不受影响）：

1. `_try_garp` 新增 `latest_period_snapshot: dict | None` 参数（调用点从 state 取）；负债率取数：快照 `资产负债率`（快照已按 analyst-data-sources 规范携带 `报告日`）→ 除以 100 → 判定；快照缺字段回落 `solvency.资产负债率[latest_year]`。
2. details 期次标注：`负债率_期次 = "2026-06-30中报（快照）"` 或 `"2025年报（快照缺失回落）"`；`ROE_期次 = f"{latest_year}年报"`。标注进 `calc_garp` 的 details dict（经由 data 输入透传两个新键，calc_garp 端原样挂 details——只透传不比较，保持纯函数语义边界）。
3. ROE/growth/PE 取数不变；growth 已是最新期同比（拓荆案 GARP failures 无 growth 项可证），不重复处理。
4. 报告侧零改动：GARP 结果经 context 进 LLM，判定理由更新后正文自然跟随。

## Alternatives Considered

- **方案 A：ROE 也切最新期**——不选：半年度累计 ROE 与「>15%」年度阈值不可比，切了会把年中真 GARP 股系统性误判失败（比期次过时更糟的口径错误）。
- **方案 B：calc_garp 接收期次参数做校验**——不选：把期次逻辑塞进纯比较函数污染边界；取数期次是 compute 层职责。

## Risks

- 快照资产负债率与 solvency 年报口径的字段名/单位差异（快照是百分比数值 47.85，solvency 同为百分比 64.11）——实现按同一「百分比→小数」转换，测试覆盖两种来源。
- 判定翻转的影响面：中报负债率过线的票，GARP failures 少一项——`pass` 结论可能由 False 变 True，下游 LLM 叙述与 citation 校验（GARP failures 集合比对是 claim 级，非全量断言）不受结构性影响；回归测试锁定。
