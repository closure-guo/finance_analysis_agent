# 两个 delta 端到端验证记录（2026-09-13 12:54 UTC）

## 601318——action=buy

- price_check: `{'result': 'pass', 'note': 'price_levels 不可用（unknown），跳过校验'}`
- 决策参数: `{'position_size': 'light', 'entry_price': None, 'stop_loss': None, 'target_price': None}`
- 派生指标（代码计算）: `{}`

**风险辩论引用情况**（mentions = reasoning 中出现代码计算的赔率/止损距离数值）:

- aggressive: mentions_ratio=None mentions_stop_pct=None
- conservative: mentions_ratio=None mentions_stop_pct=None
- neutral: mentions_ratio=None mentions_stop_pct=None
- aggressive: mentions_ratio=None mentions_stop_pct=None
- conservative: mentions_ratio=None mentions_stop_pct=None
- neutral: mentions_ratio=None mentions_stop_pct=None
- aggressive: mentions_ratio=None mentions_stop_pct=None
- conservative: mentions_ratio=None mentions_stop_pct=None
- neutral: mentions_ratio=None mentions_stop_pct=None
- aggressive: mentions_ratio=None mentions_stop_pct=None
- conservative: mentions_ratio=None mentions_stop_pct=None
- neutral: mentions_ratio=None mentions_stop_pct=None

**报告决策节**:

```

- **方向**: buy
- **置信度**: 60%
- **仓位**: light
- **入场价**: 未提供
- **止损价**: 未提供
- **目标价**: 未提供
- **理由**: 综合四轮风险辩论，方向上买入成立：中期多头趋势完好、基本面弱改善（中报净利大增36%、ROE回升至14%）构成买入基础，且方案已补齐完整退出纪律（52元分批入场、44元止损、63元目标、双退出条件，风险收益比约1.3:1）。仓位上采纳保守派与中性派裁决：置信度0.60、健康度52.1分（warning）、GARP不通过、机构减持四项负面信号叠加，胜率仅为中等偏上，期望优势薄，light仓位是证据强度下唯一诚实的仓位表达；激进方的moderate以上仓位主张在胜率证据不足下属透支。执行细则采纳保守派两项技术性要求：首批入场宜参考至少一项短期技术指标企稳信号（MACD绿柱收窄或KDJ超卖钝化）作为辅助触发条件，将左侧接刀修正为右侧分批；持仓期以中期均线作为动态止盈参考，与静态63元目标先到先执行。并重申底线：若首批触发止损，不得在同一下跌结构中立即重进。综上，维持light仓位分批买入，44元止损与中期趋势线为最终裁判，置信度0.60的交易，纪律即收益。

```

---

## 验证结论（2026-09-13，共 3 次真实管线运行：600036 / 600519 / 601318）

| 验证点 | 结果 |
|---|---|
| watch 分支报告渲染（无硬价格行 + 触发条件见理由 + 仓位行） | ✅ 600036 / 600519 |
| buy 分支「未提供」诚实标注（trader 未申报价位的真实形态） | ✅ 601318 |
| 仓位行 / 置信度 / 理由渲染 | ✅ 全部 |
| price_check 键在图终态持久化（incident 027 修复实证：修复前恒为 None） | ✅ 601318 |
| validate「价位缺失跳过校验」路径（trader 未申报价位的合法路径） | ✅ 601318 |
| buy + 真实价位 → derived_metrics 计算 + 辩论同源引用 | ⏳ 未覆盖：3 次运行 trader 均未申报价位（schema 可选字段，模型行为非确定）；计算与注入逻辑已由 21 个单元测试覆盖，真实数据路径留待 round8 实验提取核对 |

**附带发现（升级为 incident 027）**：首次 E2E 暴露 `price_check`/`derived_metrics` 等键未在 AnalysisState 声明、被图合并静默丢弃——价位校验 fail 打回与价位修正在 r1-r7 全部真实运行中从未生效。已修复（state.py 补声明 8 键 + 图通道契约测试），601318 运行实证修复生效。

**遗留观察**：trader 对价位的申报率不稳定（3/3 次 None）——价位是 buy/sell 决策的承重参数，「可选字段」设计削弱了 deterministic-derived-metrics 的触发面；可考虑后续 delta 把 buy/sell 的价位设为必填（trader.md 已要求，模型遵从率问题），交 round8 后评估。
