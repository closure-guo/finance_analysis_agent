# citation 22 条待终裁决策单

生成：tests/scripts/gen_pending22_sheet.py（2026-09-12）。每条含 r2 原判定、
r4（阶段 0–5 后校验器）同源判定、已核实证据与处置建议。**终裁人只需逐条
确认/否决「建议」列**——建议仅基于机器判定演化与代码取证，不代替人工判断。

| # | trace | r2 判定 | 归因 | field_ref | stated | r4 同源判定 | r4 ground_truth | 建议 |
|---|---|---|---|---|---|---|---|---|
| 1 | 比亚迪 | UNVERIFIABLE | 待终裁 | technical_indicators.MA.20.-1 | 3.62 | 同家族1条: PASS×1 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 2 | 比亚迪 | UNVERIFIABLE | 待终裁 | macro_indicators.pmi.1.制造业-指数 | 49.2 | 同家族1条: PASS×1 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 15 | 分析平安 | UNVERIFIABLE | 待终裁 | technical_indicators.MACD.histogram.-7 | 0.8077 | 同家族3条: PASS×3 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 16 | 分析平安 | UNVERIFIABLE | 待终裁 | technical_indicators.KDJ.J.-8 | 114.31 | 同家族1条: PASS×1 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 17 | 分析平安 | UNVERIFIABLE | 待终裁 | macro_indicators.m2.0.货币和准货币(M2)-同比增长 | 7.7 | PASS() | 7.7 | 校验器限制（r4 同源已修复为 PASS）→ 终裁「非幻觉」，无需处置 |
| 51 | 茅台 | UNVERIFIABLE | 待终裁 | technical_indicators.MA.5.-1 | 1306.264 | 同家族5条: PASS×2, UNVERIFIABLE×2, FAIL×1 |  | r4 同家族混合（同家族5条: PASS×2, UNVERIFIABLE×2, FAIL×1）→ 抽样人工复核该族，重点看 FAIL 项 |
| 52 | 茅台 | UNVERIFIABLE | 待终裁 | macro_indicators.cpi.0.全国-同比增长 | 0.8 | 同家族2条: PASS×2 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 73 | 宁德 | UNVERIFIABLE | 待终裁 | technical_indicators.MA.5.-1 | -54.04 | 同家族2条: PASS×1, UNVERIFIABLE×1 |  | r4 同家族混合（同家族2条: PASS×1, UNVERIFIABLE×1）→ 抽样人工复核该族，重点看 FAIL 项 |
| 74 | 宁德 | UNVERIFIABLE | 待终裁 | profitability_metrics.净利率.2025 | 17.04 | 同家族1条: PASS×1 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 75 | 宁德 | UNVERIFIABLE | 待终裁 | solvency_metrics.资产负债率.2025 | 61.94 | 同家族2条: PASS×1, UNVERIFIABLE×1 |  | r4 同家族混合（同家族2条: PASS×1, UNVERIFIABLE×1）→ 抽样人工复核该族，重点看 FAIL 项 |
| 76 | 宁德 | UNVERIFIABLE | 待终裁 | efficiency_metrics.存货周转率.2025 | 4.05 | 同家族2条: PASS×1, UNVERIFIABLE×1 |  | r4 同家族混合（同家族2条: PASS×1, UNVERIFIABLE×1）→ 抽样人工复核该族，重点看 FAIL 项 |
| 77 | 宁德 | FAIL·path_unresolvable | 待终裁 | quarterly_trend.yoy | 36.46 | 同家族 0 条 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 78 | 宁德 | FAIL·path_unresolvable | 待终裁 | quarterly_trend.net_profit | 225.46 | 同家族 0 条 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 79 | 宁德 | FAIL·path_unresolvable | 待终裁 | quarterly_trend.qoq | 8.72 | 同家族 0 条 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 88 | 中芯 | UNVERIFIABLE | 待终裁 | macro_indicators.m2.0.货币和准货币(M2)-同比增长 | 7.7 | 同家族2条: PASS×2 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 95 | 平安 | UNVERIFIABLE | 待终裁 | macro_indicators.pmi.0.制造业-指数 | 0.6 | 同家族4条: PASS×4 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 96 | 平安 | UNVERIFIABLE | 待终裁 | macro_indicators.m2.0.货币和准货币(M2)-同比增长 | -0.9 | 同家族5条: PASS×4, UNVERIFIABLE×1 |  | r4 同家族混合（同家族5条: PASS×4, UNVERIFIABLE×1）→ 抽样人工复核该族，重点看 FAIL 项 |
| 106 | 招行 | UNVERIFIABLE | 待终裁 | technical_indicators.MA.5.-1 | 41.25 | 同家族2条: PASS×1, UNVERIFIABLE×1 |  | r4 同家族混合（同家族2条: PASS×1, UNVERIFIABLE×1）→ 抽样人工复核该族，重点看 FAIL 项 |
| 107 | 招行 | UNVERIFIABLE | 待终裁 | technical_indicators.MACD.histogram.-1 | 0.218 | 同家族2条: PASS×2 |  | r4 同家族全部 PASS（新规则吸收）→ 终裁「非幻觉」，无需处置 |
| 124 | 美的 | FAIL·path_unresolvable | 待终裁 | quarterly_trend.net_profit | 13771000000 | 同家族1条: FAIL×1 |  | r4 同家族混合（同家族1条: FAIL×1）→ 抽样人工复核该族，重点看 FAIL 项 |
| 125 | 美的 | FAIL·path_unresolvable | 待终裁 | quarterly_trend.yoy | 1.32 | 同家族1条: FAIL×1 |  | r4 同家族混合（同家族1条: FAIL×1）→ 抽样人工复核该族，重点看 FAIL 项 |
| 126 | 美的 | FAIL·path_unresolvable | 待终裁 | quarterly_trend.qoq | 8.65 | 同家族1条: FAIL×1 |  | r4 同家族混合（同家族1条: FAIL×1）→ 抽样人工复核该族，重点看 FAIL 项 |
| r4-1 | 全面分析平安银行 | FAIL·path_unresolvable（r4 轮） | 列名待核 | financial_indicators.加权每股收益 | 2.07 | 本轮（r4 即最新） | | 校验器限制（列名别名缺口，真实列名「加权每股收益(元)」实测）→ 终裁「非幻觉」；处置=词表补「加权每股收益(元)」别名 |
| r4-2 | 全面分析招商银行 | FAIL·path_unresolvable（r4 轮） | 列名待核 | financial_indicators.2025-12-31.加权每股收益 | 5.7 | 本轮（r4 即最新） | | 校验器限制（列名别名缺口，真实列名「加权每股收益(元)」实测）→ 终裁「非幻觉」；处置=词表补「加权每股收益(元)」别名 |
