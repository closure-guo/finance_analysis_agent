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
- **全量回归暴露两处消歧误伤，已修正并回写 spec/design**（「构造场景让位于实证语料」）：
  1. claim_benchmark 合成语料（state_v1 资产负债率 2022/2024 合成撞车 40.0 + 空 interpretation 旧格式 claim）被消歧义务误判 FAIL → 新增降级边界「interpretation 为空跳过消歧」（与 metric_name/period 未申报降级先例一致）；
  2. 002412 rejudge 真实语料「自2021年4.30次缓慢下行」历史参照表述被认领检查误拦 → 判定语义收敛为「认领检查仅撞车档（锚点基数≥2）生效」，唯一锚点期次表述自由。
  修正后：碰撞单测 11/11、citation 全家族 266、benchmark/rejudge 27 全绿。

## 结论

[x] 静态/单测级验证全部通过（含全量回归 5 失败归因修复），可进 PR 评审
[ ] 真实管线实跑验证留待 10-09 窗口完成后归档（archive 前置条件届时补齐）

---

## 10-09 窗口补验（2026-10-09 13:50 真实管线跑批，session `8bc9b9a9-a66` 拓荆科技 688072）

> 背景：本报告原结论行「实跑验证留待 10-09 窗口完成后归档」——归档（PR #270）先于窗口执行，本节为欠账补录（issue #269 勘误承诺）。跑批日志：`2026-10-09-fa-run-688072-sse.txt`。

| 待验证项 | 实测 | 通过 |
|---|---|---|
| ① 行情数据截止行实际呈现 | 报告头部「行情数据截止: 2026-10-08」（10-09 盘中跑批，当日 K 未收盘不纳入——顺延语义正确） | ✅ |
| ① 资金流口径显式化 | 舆情节「板块口径风险信号：10月8日…主力资金净流出」——板块/个股口径显式区分 | ✅ |
| ② 消歧实战表现 | `anomalies=[]`——ambiguous_value_undisambiguated 桶本跑未触发；报告期次标注抽查无错配（条款为条件触发核对，未触发=无异常可核） | ✅（未触发） |
| ③ 滞回/触发器/快照协同 | watch 决策落均衡带内（置信度 58%），inaction_reason + 再评估触发条件渲染齐备，观点入池 open + T+20 窗口，三处触发位一致（688.5/570） | ✅ |

## 结论（补录后更新）

- [x] 静态/单测级验证全部通过（含全量回归 5 失败归因修复），可进 PR 评审
- [x] 真实管线实跑验证 10-09 窗口已完成（本节），archive 前置条件补齐
