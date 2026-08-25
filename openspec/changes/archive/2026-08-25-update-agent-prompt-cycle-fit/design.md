# Design: update-agent-prompt-cycle-fit

## Context

2026-08 与提示词方法论实测对照（见 proposal Why）发现 3 处周期适配缺口 + 1 处数据时效系统性风险。本 delta 覆盖 prompt 层周期感知语义 + 数据层时效守卫，使"分析规则与当前市场周期一致"且有数据时效兜底。

**数据时效现状（实测）**：`fetch_macro_indicators`（akshare_client.py:497-518）拉 CPI/PMI/M2/LPR，每指标取最近 6 个月；但接口时效不一——PMI/CPI 最新仅 2025 年（滞后 ~1 年），M2/LPR 到 2026-08。当前返回 dict 无 as_of_date/freshness，LLM 无法识别滞后。

## Goals / Non-Goals

**Goals**
- 3 个分析师 .md（fundamental/technical/macro）方法论改为周期感知语义
- `fetch_macro_indicators` 返回结构追加 as_of_date + freshness（stale 界 = 3 个月）
- 宏观分析师提示词使用 freshness 标记降级结论（数据滞后 → 标注 + 降 confidence）
- 契约测试 + 守卫单测

**Non-Goals**
- 不修复 AKShare 接口本身的滞后（外部数据源问题，非本仓可控）
- 不改变 AnalystReport / TradeDecision JSON schema
- 不改 LangGraph 节点结构（只改 fetch 返回 + prompt 文本）
- 不给 fetch_macro_indicators 强行新增自动补拉接口（YAGNI）

## Decisions

### D1: 时效阈值 3 个月（90 天）

宏观指标月度发布，3 个月 = 约 3 期未更新才判 stale，容忍正常发布节奏（M2/LPR 当月、PMI/CPI 次月初），又足以捕获跨年滞后（当前 PMI/CPI 滞后 12 期）。

- 备选 1 期（1 个月）过严：LPR 两个月未动也符合国情（本月 3.0 下月或不变），会误标。
- 备选 6 个月过宽：无法在当年及时标记半年失真的数据。

### D2: as_of_date 从各指标首列（日期/月份）解析

现有代码已按首列降序、head(6) 取最新，as_of_date 直接取 records[0] 的首列值（兼容 date/datetime/月字符串）；freshness = (now - as_of_date).days ≤ 90。各指标独立计算——避免"PMI 滞后但 M2 新"时统一标记掩盖真相（spec 场景"不误用相邻指标日期"即为此）。

- 备选：统一按最新指标日期标记整体 freshness。否决：会掩盖单个指标滞后（正是本次事故）。

### D3: 时效元数据随记录返回，不新增单独 state 通道

在 `fetch_macro_indicators` 返回的每指标 dict 上追加 `as_of_date` + `freshness` 顶层键，消费方（macro analyst context 构建）读取后渲染进 prompt。既有消费方读 records 列表不受影响（向后兼容）。

### D4: 提示词改用"同业相对 + 周期感知"表述

fundamental_analyst 的 ROE 15% / 负债率 60% / 利息保障 3 等改为"参考阈值，须与同业中位数对比并考虑当前利率/通胀环境调整判定"。技术面补钝化提示；宏观面补剪刀差 + 时效降级。

## Risks / Trade-offs

- [freshness 误判（时区/月字符串解析）] → 单测覆盖月字符串（"2025年08月份"）与 ISO 日期两种格式，解析失败时默认 stale 且打 warning（fail-safe 偏保守）
- [提示词膨胀] → 每文件仅追加/改写 2-4 行，控制 token 增量
- [Langfuse 版本漂移] → 与上一 delta 相同：实施后发布 ver=3 production label，契约测试锁定本地
- [过严标注导致宏观结论过度悲观] → stale 只降级 confidence 不改变结论方向，把判断权交给 LLM

## Migration Plan

1. 改 `akshare_client.py:497-518` `fetch_macro_indicators`（as_of_date/freshness 计算 + 单测）
2. 改 macro analyst prompt（消费 freshness 的降级语义 + 剪刀差判读）
3. 改 fundamental/technical analyst prompt（周期感知表述）
4. 契约测试更新（方法论关键词断言）+ 数据守卫单测
5. pytest/ruff/mypy
6. Langfuse 发布 ver=3（如启用）
7. 跑一次 eval 对照本轮周期适配收益（可选）

## Open Questions

- macro_analyst 的 freshness 消费：是让 LLM 自发读"并标注时效"，还是由 context 构建层强制附加"⚠ 该指标数据滞后至 YYYY-MM"？倾向后者（确定性，不依赖 LLM 自觉），但实现需看 `_build_macro_context` 现有组装位置。