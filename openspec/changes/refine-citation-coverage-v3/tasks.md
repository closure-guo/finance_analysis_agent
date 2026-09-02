# Tasks: refine-citation-coverage-v3

> 粗粒度验收 checklist。细粒度 TDD 步骤由 writing-plans 产出，不在此处。

## 1. 普查规则修正（D1，issue #106，核心交付）

- [x] 1.1 普查容差独立化为 2%（相对）+ 0.01 下限（CENSUS_TOL + _census_close，fixture 钉死）
- [x] 1.2 方向词语境符号不敏感匹配（_DIRECTION_WORDS ±20 字符，CensusNumber.direction_neg）
- [x] 1.3 不等式匹配（ge/le/approx；自然面值 + 20% 邻域带防跨指标误认领）
- [x] 1.4 模板/脚手架文本区间排除（_SCAFFOLD_HINTS：档位/仓位/如总资金/试探性/决策语义）
- [x] 1.5 事件数字标记 event_covered（compute_coverage event_values 参数 + CoverageReport.event_covered 字段）
- [ ] 1.6 用同一批冒烟 trace 重跑 spotcheck（需从 Langfuse trace 重建完整报告 markdown 后跑新 compute_coverage；抽样材料生成器同步 v3 分类；待集成验证）

## 2. state anomalies 自动补登记（D2，issue #107-B，核心交付）

- [x] 2.1 双条件共现匹配（supplement_anomaly_claims：指标名同句 ∧ 数值 0.5pp 容差）
- [x] 2.2 field_ref 指向 growth_rates.{dim}.{metric} 结构化真值，anomaly 字符串只定位不验证
- [x] 2.3 反洗白：state 无真值（growth_rates 缺键）/双条件不满足 → 不补登记，保持 unmatched
- [x] 2.4 补登记 claim 并入 verify_claims（anomaly_supplement 伪代理），同路径校验；取整 0.5pp 误差被 ABS_TOL=0.01 覆盖（测试钉死）
- [x] 2.5 自动补登记单元测试 5 例（共现/反洗白/去重/标准校验 PASS）

## 3. comparative 基期值双端建档（D3，issue #107-C）

- [x] 3.1 Claim comparative 基期校验（stated_value_b 缺失 → FAIL path_unresolvable；超容差 → FAIL value_mismatch）
- [x] 3.2 analysts prompt 强制比较值双端申报（fundamental/macro/technical 已加规则）+ deploy_prompts 发布 14 全 OK
- [x] 3.3 基期值校验走与当期相同容差语义（max(0.01, 0.5%)）；测试钉死（正确 PASS / 错值 FAIL / 缺申报 FAIL）

## 4. 可重算计算值补登记（D4，issue #107-D）

- [x] 4.1 增速类计算值补登记（D2 吸收）：supplement 源头从 anomalies 扩到整个 growth_rates——FCF 同比 96.6% 类即使非 anomaly 也补（数值 0.5pp 容差 ∧ 指标名共现）
- [x] 4.2 补登记 claim 走标准校验路径（stated=0.97 vs truth=0.966 取整容差 PASS 已测）；不可定位结构化真值不补

## 5. 验证与回归

- [ ] 5.1 `uv run pytest -m "not live"`、ruff、mypy（任务范围）全绿
- [ ] 5.2 openspec validate <change-id> --strict 通过
- [x] 5.3 v3 效应实证（对 20 条抽查逐条模拟新普查）：E/F 类 8 条全部认领；A 类脚手架被普查排除、G 类走 event_covered（单元测试已证）；剩余 unmatched 收敛到 8 条真缺口（B/C/D + 1400亿），正是 reject 补 claim 集——目标达成
