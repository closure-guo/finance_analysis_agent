# require-trade-price-declaration 人工验证报告（2026-09-14）

## 背景与根因

连续 4 轮真实运行（round8 E2E 3/3、round9 宁德 buy）trader 从不申报数值价位（entry/stop/target 全 null）。根因：`validate.py` 对 buy/sell 价位缺失**静默 pass**（「schema 可选，跳过校验」），trader 无任何反馈压力；derived_metrics（止损距离/赔率）真实数据路径因此从未激活。

## 修复内容

1. **validate 收紧**（`nodes/validate.py`）：buy/sell 三价任一缺失（None/≤0/非数值）→ price_check **fail 打回一次**（feedback 列明缺失项、要求申报）；已打回仍缺失 → 放行 + note「已打回仍未申报」（不进参考带修正路径——缺失无数值可修；报告「未提供」兜底不变）。
2. **派生指标与 band 校验解耦**：派生指标只依赖申报价格——price_levels 不可用/行情缺失跳过 band 校验时**照常计算**（E2E 首跑发现的缺口：早退分支漏算导致辩论拿不到代码值，已修复）。
3. **prompt 契约**：trader.md「buy/sell MUST 申报三价数值，禁止 null/0」；risk_judge.md「维持 buy/sell 方向 MUST 继承价位（可调数值，不得置 null）」。已 deploy（14 导入）。

## 验证证据

### 单元测试（30 个，全绿）

- `TestPriceDeclarationRequired`（5）：buy 三价全缺 fail+缺失清单；部分缺失只列缺失项；sell 0 计缺失（比亚迪形态）；二次仍缺失放行+note+attempts 不递增；watch 直通不变
- `TestDerivedMetrics` 增 2：price_levels 不可用 / kline 缺失时派生指标照常计算
- 既有价位校验/修正/路由测试无回归

### 真实运行（graph.invoke 全管线，LLM 真调用）

| 运行 | 标的 | 结果 | 关键证据 |
|---|---|---|---|
| 1 | 300750 宁德 | watch | watch 直通正确（无价位要求，不误打回） |
| 2 | 601318 平安 | **buy** | **trader 首次申报三价 57.5/52.5/68.0**；报告渲染入场/止损/目标/派生指标行（8.7%、2.10:1）；发现派生早退缺口（当轮修复） |
| 3 | 601318 平安（修复后） | **buy** | **完整闭环**：trader 申报 62.0/57.0/74.0 → 派生 8.1%、2.40:1（代码计算）→ **风险辩论三方两轮 6/6 mentions=True 同源引用**（激进方「低beta应重仓」被用代码值反驳）→ RJ 理由明写「均为代码派生值，直接引用」→ 报告参数行完整渲染 |

原始记录：`tests/validation/delta-e2e-验证记录.md`（2026-09-13/14 各条目）。

## 指标定义对齐说明

连续 4 轮 0 申报的口径：round8 E2E 3 次 + round9 实验 9 条 deep（含宁德 buy 三价全 null）。本次验证后该口径闭合：价位申报率从 0/4 轮 → 2/2 次 buy 决策申报（prompt 契约 + 打回威慑）。

## 残余事项

- 打回路径（trader 首次不申报 → fail → 补报）在真实运行中未触发（prompt 契约生效后首轮即申报），由单元测试覆盖；后续真实运行若触发属正常修正回路。
- price_levels 参考带在直连 graph.invoke 场景不可用（E2E 走本地无 API server），band 校验路径由单元测试覆盖；docker 后端全栈场景下照常工作。

## 结论

可验证范围全部通过：价位申报契约生效（0/4 → 2/2）、fail 打回机制就位、派生指标真实数据路径激活（辩论 6/6 同源引用）、报告 buy+真实价位渲染完整。delta 达到归档条件。
