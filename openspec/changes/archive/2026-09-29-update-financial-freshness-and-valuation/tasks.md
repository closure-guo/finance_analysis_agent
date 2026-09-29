# Tasks: update-financial-freshness-and-valuation

- [x] 数据层：最新报告期快照获取（latest_period_snapshot state 键、累计口径标注、同比缺失留空、失败降级不阻断）——TDD 单测覆盖年报后含中报/无同期/全失败三场景
- [x] 数据层：季度利润表扩展单季营收/营业成本，quarterly_trend 增加营收同比与单季毛利率序列（缺失置 None，不产出伪值）
- [x] compute：PE_ttm 确定性推导（中报拼合/年报直取/输入缺失或 TTM≤0 留空注明原因），口径标注 derived_ttm，不覆盖主源 PE
- [x] metrics：GARP 估值输入缺失输出「数据缺失（未参与比较）」+ missing 标注，比较失败与数据缺失分桶
- [x] compute+analysts：估值段注入基本面上下文（PE/PE_ttm/PB/market_cap/相对估值结论），估值维度整体缺失时显式声明段
- [x] prompt：fundamental_analyst.md 更新输入清单与估值/快照分析要点（最新报告期校验年报趋势、估值必须有数字依据），执行 deploy_prompts 发布
- [x] metrics：INDUSTRY_OVERRIDES 增半导体设备覆盖（design.md 校准值），红黄绿灯与健康度输出携带 industry_override 口径标注，报告健康度章节渲染
- [x] citation：latest_period_snapshot.* 与 quarterly_trend 新字段的 claim 解析/回声匹配抽验，必要时补 assertion-golden-set 样例
- [x] evals 台账：健康度口径变更在 docs/evals/metrics.md §1 登记（口径变更先改台账再动代码的纪律）
- [x] 集成验证：以 688072 真实数据全管线运行，报告呈现中报毛利率回升事实、负债率最新值、PE_ttm 数字与口径、健康度行业口径标注；人工验证报告落 tests/validation/
- [x] openspec validate update-financial-freshness-and-valuation --strict 通过
