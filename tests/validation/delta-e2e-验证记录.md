# 两个 delta 端到端验证记录（2026-09-13 12:37 UTC）

## 600036——action=watch

- price_check: `None`
- 决策参数: `{'position_size': 'light', 'entry_price': None, 'stop_loss': None, 'target_price': None}`
- 派生指标（代码计算）: `{}`

**风险辩论引用情况**（mentions = reasoning 中出现代码计算的赔率/止损距离数值）:

- aggressive: mentions_ratio=None mentions_stop_pct=None
- conservative: mentions_ratio=None mentions_stop_pct=None
- neutral: mentions_ratio=None mentions_stop_pct=None
- aggressive: mentions_ratio=None mentions_stop_pct=None
- conservative: mentions_ratio=None mentions_stop_pct=None
- neutral: mentions_ratio=None mentions_stop_pct=None

**报告决策节**:

```

- **方向**: watch
- **置信度**: 62%
- **仓位**: light
- **再评估触发条件**: 见理由
- **理由**: 综合风险辩论，维持watch结论。共识点：招行基本面优质（净利率44.77%、ROE 13.44%、拨备与资本充足率股份行头部）且中期趋势确立（均线多头、MACD零轴上方）。分歧在入场时机：激进方主张轻仓立即建仓，但中性方指出RSI/KDJ高位入场使止损距离拉大、盈亏比劣于回调后入场，保守方强调高杠杆行业尾部风险（最大回撤16.18%、年化波动16.95%）与宏观未验证（PMI跌破荣枯线、息差压力仅缓解未扭转）。beta=-0.07的负相关被中性方合理质疑为可能来自统计噪音，不足以作为对冲买入依据。多数意见（保守+中性）支持watch，且均认同应设定具体回调触发位（如10/20日均线支撑附近）分批介入，而非无限期观望。因此维持watch，条件收敛为：回调至均线支撑分批轻仓介入，以16.18%历史回撤口径做压力止损参考，PMI回升或息差企稳作为加仓前置验证。

```

## 600519——action=watch

- price_check: `None`
- 决策参数: `{'position_size': 'light', 'entry_price': None, 'stop_loss': None, 'target_price': None}`
- 派生指标（代码计算）: `{}`

**风险辩论引用情况**（mentions = reasoning 中出现代码计算的赔率/止损距离数值）:

- aggressive: mentions_ratio=None mentions_stop_pct=None
- conservative: mentions_ratio=None mentions_stop_pct=None
- neutral: mentions_ratio=None mentions_stop_pct=None
- aggressive: mentions_ratio=None mentions_stop_pct=None
- conservative: mentions_ratio=None mentions_stop_pct=None
- neutral: mentions_ratio=None mentions_stop_pct=None

**报告决策节**:

```

- **方向**: watch
- **置信度**: 65%
- **仓位**: light
- **再评估触发条件**: 见理由
- **理由**: 维持watch结论。风险辩论中，保守方与中性方有力地指出激进方的两处核心论据漏洞：其一，beta 0.059仅度量相对大盘指数的共动性，不能推出茅台对宏观需求脱敏，PMI与M1-M2剪刀差走阔对其商务宴请与批价体系的传导依然成立；其二，最大回撤23.07%是历史极值而非安全边际，在增速中枢由正转负（-6.9%且降幅环比扩大）的基本面范式转换期，历史回撤幅度不构成底部边界。激进方的'历史黄金坑高胜率'与'低beta宏观脱敏'论点被推翻。同时中性方确认：单季降幅数据信息量有限（未区分基数效应/控量挺价/真实需求恶化），watch恰当地体现了该不确定性。综合判断：增长拐点未确认前买入缺乏基本面锚定，但ROE 32.5%、毛利率91.2%的护城河与低VaR(95%) 1.69%限制深跌风险，不支持sell。再评估触发条件明确为：单季增速降幅收窄至-4%以内（保守方建议连续两季确认以防基数效应假信号）+股价回踩MA60缩量企稳的双信号确认。确认后执行预案：light仓位（组合不超过5%），以MA60或前低为参考预设止损（派生口径估算8-10%）。

```
