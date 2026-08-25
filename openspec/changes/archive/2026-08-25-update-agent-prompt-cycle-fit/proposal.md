# Proposal: update-agent-prompt-cycle-fit

## Why

上一轮 `enhance-agent-prompt-quality` 沉淀的提示词方法论经与 **2026-08 当前市场周期实测数据对照**（上证 2871 点、全 A PE-TTM 11-37、LPR 3.0%/3.5% 历史低位、M2 7.7%、PMI 49.4 荣枯线下）发现 3 处周期适配缺口 + 1 处系统性数据时效风险：

1. 分析师静态阈值（ROE 15%/负债率 60%）在低利率+宏观偏弱周期整体过严，未提示"阈值应参照同业/周期调整"。
2. technical_analyst 缺"强趋势中 RSI/KDJ 钝化失效"提示（TradingAgents 已含同款约束）。
3. macro_analyst 只看 M2 增速、未看 M1/M2 剪刀差（当前 M2 7.7% 但 M1 仅 4.0%，资金空转——纯 M2 判断会误判流动性宽松程度）。
4. **系统性**：PMI/CPI 数据接口时效滞后约 1 年（最新 2025 年），`fetch_macro_indicators` 未携带"最新数据日期/过期标记"，LLM 会把 2025 年 PMI 当"现在"——直接违反"以数据最新日期为现在"的反幻觉约束。

## What Changes

- ** fundamental_analyst.md 方法论**：ROE 15%/负债率 60% 等静态阈值改为"同业相对 + 周期感知"表述（阈值作为参考，必须与同业中位数对比并按当前利率/通胀环境调整）。
- **technical_analyst.md 方法论**：补"强趋势中 RSI/KDJ 可能长期钝化，以 MA 趋势为主、超买超卖信号降权"。
- **macro_analyst.md 方法论**：补 M1/M2 剪刀差判读（剪刀差收窄=资金活化、流动宽松成立；走阔=资金空转，需下调宽松结论），并补"指标数据若明显滞后于当前日期，须标注数据时效并降级结论"。
- **data 层时效守卫**：`fetch_macro_indicators` 返回结构追加每指标最新数据日期与过期标记（最新日期距今 >3 个月 → stale=true），prompt/摘要使用该标记。

不改变输出 JSON schema 与 LangGraph 节点结构（分析师 report 仍为 AnalystReport）；数据层仅扩展返回 dict 字段（向后兼容，加字段不破坏现有消费方）。

## Capabilities

- **Modified Capabilities**: `agent-prompt-contracts`（提示词行为契约——方法论规则更新为周期适配语义）、`pipeline-events` 或数据相关能力视 need（数据时效标记归属确认后决定，若主规范库无对应 capability 则新增）
- **New Capabilities**: 待定（数据时效守卫若无既有 capability 则新增 `macro-data-freshness`）

## Impact

- 代码：`src/finance_agent/prompts/{fundamental,technical,macro}_analyst.md`（Langfuse 发布 ver=3）；`src/finance_agent/data/akshare_client.py` `fetch_macro_indicators`（加字段 + 时效计算）；可能有 prompt 契约测试更新
- 行为：宏观分析结论质量（时效感知 + 剪刀差），技术面信号在趋势市不再误报，基本面阈值按同业/周期调整
- 测试：契约测试（方法论关键词）+ 数据守卫单测（stale 标记计算）