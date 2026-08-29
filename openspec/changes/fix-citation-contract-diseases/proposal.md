# Proposal: fix-citation-contract-diseases

## Why

汉森制药 002412 复盘（2026-08-26，39/68 claims FAIL）实证归因：FAIL 几乎全部
是校验器/上下文构造的契约疾病，非 LLM 幻觉——
1. **索引错位**：technical context 裁剪为最近 60 期（index 59=最新），校验器
   按 state 完整 250 期序列解析（index 59=190 天前）→ 14 条技术面引用全灭
   （铁证：MA.20.59 与 BOLL.middle.59 同值 8.224，LLM 在忠实读数）；
2. **词表分裂**：context 用中文段落标题（利润表/盈利能力/杜邦分析…），校验
   器按 state 英文键解析 → ~24 条引用路径不可达，数值本身真实；
3. **容差失真**：数值型用绝对容差 0.01，对亿元级数值要求精确到分，四舍五入
   即假阴性。
   高 FAIL 率驱动 citation 重试全量重跑分析师（每轮 12~16 分钟、零收益），
   是超时事故的第二大成本来源。

## What Changes

- **负索引约定（修 A）**：序列型 field_ref 支持负索引（-1=最新一期，与序列
  长度解耦）；technical context 窗口说明明示该约定。裁剪窗口此后怎么改都不
  影响校验语义。
- **单一词表（修 B）**：各分析师 context 段落标题内联标注英文 state 键
  （如「利润表（income_statement，近3年）」），LLM 自然引用英文键；不在
  resolver 建中文映射表（避免第二份真相源腐烂）。resolver 补齐 DataFrame
  行键.列名解析与 `[N]` 括号索引。
- **相对容差（修 C）**：数值型 PASS ⟺ |delta| < 0.01 或相对误差 < 0.5%
  （与计算型对齐）。

## Capabilities

- **New Capabilities**: `citation-verification`（主规范库此前无该能力域；
  data-ordering-citation-contract 的「校验算法不变」契约位于 archive，本
  delta 以 ADDED 建立新契约并显式取代该限制）

## Impact

- `src/finance_agent/citation.py`（resolver：负索引/括号/DataFrame；容差）
- `src/finance_agent/nodes/analysts.py`（context 段落标注英文键 + 负索引说明）
- `tests/scripts/rejudge_citation_offline.py`（离线重判验收工具）
- 与评估体系类 delta 分开归档：本 delta 是「修仪器」
