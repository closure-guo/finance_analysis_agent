# Incident 022: 契约修复冒烟验证 — 第四类契约疾病浮现（技术上下文数组方向未声明）

**日期**: 2026-08-30
**环境**: citation 确定校验器（`src/finance_agent/citation.py`，fix-citation-contract-diseases 已合入）× 三标的深度模式实跑
**关联**: [020](020-citation-contract-diseases-20260828.md)（修 A/B/C 的验收延续）、`harden-evaluation-rigor`（verifier-baseline-v1 立项）

## 现象

契约修复后首次多标的冒烟实跑（fast-path `/api/analyze`，GLM-5.3，2026-08-30 09:34Z）：

| 标的 | 类型 | claims | PASS | FAIL | UNVERIFIABLE | FAIL 率 | citation_pass | 分析师轮次 |
|---|---|---|---|---|---|---|---|---|
| 汉森制药 002412 | 历史事故现场 | 46 | 41 | 1 | 4 | **2.2%** | false | 2（重试 1 次） |
| 贵州茅台 600519 | 大盘股 | 45 | 36 | 1 | 8 | **2.2%** | false | 3（重试 2 次） |
| 中际旭创 300308 | 异动股 | 24 | 8 | 13 | 3 | **54.2%** | false | 2（重试 1 次） |

证据：`reports/citation_smoke_verify.json`（Langfuse trace 取证：d7e46a12… / 04d79b40… / da3a81c6…）。

## 验收判定（按任务 1 五项标准）

| 标准 | 结果 |
|---|---|
| FAIL 率 < 10% | **部分通过**：汉森/茅台 2.2% ✅；中际旭创 54.2% ❌ |
| `iteration_count` 未递增 | **未过**：三标的均触发分析师全量重跑（node_start 序列实证：汉森 2 轮、茅台 3 轮、中际旭创 2 轮） |
| 技术类 field_ref 负索引且全解析 | **通过**：三标的全部使用负索引；汉森 14/14、茅台 16/16 解析 PASS；中际旭创 14 条解析到值但 13 条值级 FAIL |
| 基本面类 field_ref 英文键 | **通过**：零中文根键 |
| 亿级数值无绝对容差误判 | **通过**：茅台 3/0、汉森 4/0 |

## 归因（含漏网路径定位）

### A. 中际旭创 13 条技术 FAIL = 第四类契约疾病（期次错位），校验器裁决正确

FAIL 明细（全部 `technical_indicators.*.-1` 且值级偏差巨大，如 MA5 stated=1211.36 vs gt=858.32）：

- **数据方向取证**：`fetch_kline` 明确 `sort_values("日期")` 升序存储（`src/finance_agent/data/akshare_client.py:417`），state 的 technical 序列为**时间正序**（旧→新）；
- 校验器 `-1` 解析到序列末元素 = **真实最新值**（MA5=858.32），**解析层完全正确**；
- LLM 的 stated 值逐条等于**该序列窗口首元素**（MA5=1211.36 / MA10=1172.33 / MACD.DIF=96.64…），并以这些值编造「多头排列」叙事——与真实最新结构（MA5 858 < MA60 1069，空头排列）互为镜像；
- **归因**：technical context（`analysts.py` `_build_technical_context`）只声明「各序列为最近 60 期 + 负索引约定」，**未声明数组内部顺序**（正序、末尾为最新）。LLM 按主流行情展示习惯（最新在前）将窗口首元素误读为「最新」，期次整体错位（60 个交易日前）。同类语境下汉森/茅台的 LLM 会话读对了方向（stated=末元素），证明是**会话相关的行为风险**而非确定性 bug；
- **不是校验器问题**：残量 FAIL 是「stated 值与 state 最新期不符」的真质疑，`citation.py` 裁决正确，契约不修。

### B. 任一 FAIL 即触发全量重跑（iteration_count 递增）

`citation_pass=false`（即使 1/46 条 FAIL）→ `after_citation` 走 retry，分析师全量重跑（茅台 3 轮 = 2 次重跑）。这是 incident 020 遗留 #1「重试策略未改」的复现，与本次契约修复无关。

### C. 单条叙述性键 FAIL（汉森 `quarterly_trend.warnings` / 茅台 `quarterly_trend.yoy`）

field_ref 指向容器键（warnings/yoy 为 dict/非数值），gt=None → FAIL。路径写法缺期次/具体值定位（应如 `quarterly_trend.yoy.<季度序号>`）。数值大概率真实存在——按标注口径②属路径问题，不计 Agent 错。校验器语义正确（容器键不可直接数值比对）。每标的仅 1 条（2.2%），残量风险级。

## 修复（本任务红线：业务管线零改动 → 落新 delta）

1. **建议 delta「技术上下文数组方向声明」**：`analysts.py` 技术 context 明示「序列为时间正序（旧→新），列表**末尾**为最新一期；引用 -1 时必须核对末元素」，并可在反幻觉规则中增加「引用最新值前先确认位于序列尾部」。预期将中际旭创类期次错位降为零。属业务 prompt/context 变更，另行走 OpenSpec 管线。
2. **重试策略 delta**（020 遗留 #1）：citation FAIL 触发重跑的门槛与收益评估（降级判定已有 stargnation 逻辑，需放宽首轮即重跑的行为）。亦另立。

## 验证数据（修复前的现状基线）

- 三标的 Langfuse trace 取证 JSON：`reports/citation_smoke_verify.json`
- 技术 FAIL 明细 + context 序列方向证据：见上节 A；原始 index-interp 对照存于本记录下方附录
- node_start 序列（分析师轮次实证）查询脚本：`tests/scripts/verify_smoke_citation.py --collect-only` 可复现证据拉取
- 亿级数值 PASS 明细：茅台 3 条（无绝对容差误判）、汉森 4 条（同）

## 结论

契约修复（负索引/单一词表/相对容差）在**稳态标的**（汉森/茅台）冒烟通过（FAIL 率 2.2%、零契约疾病）；**趋势异动标的**暴露第四类契约疾病（context 数组方向未声明 → LLM 期次错位），校验器裁决正确、待 context 修复（新 delta）。iteration 递增重跑为已知遗留，另立 delta。任务 1 冒烟验收：**部分通过**，两处未过项均有明确归因与修复路径，不放大为校验器缺陷。

## 附录：中际旭创技术 FAIL 明细（stated vs 解析 gt）

| field_ref | stated | gt (最新真实值) | 判定 |
|---|---|---|---|
| MA.5.-1 | 1211.36 | 858.32 | LLM 期次错位（引窗口首元素） |
| MA.10.-1 | 1172.33 | 902.35 | 同上 |
| MA.20.-1 | 1100.09 | 915.36 | 同上 |
| MA.60.-1 | 834.88 | 1069.12 | 同上 |
| MACD.DIF.-1 | 96.64 | -44.09 | 同上 |
| MACD.DEA.-1 | 92.15 | -43.20 | 同上 |
| RSI.14.-1 | 62.63 | 41.56 | 同上 |
| BOLL.upper/lower/middle.-1 | 1282.05/918.14/1100.09 | 1016.90/813.82/915.36 | 同上 |
| KDJ.K/D/J.-1 | 70.3/78.28/54.35 | 19.57/27.11/4.49 | 同上 |