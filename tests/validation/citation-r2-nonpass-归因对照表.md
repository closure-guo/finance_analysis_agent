# citation r2 非 PASS 137 条离线归因对照表

生成：rework-citation-gate-attribution 阶段 1–3 归一规则（纯规则判定）。**「校验器误报」「结构不可验」为本表的机器归因，待 owner 逐条终裁确认；「待终裁」行必须人工看。**

| 归因 | 处置 | n |
|---|---|---|
| 结构不可验→分型 | 文本 claim 回声匹配 | 81 |
| 校验器误报 | 路径形态归一（日期/季度标签） | 18 |
| 待终裁 | 计算型未注册或空值 | 16 |
| 待终裁 | 路径不可解析（无日期/季度形态，需核对该域真实键） | 6 |
| 校验器误报 | 词表别名/真实列名 | 5 |
| 校验器误报 | 符号校验限定有符号量 | 5 |
| 校验器误报 | 单位量级归一 | 5 |
| 结构不可验→注册 | 派生字段重算注册 | 1 |

| # | trace | 原状态 | 桶 | 归因 | 处置 | field_ref | stated | interp(截断) |
|---|---|---|---|---|---|---|---|---|
| 1 | 比亚迪 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | technical_indicators.MA.20.-1 | 3.62 | MA20 由 60 期前的 92.46 回落至 88.84，累计下行约 3.62 |
| 2 | 比亚迪 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | macro_indicators.pmi.1.制造业-指数 | 49.2 | 7月制造业PMI为49.2，较6月的50.3回落，跌破荣枯线 |
| 3 | 比亚迪 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.yoy.2026Q2 | 29.664 | 2026Q2归母净利润同比+29.66% |
| 4 | 比亚迪 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.yoy.2026Q1 | -55.384 | 2026Q1归母净利润同比-55.38% |
| 5 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.0.title | 比亚迪2026年中报净利润123.25亿元、同比下降20.54% | 核心业绩利空，为舆情面最主要的负面因素 |
| 6 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.1.title | 闪充车型订单需求充足，将全力推进产能释放 | 公司层面的正面经营信号 |
| 7 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.2.title | 海外销量增长迅猛，国内第1万座闪充站正式落成 | 出海与补能网络双利好 |
| 8 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.9.title | 闪充站数量破万、年底冲2万座，AI储能成为下一阶段进攻主线 | 媒体看好闪充+AI储能的战略叙事，正面舆情 |
| 9 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.6.title | 未来两三年是智驾、座舱及AI技术加速落地关键窗口期 | 管理层技术战略指引，中性偏正面 |
| 10 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.7.title | 物理AI复杂度极高，公司正从简单场景逐步推进机器人应用 | 机器人布局务实推进，中性 |
| 11 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.3.title | 27.78亿元资金今日流出汽车股 | 行业资金面短期承压，轻微负面 |
| 12 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.5.title | 车企60天账期承诺兑现情况受媒体监督 | 行业治理类中性话题，比亚迪被纳入对比范围 |
| 13 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.0 | 2024年2月推出荣耀版车型起售价降至7.98万元，引发行业价格战 | 历史L1级事件，曾压制盈利与行业格局，当前未复现 |
| 14 | 比亚迪 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.1 | 泰国工厂投产、年产能约15万辆，全球化进入本地化生产阶段 | L2级持续利好事件，与近期海外销量高增新闻相互印证 |
| 15 | 分析平安 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | technical_indicators.MACD.histogram.-7 | 0.8077 | 7期前红柱峰值0.808，红柱从峰值快速收缩，短期动能明显衰减 |
| 16 | 分析平安 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | technical_indicators.KDJ.J.-8 | 114.31 | 8期前J值高达114.3（超买极值区），此后持续回落，短线动能消退 |
| 17 | 分析平安 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | macro_indicators.m2.0.货币和准货币(M2)-同比增长 | 7.7 | 2026年7月 M2 与 M1 增速剪刀差为 3.7 个百分点 |
| 18 | 分析平安 | FAIL | semantic_term_mismatch | 校验器误报 | 词表别名/真实列名 | income_statement.20251231.归属于母公司的净利润 | 134778000000 | 2025年归母净利润1347.78亿元 |
| 19 | 分析平安 | FAIL | semantic_term_mismatch | 校验器误报 | 词表别名/真实列名 | income_statement.20241231.归属于母公司的净利润 | 126607000000 | 2024年归母净利润1266.07亿元 |
| 20 | 分析平安 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | financial_indicators.2025-12-31.加权每股收益 | 7.44 | 2025年加权EPS 7.44元，2024年6.99元 |
| 21 | 分析平安 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.yoy.2026Q2 | 64.66 | 2026Q2归母净利润同比+64.7% |
| 22 | 分析平安 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.net_profit.2026Q2 | 675.63 | 2026Q2归母净利润675.63亿元 |
| 23 | 分析平安 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.net_profit.2026Q1 | 250.22 | 2026Q1归母净利润250.22亿元 |
| 24 | 分析平安 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.yoy.2026Q1 | -7.38 | 2026Q1归母净利润同比-7.4% |
| 25 | 分析平安 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.net_profit.2025Q4 | 19.22 | 2025Q4归母净利润19.22亿元 |
| 26 | 分析平安 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.yoy.2025Q4 | -74.11 | 2025Q4归母净利润同比-74.1% |
| 27 | 分析平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | garp_result.failures | PE>=行业平均；负债率>=60% | GARP估值未通过 |
| 28 | 分析平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.2.title | 2026年中报净利润925.85亿元、同比上涨36.06% | 核心业绩利好，构成近期舆情最主要的正面支撑 |
| 29 | 分析平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.1.title | 2026年二季度已披露持股减少机构超360家 | 机构持仓集中减少，反映部分机构兑现收益，为主要负面信号 |
| 30 | 分析平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.6.title | 五大上市险企上半年净利同增近八成 | 行业整体业绩向好，保险板块走强，属行业性正面舆情 |
| 31 | 分析平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.5.title | 互联网保险概念下跌0.93%，主力资金净流出15股 | 概念板块短期资金流出，板块情绪小幅转弱，属轻微负面 |
| 32 | 分析平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.4.title | 21股获融资客大手笔净买入（含平安） | 杠杆资金积极买入，短期资金面情绪偏正面 |
| 33 | 分析平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.7.title | 31股获杠杆资金净买入超亿元 | 杠杆资金持续净买入，市场情绪回暖信号 |
| 34 | 分析平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.0.summary | 代理人队伍缩减至35.4万人，较峰值下降约60% | 寿险改革阵痛持续，NBV绝对值仍低于2019年水平，为持续性偏负面因素 |
| 35 | 茅台现金流 | FAIL | direction_mismatch | 校验器误报 | 符号校验限定有符号量 | macro_indicators.pmi.0.制造业-指数 | 49.8 | 8月制造业PMI为49.8，低于荣枯线50 |
| 36 | 茅台现金流 | FAIL | direction_mismatch | 校验器误报 | 符号校验限定有符号量 | macro_indicators.pmi.0.非制造业-指数 | 49 | 8月非制造业PMI为49.0，低于荣枯线，服务业景气偏弱 |
| 37 | 茅台现金流 | FAIL | direction_mismatch | 校验器误报 | 符号校验限定有符号量 | macro_indicators.pmi.1.制造业-指数 | 49.2 | 7月制造业PMI为49.2，低于荣枯线 |
| 38 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | cashflow_metrics.经营现金流/净利润.2025 |  | 经营现金流/净利润低于0.8且连续低于2024年水平，利润含金量边际走弱，但绝对 |
| 39 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.0.title | 2026年中报净利润445.17亿元、同比下降1.95% | 中报业绩小幅下滑，属轻微负面，但幅度有限 |
| 40 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.6.title | 年内第六次调价，自营店飞天涨至1766元 | 公司持续挺价，品牌力与渠道议价能力获正面评价 |
| 41 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.1.title | i茅台6款次新飞天9日起常态化投放 | 直销渠道常态化放量，渠道改革深化，偏正面 |
| 42 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.3.title | 次新飞天由每月仅三天到每日两场可购 | 直销供给增加，公司主动调节市场供需 |
| 43 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.4.title | 主力资金连续5日净流入140股（含茅台） | 资金面舆情偏暖，市场短期情绪积极 |
| 44 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.7.title | 13.94亿主力资金净流入，白酒概念涨2.19% | 白酒板块资金回流，行业情绪改善 |
| 45 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.8.title | 食品饮料行业资金流入榜：贵州茅台等5股净流入超亿元 | 个股获亿元级资金净流入，市场关注度高 |
| 46 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.9.title | 两融余额三连降，累计缩水286.82亿元 | 杠杆资金整体谨慎，为市场层面的中性偏谨慎信号，非公司特定 |
| 47 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.0.title | 飞天茅台出厂价上调约20%至1169元/瓶 | 重大历史提价事件，奠定近年利润基础 |
| 48 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.1.title | i茅台数字营销平台上线 | 渠道数字化改革持续深化，长期正面 |
| 49 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.2.title | 张德芹接任贵州茅台董事长 | 管理层变动属中性，市场关注渠道与价格策略延续性 |
| 50 | 茅台现金流 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list | 新闻列表中无经营性现金流相关报道 | 用户关注的现金流健康度在舆情侧缺乏证据，需依赖财报数据，数据不足 |
| 51 | 茅台 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | technical_indicators.MA.5.-1 | 1306.264 | MA5(1306.26)略高于MA20(1301.66)与MA60(1274.6 |
| 52 | 茅台 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | macro_indicators.cpi.0.全国-同比增长 | 0.8 | CPI同比从7月的0.5%回升至8月的0.8% |
| 53 | 茅台 | FAIL | value_mismatch | 校验器误报 | 单位量级归一 | cashflow_metrics.FCF.2025 | 583.95 | 2025年自由现金流约583.95亿元 |
| 54 | 茅台 | FAIL | value_mismatch | 校验器误报 | 单位量级归一 | cashflow_metrics.FCF.2024 | 877.85 | 2024年自由现金流约877.85亿元 |
| 55 | 茅台 | FAIL | value_mismatch | 校验器误报 | 单位量级归一 | income_statement.20251231.营业总收入 | 1720.54 | 2025年营业总收入1720.54亿元 |
| 56 | 茅台 | FAIL | value_mismatch | 校验器误报 | 单位量级归一 | income_statement.20251231.归母净利润 | 823.2 | 2025年归母净利润823.20亿元 |
| 57 | 茅台 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.yoy.2026Q2 | -6.9 | 2026Q2归母净利润同比-6.9% |
| 58 | 茅台 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.yoy.2025Q4 | -30.34 | 2025Q4归母净利润同比-30.34% |
| 59 | 茅台 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.qoq.2026Q1 | 53.97 | 2026Q1归母净利润环比增长53.97% |
| 60 | 茅台 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.net_profit.2026Q1 | 272.43 | 2026Q1归母净利润272.43亿元 |
| 61 | 茅台 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.net_profit.2026Q2 | 172.74 | 2026Q2归母净利润172.74亿元 |
| 62 | 茅台 | FAIL | value_mismatch | 校验器误报 | 单位量级归一 | balance_sheet.20251231.应收账款 | 260.9 | 2025年末应收账款约260.90万元 |
| 63 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | garp_result.pass | 0 | GARP估值未通过，净利润增长率不达标 |
| 64 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.0.title | 2026年中报净利润445.17亿元，同比下降1.95% | 核心负面舆情：业绩出现小幅同比下滑，压制市场情绪 |
| 65 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.6.title | 茅台年内第六次调价：自营店飞天涨至1766元 | 挺价能力强，公司对终端价格体系仍有掌控力，正面信号 |
| 66 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.3.title | i茅台次新飞天开启常态化售卖，由每月仅三天到每日两场可购 | 直销渠道放量，渠道数字化改革持续深化，正面信号 |
| 67 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.7.title | 13.94亿主力资金净流入，白酒概念涨2.19% | 板块资金面回暖，市场对白酒股情绪修复 |
| 68 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.4.title | 主力资金连续5日净流入140股 | 贵州茅台位列资金持续流入个股，情绪面偏正面 |
| 69 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.9.title | 两融余额三连降，累计缩水286.82亿元 | 市场整体杠杆资金收缩，风险偏好下降的背景性信号 |
| 70 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.0.title | 飞天茅台出厂价上调约20%（969元升至1169元） | 历史重大正面事件，直接增厚利润，体现强定价权 |
| 71 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.2.title | 张德芹接任贵州茅台董事长 | 管理层变动影响中性，市场关注渠道与价格策略延续性 |
| 72 | 茅台 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list | 近10条新闻中正面/资金面类约6条，负面1条，中性3条 | 负面舆情集中度低，整体舆情结构中性偏正面，9月以来呈改善趋势 |
| 73 | 宁德 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | technical_indicators.MA.5.-1 | -54.04 | MA5 较 MA60 低约 54.04（378.45-341.92），中期均线系 |
| 74 | 宁德 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | profitability_metrics.净利率.2025 | 17.04 | 2025年净利率17.04%，较2024年14.02%提升约3个百分点 |
| 75 | 宁德 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | solvency_metrics.资产负债率.2025 | 61.94 | 资产负债率由2024年65.24%降至61.94% |
| 76 | 宁德 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | efficiency_metrics.存货周转率.2025 | 4.05 | 存货周转率由2024年5.20次降至4.05次 |
| 77 | 宁德 | FAIL | path_unresolvable | 待终裁 | 路径不可解析（无日期/季度形态，需核对该域真实键） | quarterly_trend.yoy | 36.46 | 2026Q2净利润同比增速36.46% |
| 78 | 宁德 | FAIL | path_unresolvable | 待终裁 | 路径不可解析（无日期/季度形态，需核对该域真实键） | quarterly_trend.net_profit | 225.46 | 2026Q2净利润225.46亿元，环比+8.72% |
| 79 | 宁德 | FAIL | path_unresolvable | 待终裁 | 路径不可解析（无日期/季度形态，需核对该域真实键） | quarterly_trend.qoq | 8.72 | 2026Q2净利润环比增长8.72% |
| 80 | 宁德 | UNVERIFIABLE |  | 结构不可验→注册 | 派生字段重算注册 | garp_result.pass | 0 | GARP估值未通过，PE不低于行业平均且负债率超60% |
| 81 | 宁德 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.1.title | 宁德时代等在厦门成立创投基金，出资额50亿 | 公司资本开支与产业布局扩张，正面信号 |
| 82 | 宁德 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.2.title | 宁德时代在佛山成立新能源公司，含物联网业务 | 业务版图持续扩张，正面但影响中等 |
| 83 | 宁德 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.0.title | 宁德时代拿下海外大单 | 海外订单落地，利好基本面与舆情 |
| 84 | 宁德 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.9.title | 瑞浦兰钧：网传'限制员工如厕'等说法与事实不符，向宁德时代致歉 | 负面传闻被证实为谣言并获致歉，舆情风险消除 |
| 85 | 宁德 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.0.title | 发布神行电池PLUS，续航突破1000公里，支持4C超充 | L1级正面事件，巩固磷酸铁锂技术领先地位 |
| 86 | 宁德 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.1.title | 美国IRA及地缘政治因素导致福特密歇根电池工厂合作受阻，改为技术授权模式 | L1级负面事件，海外扩张面临持续政策风险 |
| 87 | 宁德 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list | 正面业务扩张类新闻约占30% | 近10条新闻中约3条为明确正面（海外大单、厦门基金、佛山新公司），其余为中性或无 |
| 88 | 中芯 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | macro_indicators.m2.0.货币和准货币(M2)-同比增长 | 7.7 | M2同比增速从2026年5月的8.6%回落至7月的7.7%，边际小幅收紧 |
| 89 | 中芯 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | garp_result.pass | 0 | GARP估值未通过，失败原因为PE不低于行业平均 |
| 90 | 中芯 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.1.title | 中国AI 50概念下跌1.49%，主力资金净流出40股 | 中芯国际所属AI概念板块近期资金流出、板块下跌，构成间接的轻微负面情绪信号 |
| 91 | 中芯 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.2.title | 国家大基金持股概念下跌1.08%，主力资金净流出35股 | 大基金持股概念（中芯国际为核心标的）资金流出，间接负面 |
| 92 | 中芯 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.0.title | 9月7日科创板主力资金净流入84.42亿元 | 科创板整体资金面一度大幅净流入，间接正面 |
| 93 | 中芯 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.0.title | 事件数据暂时不可用 | 个股关键事件缺失，重大事件影响无法评估 |
| 94 | 中芯 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list | 个股直接舆情数据缺失 | 新闻列表中无中芯国际个股新闻，个股舆情判断数据不足，整体舆情评级为中性 |
| 95 | 平安 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | macro_indicators.pmi.0.制造业-指数 | 0.6 | 制造业PMI从7月的49.2回升至8月的49.8，边际改善但仍处收缩区间 |
| 96 | 平安 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | macro_indicators.m2.0.货币和准货币(M2)-同比增长 | -0.9 | M2同比增速从5月的8.6%回落至7月的7.7%，货币扩张边际放缓 |
| 97 | 平安 | FAIL | semantic_term_mismatch | 校验器误报 | 词表别名/真实列名 | cashflow_metrics.FCF收益率.2025 | 2.4 | 2025年FCF收益率为2.40% |
| 98 | 平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | anomalies |  | 异常检测提示六项红灯：资产负债率、净债务/EBITDA、ROA、总资产周转率、经 |
| 99 | 平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | garp_result |  | GARP估值未通过，PE高于行业平均且净利润增速不足，当前估值对成长型投资者吸引 |
| 100 | 平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.0.title | 2026年中报净利润256.96亿元，同比增长3.32% | 核心正面业绩新闻，支撑盈利稳定预期 |
| 101 | 平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.2.title | 二季度已披露持股减少机构超30家 | 机构减持集中，反映机构信心偏弱，为重要负面信号 |
| 102 | 平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.3.title | 银行行业今日涨1.53%，主力资金净流入2.10亿元 | 板块层面资金情绪回暖，对个股舆情有间接支撑 |
| 103 | 平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.7.title | 银行行业资金流出榜：邮储银行、工商银行等净流出居前 | 板块资金面波动，存在阶段性流出压力 |
| 104 | 平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.9.title | 银行密集落地AI智能体 | 行业科技转型叙事，对平安银行数字化零售战略有正面联想 |
| 105 | 平安 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.0.title | 零售转型进入深水区，零售贷款不良率上升，信用卡、消费贷资产质量承压 | 持续性中性偏负面因素，资产质量是投资者核心关注点 |
| 106 | 招行 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | technical_indicators.MA.5.-1 | 41.25 | MA5(41.25)>MA10(40.85)>MA20(39.94)>MA60( |
| 107 | 招行 | UNVERIFIABLE |  | 待终裁 | 计算型未注册或空值 | technical_indicators.MACD.histogram.-1 | 0.218 | 柱状图由前期负值转正并连续扩大（-0.43→0.22），MACD多头动能增强，趋 |
| 108 | 招行 | FAIL | semantic_term_mismatch | 校验器误报 | 词表别名/真实列名 | income_statement.20251231.归属于母公司的净利润 | 150181000000 | 2025年归母净利润1501.81亿元，较2024年1483.91亿元增长1.2 |
| 109 | 招行 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.yoy.2026Q2 | 2.52 | 2026Q2净利润同比增长2.52% |
| 110 | 招行 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.qoq.2026Q2 | 1.96 | 2026Q2净利润环比增长1.96% |
| 111 | 招行 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | quarterly_trend.net_profit.2026Q2 | 385.93 | 2026Q2净利润385.93亿元 |
| 112 | 招行 | FAIL | path_unresolvable | 校验器误报 | 路径形态归一（日期/季度标签） | financial_indicators.2025-12-31.股息发放率 | 20.4354 | 2025年股息发放率约20.44%（预计算口径） |
| 113 | 招行 | FAIL | semantic_term_mismatch | 校验器误报 | 词表别名/真实列名 | financial_indicators.2025-12-31.加权净资产收益率 | 13.44 | 2025年加权净资产收益率13.44% |
| 114 | 招行 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.0.title | 2026年中报净利润764.45亿元、同比上涨2.02% | 核心正面新闻，业绩稳健增长支撑舆情 |
| 115 | 招行 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.4.title | 王小青行长任职资格获核准 | 管理层确定性提升，正面事件，影响中等 |
| 116 | 招行 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.2.title | 行长助理王兴海辞职 | 高管变动，轻微负面/中性事件 |
| 117 | 招行 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.3.title | 市值重回万亿元 | 市场信心修复的标志性正面事件 |
| 118 | 招行 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.9.title | 近半上市银行净息差企稳回升，为何难言拐点 | 行业性谨慎观点，净息差压力尚未根本缓解，构成潜在压制 |
| 119 | 招行 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.6.title | 跨境支付(CIPS)概念下跌1.05%，主力资金净流出 | 相关概念板块资金流出，轻微负面情绪信号 |
| 120 | 招行 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.5.title | 银行行业今日涨1.53%，主力资金净流入2.10亿元 | 板块资金净流入，行业情绪偏暖 |
| 121 | 招行 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.0.title | 零售客户数突破2亿，财富管理转型深化 | 长期正面基础事件，客户基础扩大支撑AUM增长 |
| 122 | 美的 | FAIL | direction_mismatch | 校验器误报 | 符号校验限定有符号量 | macro_indicators.pmi.0.制造业-指数 | 49.8 | 2026年8月制造业PMI为49.8，低于荣枯线50 |
| 123 | 美的 | FAIL | direction_mismatch | 校验器误报 | 符号校验限定有符号量 | macro_indicators.pmi.1.制造业-指数 | 49.2 | 2026年7月制造业PMI为49.2，低于荣枯线50 |
| 124 | 美的 | FAIL | path_unresolvable | 待终裁 | 路径不可解析（无日期/季度形态，需核对该域真实键） | quarterly_trend.net_profit | 13771000000 | 2026Q2单季归母净利润137.71亿元 |
| 125 | 美的 | FAIL | path_unresolvable | 待终裁 | 路径不可解析（无日期/季度形态，需核对该域真实键） | quarterly_trend.yoy | 1.32 | 2026Q2净利润同比仅增1.32% |
| 126 | 美的 | FAIL | path_unresolvable | 待终裁 | 路径不可解析（无日期/季度形态，需核对该域真实键） | quarterly_trend.qoq | 8.65 | 2026Q2净利润环比增长8.65% |
| 127 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.9.title | 截至8月31日累计回购A股股份金额达80.2亿元 | 大额回购彰显管理层信心，正面信号 |
| 128 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.0.title | 已回购超80亿元 |  |
| 129 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.2.title | 2026年中报净利润为264.46亿元 | 中报业绩披露，规模体量大，中性偏正面 |
| 130 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.1.title | 二季度已披露持股减少机构超160家 | 机构减持家数较多，资金面负面信号 |
| 131 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.3.title | 9月10日斥资3299.21万元回购38.36万股 | 回购持续进行，正面 |
| 132 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.4.title | 9月9日斥资4001.65万元回购46.79万股 | 回购持续进行，正面 |
| 133 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.5.title | 9月8日斥资6819.13万元回购80万股 | 回购持续进行，正面 |
| 134 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.6.title | 9月7日回购575000股 | 回购持续进行，正面 |
| 135 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.7.title | 9月4日斥资533.86万元回购6.14万股 | 回购持续进行，正面 |
| 136 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | news_list.8.title | 72股今日获机构买入评级 | 机构仍给予买入评级，中性偏正面 |
| 137 | 美的 | UNVERIFIABLE |  | 结构不可验→分型 | 文本 claim 回声匹配 | key_events.0.title | 库卡机器人业务分拆上市推进 | ToB转型长期利好，短期利润贡献有限，中性 |
