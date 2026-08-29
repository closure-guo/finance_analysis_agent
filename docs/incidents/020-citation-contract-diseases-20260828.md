# Incident 020: citation 校验器契约疾病 — 索引错位、词表分裂与容差失真制造大面积假 FAIL

**日期**: 2026-08-28
**环境**: citation 确定性校验器（`src/finance_agent/citation.py`）× 四分析师 context 构造（`src/finance_agent/nodes/analysts.py`）
**影响**: 汉森制药 002412 深研（2026-08-26）round-2 67 条 claims **41 条 FAIL（61%）**，复盘认定几乎全部为校验器/上下文构造的**契约疾病**而非 LLM 幻觉；高 FAIL 率驱动 citation 重试把 4 分析师全量重跑（每轮 12~16 分钟、零收益），是深研超时事故的第二大成本来源（incidents 019 遗留 #1 的立项兑现、006 的同族深化）
**状态**: 已修复（`fix-citation-contract-diseases` delta，分支待合并）

## 现象

- 002412 深研两轮校验，round-1 39/68 FAIL、round-2 41/67 FAIL，`citation_pass=False` 触发分析师全量重跑
- **铁证（索引错位非幻觉）**：`MA.20.59` 与 `BOLL.middle.59` 同值 8.224——LLM 在忠实读数，读的是 context 裁剪窗口（最近 60 期，index 59=最新）里的数；校验器却按 state 完整 250 期序列解析（index 59=190 天前）→ 14 条技术面引用全灭
- **词表分裂**：context 用中文段落标题（利润表/盈利能力/杜邦分析…），校验器按 state 英文键解析 → ~24 条引用路径不可达（如 `盈利能力.毛利率.2025`），数值本身真实
- **容差失真**：数值型绝对容差 0.01，对亿元级数值（1,038,756,658.94）要求精确到分，LLM 四舍五入即假阴性

## 根因（三层疾病 + 一个元根因）

| 层 | 根因 | 后果 |
|---|---|---|
| 索引语义 | context 序列裁剪窗口的索引（59=最新）与校验器按完整序列原位解析（59=190 天前），两套语义无契约对齐 | 技术面引用系统性错位 FAIL |
| 词表 | context 展示中文标签、state 键为英文，两套命名体系零对齐 | 引用路径不可达 FAIL |
| 容差 | 数值型绝对 0.01 未随数量级缩放（计算型早已是相对 0.5%） | 大数值四舍五入假阴性 |
| **元根因** | 校验器给 LLM 判卷，但**考卷（context）与答案册（state）不同源**——校验器自身从未被校准（"裁判无证上岗"） | 假 FAIL 被当作 LLM 幻觉，重试空转被误归因 |

## 修复（fix-citation-contract-diseases delta）

1. **修 A · 负索引约定**：序列型 field_ref 支持负索引（-1=最新一期，与序列长度及裁剪窗口解耦）；technical context 明示该约定——窗口此后怎么裁都不影响校验语义
2. **修 B · 单一词表**：各分析师 context 段落标题内联标注英文 state 键（如「利润表（income_statement，近3年）」），LLM 引用与校验器解析天然同源；**不在 resolver 建中文映射表**（避免第二份真相源腐烂）；resolver 补齐 DataFrame「行键.列名」解析与 `[N]` 括号索引；中文根键按不可路径 FAIL，不静默映射
3. **修 C · 相对容差**：数值型 PASS ⟺ |delta| < 0.01 **或**相对误差 < 0.5%（与计算型对齐；「显著偏离仍失败」为相对 ≥0.5% 且绝对 ≥0.01 双条件）
4. **离线重判设施**：002412 round-2 67 条 claims fixture（Langfuse 全保真）+ 归一化重跑脚本（中文根键→英文键、窗口正索引→负索引、年份粒度行键→日期列精确值、季度标签→并行列表序号、列名单位后缀省略还原——全部为词表/索引语义级规则，非逐条改值）

## 验证

- **离线重判：41 FAIL → 5，契约疾病归零**。残量 5 条全部为**真幻觉**（stated 值经来源序列全量搜索证伪：MA5=46.7 / MACD 柱=17.8、38 / RSI=6 / BOLL 上轨=94.7——股票价格 13 元量级下 MA5=46.7 物理不可能）；残量引用集合钉死为回归网（`tests/test_rejudge_offline.py`）
- **真实端到端（2026-08-29，002412 修复后实跑）**：28 claims，**0 FAIL** / 25 PASS / 3 UNVERIFIABLE（coverage_gaps=0 → 全为 llm_inference 契约跳过）；`citation_pass=true`，`iteration_count=1` 零重试；全程 2.7 分钟（修复前分析师每轮 12~16 分钟且被假 FAIL 拖入重跑）。证据：`tests/validation/2026-08-29-fix-citation-contract-diseases-validation.md`
- 全量 `pytest -m "not live"` **1411 passed** / ruff 0 / mypy 0（`_is_dataframe` 以 TypeGuard 收窄）
- **fixture 修复插曲（方法论教训）**：初版假设运行时 K 线止于 08-25，离线重算后技术面全灭；用 MA5/MA20 两个独立方程解出的隐含收盘完全一致（13.09），证实运行时实际含 08-26 交易日，重算后 claim 期望逐值命中——**离线重放的数据快照假设必须数值验证，不能靠时间推断**

## 关联与遗留

- 关联：[019](019-llm-output-truncation-governance.md) 遗留 #1（本 incident 立项兑现）、[006](006-citation-infinite-loop-20260716.md)（citation 重试无限循环的同族）、[001](001-llm-hallucination-20260601.md)（真幻觉治理）；`harden-evaluation-rigor`（评估体系 delta）已建立校验器准度基准集与门禁——本 delta 修复后其种子集门禁口径不变
1. **重试策略未改**：citation FAIL 仍触发分析师全量重跑（flag-only/重试环属另一 delta 范畴）。本 incident 消除的是「重试被契约疾病假 FAIL 触发」；真幻觉（实测 ~7%）触发的重试是否值得，待真实跑批观察
2. **真幻觉治理未立项**：5 条编造数值的 prompt 端防线（如要求技术面引用附「来源序列窗口」自证）可后续探索
3. **sync 协调**：`harden-evaluation-rigor` 与本 delta 都落 `citation-verification` capability（前者 ADDED 监控/注册表条款，后者新建 capability 并取代 data-ordering 的「校验算法不变」），后 sync 方须 rebase 到先 sync 方合并结果；数值容差措辞已按双条件口径在 tasks.md 对齐
4. **编号冲突预告**：未合并分支 `fix/deep-analysis-stuck` 上另有一份 incident 020（深研假卡死复盘），其合并时需改编号为 021 并回改本文件关联引用
