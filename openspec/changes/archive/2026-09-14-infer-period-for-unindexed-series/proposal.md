## Why

r2 真实语料（`tests/data/citation_r2_claims.json`，565 条）与 r4 复判（`citation_r4_claims.json`）重放后，解析/术语层仍有三类**误 FAIL**（2026-09-14 实测，逐条可复现）：

1. **未索引序列引用无声明期次**：claim 写 `quarterly_trend.yoy`（无位置索引或季度段）而期次只出现在正文（「2026Q2净利润同比增速36.46%」），`period` 字段为空 → 解析得到整条列表 → `FAIL path_unresolvable`。实测同一 claim 带 `period=2026Q2` 判 PASS、仅去掉 period 字段即判 FAIL——判死的是**申报形式**而非数值对错（r2 语料 6 条，真值本可定位）。
2. **列名单位后缀 / 空值真值**：akshare 指标表真实列名带单位后缀（实测 `cache.db` 600519:indicators 有 `加权每股收益(元)`/`股息发放率(%)`/`净资产收益率(%)`），claim 常省略后缀 → `FAIL path_unresolvable`（r2 语料 `股息发放率`）；真值为 NaN（该期未披露）时 nan 参与比较恒假 → `FAIL value_mismatch`。
3. **术语判定过严**：`quarterly_trend.net_profit`（口径归母单季）撞词表内不一致（r4 招行 385.93 亿元）；`FCF` vs `FCF收益率`、`ROE` vs `加权ROE` 判张冠李戴（r4 两条，数值与真值一致）。

另发现一处方向性缺陷：路径止于列名（省略行键）时取 `iloc[-1]`，而 state 报表 DataFrame 为**生产者降序**（`compute.py` 以 `iloc[0]` 取最新）——取到了最旧行，注释与实现相反（当前语料无命中，属未爆的雷）。

上述全部属 incident 026 定性：**校验器限制被判成分析师错误**——FAIL 进 `citation_blocked` 与 `citation_analyst_true_fail`，污染门禁与归因桶。

## What Changes

- **解析期次推断（仅用于定位）**：序列元素定位取「`period` 声明值 → 正文唯一期次表述」（优先级：季度 > 完整日期 > 年月 > 年；多值/无值不猜）。`period` 一致性检查仍只比对声明值，不用推断值（避免自证循环）。
- **定位失败降级**：数值型路径解析结果为未索引序列（列表/元组）或 NaN 时 → `UNVERIFIABLE + coverage_gap`，SHALL NOT 判 FAIL；路径不存在等仍判 `path_unresolvable`。计算型 claim 的未索引序列引用按重算回声命中，语义不变。
- **列名单位后缀归一**：列名匹配在词表别名之外增加「剥尾部括号单位」一层（多列同名判歧义，不任选）。
- **省略行键取最新行**：修正 `iloc[-1]` → `iloc[0]`（与生产者降序一致）。
- **根域术语别名 + 脚本体边界包含**：`quarterly_trend.net_profit` 接受「归母净利润/净利润」（限定该根域，不合并全局规范键）；`FCF ⊂ FCF收益率`、`ROE ⊂ 加权ROE` 接受，`MA ⊂ MACD` 仍拦截。
- **常驻回归集**：新增 `tests/test_citation_real_corpus.py`——按生产者真实形状重建 state，重放 r2 全量 565 条（428 PASS 不回归 + 137 非 PASS 无误 FAIL，白名单仅 9 条契约强制项并注明理由）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `citation-verification`：「路径形态归一」增加未索引序列期次定位/降级、列名单位后缀、省略行键取最新行、NaN 降级四条款与场景；「术语与期次一致性校验」增加 quarterly_trend 根域序列键接受与脚本体边界术语包含两条款与场景。

## Impact

无产品行为变化（不新增数据、不改打分口径）。影响面：引用校验器的解析与术语判定——误 FAIL 减少，`citation_analyst_true_fail` 归因更准；不可知类引用从 FAIL 转 UNVERIFIABLE 并计入 `citation_unverifiable_unregistered`（监控可见，不进路由、不触发重试）。

回归：`tests/test_citation_unindexed_series.py`（19 例）+ `tests/test_citation_real_corpus.py`（19 例重放）+ `tests/test_citation.py` 既有例；真实数据定向验证见 `tests/validation/2026-09-14-infer-period-for-unindexed-series-validation.md`。
