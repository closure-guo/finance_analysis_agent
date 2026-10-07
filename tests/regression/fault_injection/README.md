# 故障注入回归集（fault injection regression set）

七轮人工评审（拓荆 688072，2026-10-04 至 10-05）暴露的真实故障样本固化。
**每次改 prompt、换模型、升级校验器之后先跑本回归集再上线**；守卫被削弱
（放宽泄露模式、渲染链重新接收 anomalies、消歧校验关闭）时对应样本变红。

## 运行

```bash
uv run pytest tests/regression/fault_injection -m fault_regression -v
```

确定性、零 token、秒级。CI 在 `fault injection regression gate` 步骤强制执行
（失败阻断合并）。

## 样本清单

| 样本 | 故障来源 | 修复 | 断言守卫 |
|---|---|---|---|
| `samples/v5_leak_focus_036.txt` | v5（incident 036）：拓荆 171013 报告研究聚焦段实测泄露——英文任务独白 + Draft 标记 + 句中截断 | #221/#222（add-output-contract-guard） | `output_guard.validate_deliverable_text` 拒收 |
| `samples/v5_leak_english_monologue.txt` | v5 变体：英文思考独白主导成稿 | 同上（leak:let_me / 语言占比） | 同上 |
| `samples/v5_leak_truncated.txt` | v5 变体：句中悬空截断收尾 | 同上（truncated:tail） | 同上 |
| `samples/v5_clean_reference.txt` | —（防误伤哨兵，干净成稿） | — | `validate_deliverable_text` 直通 |
| F2（内联） | v2：价位校验报警文案（「95元」样本）泄入报告成稿 | #192（update-decision-price-gate，渲染链不接收 anomalies） | decision dict 注入 anomalies 键不外泄 + 渲染链源码不读取 |
| F3（内联） | v1 + 41.69% 撞车实例：2024 年报毛利率 = 2026Q1 单季毛利率，正文期次标注随采样漂移 | add-period-key-citation-validation | citation 消歧校验 FAIL（标记错配 / 裸引歧义），显式认领放行 |

## 扩充纪律

新增样本 MUST 是一次已修复的真实故障（标注故障版本与修复 PR/issue），
配确定性断言；禁止为凑数注入守卫从未放行过的假想样本。
