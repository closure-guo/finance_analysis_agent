# 人工验证报告: add-period-key-citation-validation + add-fault-injection-regression-set + update-report-data-disclosure

**日期**: 2026-10-05
**验证人**: ZCode（自动化验证部分）+ 人工复核留待 10-09 实跑窗口
**关联 delta**: openspec/changes/add-period-key-citation-validation/、add-fault-injection-regression-set/、update-report-data-disclosure/
**E2E 门禁**: 不适用（纯后端校验器/prompt/报告拼装变更，无交互面）
**关联 issue**: #231 / #232 / #233

## 验证结果

| 验证项 | 验证方式 | 实际结果 | 通过 |
|---|---|---|---|
| 41.69% 撞车终裁（基准实例真实性） | 回查新浪源原始财报：2024-12-31 累计毛利率=41.69%、2026-03-31 单季=41.69%；中报累计 41.0%、2025Q3 单季 34.42%、2026Q2 单季 40.58% 均实证 | 数值真实撞车，两版报告（v4/v7）各自内部自洽 | ✅ |
| 消歧校验三路判定 | tests/test_citation_period_collision.py 10 用例（标记错配 FAIL / 歧义裸引 FAIL / 显式认领 PASS / 唯一锚点不误伤 / 比较型豁免 / 单季 field_ref 放行 / 无年份词降级 / 空 state 不炸） | 10/10 绿（先红后绿，TDD） | ✅ |
| 存量语料零误伤（硬验收） | citation 全家族 266 用例（r2/r4 语料在内） | 266 passed，零新增 FAIL | ✅ |
| prompt 期次标注纪律 | 契约测试 4 分析师 + 3 辩论者（7 用例先红后绿）+ 摘要生成器文案核对 | tests/test_prompt_contracts.py 70/70 绿 | ✅ |
| 歧义桶不进修复白名单 | 锁定单测（repair 分流只捡 value_mismatch） | 绿 | ✅ |
| F1 泄露回归样本守卫拒绝 | fault_regression：incident 036 实测样本 + 英文独白 + 截断变体全拒，干净反例直通 | 9/9 绿 | ✅ |
| F2 报警外露护栏 | decision dict 注入 anomalies 键不外泄 + 渲染链源码不读取 decision_price_anomalies | 绿 | ✅ |
| F3 期次撞车样本 | 消歧校验 FAIL（semantic_period_mismatch / ambiguous_value_undisambiguated），认领放行 | 绿 | ✅ |
| 行情截止声明行 | tests/nodes/test_report_freshness_line.py：有 kline 出现「行情数据截止: 2026-09-30」、无/空 kline 省略 | 3/3 绿（先红后绿） | ✅ |
| sentiment 板块口径纪律 | 契约测试（先红后绿）+ prompt 落稿 | 70/70 绿 | ✅ |
| lint / type | ruff check + ruff format --check + mypy（citation.py） | All checks passed | ✅ |

## 待人工验证（留待 2026-10-09 节后首个交易日）

1. **真实管线跑验证**：以新行情数据跑一次拓荆科技（688072）深度分析，核对——
   - 消歧校验在实战 claim 上的表现（重点观察毛利率等年报/单季并存序列的 claim 是否带期次标注，误伤率是否为零）
   - 报告头部「行情数据截止」行与实际行情日期一致
   - sentiment 成稿中板块级资金数据是否带口径标注
2. **定向重试路径实跑观察**：若实战触发 ambiguous_value_undisambiguated 桶，核对重试反馈明细与重试后标注质量（本报告只覆盖单测级）。

## 异常记录

- 无阻塞异常。实施过程中两处测试构造修正（claim.period 未对齐 field_ref、比较型 stated_value 须为差值枚举），均为测试侧问题、实现行为正确。

## 结论

[x] 静态/单测级验证全部通过，可进 PR 评审
[ ] 真实管线实跑验证留待 10-09 窗口完成后归档（archive 前置条件届时补齐）
