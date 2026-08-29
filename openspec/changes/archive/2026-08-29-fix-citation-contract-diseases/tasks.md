# Tasks: fix-citation-contract-diseases

- [x] 修 A：负索引约定 —— resolver 负索引单测钉住 + technical context 窗口说明明示负索引
- [x] 修 B：单一词表 —— 四个分析师 context 段落标题标注英文 state 键；resolver 支持 DataFrame 行键.列名 与 `[N]` 括号索引（单测覆盖）
- [x] 修 C：数值型容差改为 |delta|<0.01 或相对误差<0.5%（单测覆盖亿元级通过/显著偏离失败；spec Scenario「显著偏离仍失败」为相对≥0.5% 且绝对≥0.01 双条件）
- [x] 离线重判：tests/scripts/rejudge_citation_offline.py 对汉森制药 67 条 round-2 claims（原始 41 FAIL）归一化后重跑 —— **实测 FAIL 5**（非预估 0-2：残量全部为真幻觉，stated 值可证不在来源序列中——MA5=46.7/MACD 柱=17.8、38/RSI=6/BOLL 上轨=94.7；契约疾病归零，残量引用集合已被 tests/test_rejudge_offline.py 钉死）。归一化规则在预估之外另增三条数据驱动规则：年份粒度行键→报表日期列精确值、季度标签→并行列表序号、列名单位后缀省略还原（`每股净资产_调整前(元)` 写作无后缀）。fixture 修正：运行时 K 线实际含 2026-08-26 收盘（由 MA5/MA20 双方程解出隐含收盘 13.09 与真实一致，初版 08-25 假设有误）
- [x] 全量验证：uv run pytest -m "not live" 1411 passed / ruff 0 / mypy（citation.py + analysts.py 0 错，TypeGuard 收窄）
