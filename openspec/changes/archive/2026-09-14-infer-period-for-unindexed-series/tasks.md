## 1. 实现（TDD 先红后绿）

- [x] 1.1 红灯：`tests/test_citation_unindexed_series.py`——裸序列+正文期次 PASS / 无期次 UNVERIFIABLE / 期次错配仍 value_mismatch / 多期次不猜 / 声明期次不回归 / 路径不存在仍 FAIL / 期次检查只用声明值；net_profit 术语接受（净利润、归母净利润）与报表域不互认
- [x] 1.2 `_effective_period`（声明优先 / 正文唯一期次推断）+ 接入 `_verify_numerical` 解析调用；`_infer_period_from_text` 四级优先级
- [x] 1.3 解析结果为 list/tuple → UNVERIFIABLE + coverage_gap；NaN 真值同口径降级
- [x] 1.4 `_check_metric_term` 根域序列键别名表（quarterly_trend.net_profit）+ 脚本体边界术语包含（`_term_containment_ok`）
- [x] 1.5 `_resolve_column_alias` 单位后缀归一（歧义返回 None）；路径止于列名改取 `iloc[0]`（生产者降序最新在前）
- [x] 1.6 单文件全绿（19 例）+ 既有 `TestNumericalRobustness` 旧钉死改为新语义

## 2. 常驻回归集（r2 真实语料重放）

- [x] 2.1 生产者真实形状 state 构造器（季度降序连续轴 + 平行列表 / 技术指标 {指标:{参数:序列}} / macro records / 报表降序 DataFrame + 单位后缀列名 / 嵌套指标 dict / 文本源），落值两趟（ground_truth 权威优先，申报值补缺不覆盖）
- [x] 2.2 137 条非 PASS 重放：除白名单（9 条 comparative 单端＝契约强制，逐条注明）外零 FAIL
- [x] 2.3 428 条 PASS 重放：零回归（不转为非 PASS）
- [x] 2.4 语料护栏：565 条 / 137 非 PASS / 9 traces 不得被裁剪

## 3. 收口

- [x] 3.1 `openspec validate --strict` 通过
- [x] 3.2 archive + spec sync（主规范 53/53）+ 全量 `uv run pytest` 绿 + ruff/mypy
- [x] 3.3 真实数据定向验证脚本（cache.db 600519）跑通并落验证报告
- [x] 3.4（PR 见提交说明） PR + CI 绿
