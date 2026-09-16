# 验证报告：infer-period-for-unindexed-series（引用解析/术语判定按真实语料收口）

日期：2026-09-14　HEAD：`ea12f11` + 本轮改动　执行：本机（Windows / uv）

## 0. 变更范围

| # | 变更 | 层 | 触发证据 |
|---|---|---|---|
| A | 未索引序列期次定位（声明 `period` → 正文唯一期次）+ 定位失败降级 UNVERIFIABLE | 解析 | r2 语料 6 条裸序列真值可定位却判 FAIL；同 claim 带 period 即 PASS |
| B | `quarterly_trend.net_profit` 根域术语接受「归母净利润/净利润」 | 术语 | r4 招行 `net_profit.0` 385.93 亿元判 semantic_term_mismatch |
| C | 列名单位后缀归一（剥尾部括号单位；歧义不任选） | 解析 | r2 `financial_indicators.2025-12-31.股息发放率`（真实列 `股息发放率(%)`）判 path_unresolvable |
| D | 脚本体边界术语包含（FCF⊂FCF收益率、ROE⊂加权ROE；MA⊄MACD 仍拦截） | 术语 | r4 两条数值正确却判 semantic_term_mismatch |
| E | 路径止于列名取最新行（`iloc[-1]` → `iloc[0]`，生产者降序） | 解析 | 实现与注释相反（`compute.py` 以 `iloc[0]` 取最新）；当前语料未命中 |
| F | NaN 真值降级 UNVERIFIABLE（nan 参与比较恒假 → 误判 value_mismatch） | 解析 | 真实 600519 `股息发放率(%)` 最新期为 NaN |

## 1. 单元与门禁（TDD 先红后绿）

```
uv run pytest tests/test_citation_unindexed_series.py tests/test_citation_real_corpus.py -q
→ 38 passed
```

- 先红记录：`test_citation_unindexed_series.py` 首轮 8 failed / 6 passed（A/B 两族），
  C/D/E/F 补例后再红 4 条（`column_unit_suffix` / `suffix_not_mix` / `containment` / `latest_row`），
  NaN 例单跑 1 failed；实现后逐条转绿。
- 旧钉死语义更新 1 处：`tests/test_citation.py::TestNumericalRobustness::
  test_field_ref_resolves_to_list_fails_gracefully` → 更名 `..._degrades_without_fail`，
  断言 FAIL → UNVERIFIABLE（旧语义即本 delta 要改的行为，改动原因见 delta）。

## 2. 常驻回归集：r2 真实语料全量重放

`tests/test_citation_real_corpus.py`（19 例：9 traces × 2 组 + 1 护栏）

- state 按**生产者真实形状**构造：`quarterly_trend` 季度轴降序连续（实测 cache.db：
  `['2026Q2','2026Q1','2025Q4','2025Q3']`）、技术指标 `{指标:{参数:序列}}`、macro records
  列表、报表 DataFrame 降序（`报告日`/`日期` 分域）且指标表列名带单位后缀、文本 claim
  回声源；落值两趟（r2 真实解析读数优先，申报值补缺不覆盖）。
- 不变量结果：
  - **428 条 PASS → 0 条回归**（无一转为非 PASS）；
  - **137 条非 PASS → 无白名单外 FAIL**。白名单 9 条全部为 `comparative` 单端申报
    （citation-verification「基期值双端申报」SHALL 判 FAIL，三分析师 prompt 均强制双端），
    语料为契约生效前快照——FAIL 属契约执行，非校验器误报，逐条注明于
    `_EXPECTED_FAIL_ALLOWLIST`。

## 3. 真实数据定向验证（cache.db 600519，真栈数据非 mock）

`tmp/verify_period_inference_realdata.py`：

```
真实 quarterly_trend 季度轴： ['2026Q2','2026Q1','2025Q4','2025Q3']   yoy：[-6.9, 1.47, -30.34, 0.48]
[PASS        ] 裸序列+正文期次（无 period 字段）  gt=-6.904267458948038（= 真实 2026Q2 同比）
[PASS        ] 裸序列 net_profit + 词表「净利润」 gt=172.74（亿元）
[UNVERIFIABLE] 无行键列名 + 真值 NaN（降级）      gt=None, coverage_gap=True
[PASS        ] 无行键列名（真值存在）             gt=28.0779（最新行）
[PASS        ] 指标表列名带单位后缀（省略后缀）     gt=65.66（加权每股收益(元)）
[PASS        ] 术语包含 FCF ⊂ FCF收益率           gt=0.34586, unit_normalized=percent
```

要点：A 的定位值与真实数据 2026Q2 同比一致（-6.90 也即 r2 语料同值）；E 取最新行命中；
F 的空值降级不判死；C/D 均按真实列名与真实域判定通过。

## 4. 回归面

```
uv run pytest -q --ignore=tests/e2e      # 全量后端
uv run ruff check / ruff format --check  # 改动文件
uv run mypy src/finance_agent/citation.py
```

结果见 §5 追加（全量运行输出）。

## 5. 全量回归与静态检查

- 全量：`uv run pytest -q --ignore=tests/e2e` → **2383 passed, 2 skipped**（826s，本机）
- ruff check / ruff format --check：All checks passed（4 文件）
- mypy：Success: no issues found（`src/finance_agent/citation.py`）
- 台账：`docs/evals/metrics.md` §1.3 追加口径注（FAIL→UNVERIFIABLE 迁移的跨切点可比性说明）

## 6. 未覆盖 / 已知边界

- **comparative 单端申报**：按现行规范仍判 FAIL（契约强制）。语料里 9 条属契约生效前
  快照；现行 prompt 已强制双端，是否需要为「历史/异常单端」加降级通道，留待
  `docs/evals/metrics.md` 待决策清单评估（本轮不动，避免削弱契约）。
- **省略行键 + 声明期次的按期选行**：本轮只修正了取行方向（最新行）。r2 语料中
  「无行键报表引用」为 0 条，无证据支撑「按 period 选行」，故不改（记入本报告）。
- **正文期次推断的四级优先级**覆盖季度/日期/年月/年；中文数字月份（「2025年十二月」）
  不识别（无真实样本）。
