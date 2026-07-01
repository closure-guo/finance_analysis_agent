# Claim Verification & Provenance — Research Notes

> 本文档记录 ADR-0010 Step 3（确定性引用校验器）设计思路的学术来源和调研基础。
> 每条设计决策标注来源论文/项目，便于后续评审和论文撰写。

## 1. 调研来源一览

| # | 来源 | 类型 | 核心贡献 |
|---|------|------|---------|
| 1 | [FinGround (arXiv:2604.23588)](https://arxiv.org/abs/2604.23588) — Guo et al., HKU, 2026 | 学术论文 | 六类金融 Claim 分类法 + computational claim 公式重构重算 |
| 2 | [LangChain qa_sources](https://python.langchain.com/docs/how_to/qa_sources/) | 框架文档 | 结构化 Citation 对象 + `with_structured_output` |
| 3 | [Perplexity 引用透明度机制](https://blog.csdn.net/CompiWander/article/details/161012628) | 产品调研 | 引用图谱 + 多源交叉验证 + 引用衰减提示 |
| 4 | [SourceScore VERITAS](https://sourcescore.org/docs/integrations/langchain/) | 开源工具 | HMAC 签名 Claim 库 + generate-then-verify 模式 |
| 5 | [Data Provenance 五要素](https://www.ipto.ai/articles/data-provenance-ai-agents) | 框架文章 | Source attestation / Retrieval context / Influence mapping |
| 6 | [TradingAgents (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138) — Xiao et al., UCLA+MIT, 2024 | 学术论文 | 多 Agent 交易框架：角色专业化 + 结构化输出解决电话效应 + Bull/Bear 辩论 |

---

## 2. 逐条设计思路溯源

### 2.1 六类 Claim 分类法

**来源**: FinGround (arXiv:2604.23588) §3.2

**论文原文**:
> We decompose a into atomic claims C = {c1, ..., cn}, each classified into one of six categories: numerical, temporal, entity-attribute, comparative, regulatory, and computational.

**论文验证**: 6 类优于 3 类 +4.3 F1；10 类无显著提升 (p=0.23)。

**我们的落地**: [ADR-0010](../adr/0010-tool-use-refactor.md) Step 3, `Claim.claim_type: Literal["numerical","temporal","entity","comparative","regulatory","computational"]`

**差异**: 无。完全采纳 FinGround 的分类法。

---

### 2.2 Computational Claim 公式重构重算

**来源**: FinGround (arXiv:2604.23588) §3.2 Verdict Classification

**论文原文**:
> For computational claims, standard NLI is insufficient; FINGROUND employs formula reconstruction: (1) identifying the implied formula using a library of 47 financial formula templates, (2) retrieving operand values from table cells, and (3) recomputing the derived quantity with ±0.5% tolerance.

**论文数据**:
- 现有检测器统一处理 claim，漏掉 43% 计算错误（§1 Introduction）
- 公式重构比 SelfCheckGPT-adapted +10–12 F1（§5.4，综述确认）
- 端到端计算型验证 90.2% F1（§3.2）
- 34% 计算型 claim 重生成产生新幻觉（§1 Introduction）
- 23% dangling citations 指向错位单元格（§1 Introduction）

**我们的落地**: [ADR-0010](../adr/0010-tool-use-refactor.md) Step 3, [dupont.py](../../src/finance_agent/metrics/dupont.py) 等纯函数从原始科目重算

**我们的优势**:
- FinGround 需要从 47 个模板猜测公式 → 我们通过 `field_ref` 直接定位到 `metrics/` 函数，无需猜测
- FinGround 从 RAG 检索的表格取操作数（23% dangling citation）→ 我们从 PREP 勾稽校验后的 state 取操作数，无检索错位
- FinGround 容差 ±0.5% → 我们采用相同容差

---

### 2.3 类型路由验证（Type-Routed Verification）

**来源**: FinGround (arXiv:2604.23588) §3.2

**论文原文**:
> type-routed strategies including formula reconstruction

**论文数据**:
> FActScore and SAFE decompose claims into atomic facts but treat all facts uniformly, so they cannot verify "gross margin was 62.4%" against table cells without structured extraction; this gap accounts for 43% of computational errors.

**我们的落地**: [ADR-0010](../adr/0010-tool-use-refactor.md) Step 3 校验器逻辑表

| claim_type | 校验方式 | 复用模块 |
|-----------|---------|---------|
| numerical / entity | `abs(state[field_ref] - stated_value) < tol` | 直接读 state |
| computational | 识别公式 → 取操作数 → 重算 → 比对 | `metrics/dupont.py` / `profitability.py` 等纯函数 |
| comparative | 两侧 numerical 校验 + 比较方向校验 | 复用 numerical |
| temporal | 数值校验 + 时间窗口存在性校验 | 直接读 state |
| regulatory | 引用存在性（不在本项目数据范围，标 `unverifiable` 跳过）| — |

**差异**: 无。类型路由策略完全采纳。

---

### 2.4 结构化 Citation 对象

**来源**: LangChain [qa_sources](https://python.langchain.com/docs/how_to/qa_sources/) 官方文档 + [TradingAgents (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138)

**LangChain 框架设计**:
```python
class Citation(BaseModel):
    text: str = Field(description="The cited text segment")
    source: str = Field(description="Source identifier like 'doc_0'")
```

**TradingAgents 论文原文（结构化输出解决"电话效应"）**:
> Most existing systems use natural language as the primary communication medium... This approach often results in a "telephone effect", where details are lost, and states become corrupted as conversations lengthen.
> Our framework combines structured outputs for control, clarity, and reasoning with natural language dialogue to facilitate effective debate and collaboration among agents.

**我们的落地**: 扩展为 `Claim` 结构，增加 `claim_type` + `field_ref` + `stated_value` + `interpretation`

**差异**: LangChain 的 Citation 是通用 RAG 场景（source 指向文档 ID），我们的 `field_ref` 指向 state 字段路径（如 `solvency_metrics.debt_ratio`），因为我们的"来源"不是文档而是 PREP 计算的结构化数据。TradingAgents 用结构化输出解决 agent 间通信的"电话效应"，我们用结构化输出同时解决通信和校验两个问题。

---

### 2.11 TradingAgents 架构借鉴

**来源**: [TradingAgents (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138) — Xiao et al., UCLA+MIT, 2024

**TradingAgents 5 层架构 vs 我们的落地**:

| 层 | TradingAgents 角色 | 我们的落地 | 差异 |
|---|------|-----------|------|
| I. Analyst Team | 基本面/情绪/新闻/技术面（4 并行） | 宏观/基本面/技术面/舆情（4 并行） | 我们多了宏观、少了独立新闻（舆情覆盖） |
| II. Researcher Team | Bull/Bear 辩论 + Research Manager | ✅ 完整采纳：Bull/Bear 2 轮并行辩论 + Research Manager | 2 轮（立论+反驳），Send 并行 |
| III. Trader | 买卖决策 | ✅ 采纳：Trader 基于辩论结论做交易决策 | 输出交易计划 |
| IV. Risk Management | 3 辩论者（激进/保守/中性）+ Risk Judge | ✅ 采纳：3 辩论者 2 轮 + Risk Judge | PREP 风控指标作为 prompt context 注入 |
| V. Fund Manager | 批准/拒绝/退回 | ✅ 采纳：批准/拒绝/退回（限 1 次） | 退回循环上限 1 次防死循环 |

**关键借鉴**:
1. **角色专业化 + 认知解耦**: 分析师并行各自专注一个维度，验证我们多 agent 并行的设计
2. **结构化输出解决电话效应**: 论文明确用结构化输出替代自然语言作为 agent 间通信介质，验证 Q8 的 (B)+(C) 选择
3. **辩论机制作为中间层**: Bull/Bear 辩论在分析师和决策者之间，减少确证偏误
4. **风险辩论的多视角压力测试**: 3 种风险偏好（激进/保守/中性）对交易计划做压力测试
5. **合规声明**: 即使做交易决策的系统也声明 "not intended as financial advice"，我们也保留免责声明

---

### 2.5 分层溯源（Data / Event / LLM Inference 三类来源）

**来源**: 综合设计，借鉴以下来源:

- **Data Claim（数据溯源）**: FinGround numerical/computational 类型 + [ipto.ai Data Provenance](https://www.ipto.ai/articles/data-provenance-ai-agents) 的 "Retrieval context" 要素
- **Event Claim（事件溯源）**: FinGround temporal 类型 + 项目 [001-llm-hallucination incident](../incidents/001-llm-hallucination-20260601.md) 的教训（LLM 编造事件）
- **LLM Inference（推断标注）**: FinGround regulatory 类型（标记 `unverifiable` 跳过）

**我们的落地**: `Claim.source_type: Literal["data", "event", "llm_inference", "mixed"]`

| source_type | 含义 | 校验策略 |
|------------|------|---------|
| data | 数字来自 state 字段 | `field_ref` 重算比对 |
| event | 事件引用来自 key_events | `event_ref` 引用存在性校验 |
| llm_inference | LLM 预训练知识推断 | 跳过（标 `unverifiable`） |
| mixed | 多源混合 | 拆分为原子 claim 分别校验 |

---

### 2.6 分 Agent 溯源粒度（非全员 Claim）

**来源**: 项目自主决策，基于 FinGround 的类型分布数据

**FinGround 数据支撑**:
- 6 类分类法优于 3 类 +4.3 F1，10 类无显著提升 → 6 类是最佳粒度
- computational 受益最大（公式重构比 SelfCheckGPT-adapted +10–12 F1）→ 适合基本面（杜邦）
- regulatory 标 unverifiable 跳过 → 宏观结论多为此类
- 蒸馏 8B 模型 91.4% F1，保留 96.2% → v2.0 可蒸馏降低成本

**我们的落地**:

| Agent | Claim 嵌入 | 溯源类型 | 验证策略 |
|-------|-----------|---------|---------|
| 基本面 | 强制 | data + computational | `metrics/` 纯函数重算 |
| 风控 | 强制 | data + computational | `metrics/risk.py` 重算 |
| 舆情 | 强制 | event | `event_ref` 引用存在性校验 |
| 宏观 | 不嵌入 | 标注 `llm_inference` | 跳过 |
| 技术面 | 部分 | 数字标 `field_ref`，定性标 `llm_inference` | 数字部分查 `metrics/technical.py` |

---

### 2.7 多源交叉验证（Cross-Verified 标记）— v2.0 备选

**来源**: Perplexity 引用透明度机制

**机制**: 同一事实被 ≥3 个独立源支持时加 "Consensus Verified" 徽章

**我们的潜在落地**: 当基本面和风控都引用同一指标（如资产负债率）且值一致时，标注 `cross_verified: true`。v1.0 不实现，记为 v2.0 备选。

---

### 2.8 引用衰减提示 — v2.0 备选

**来源**: Perplexity 引用透明度机制

**机制**: 超 18 个月的内容标 "Stale Source"

**我们的潜在落地**: 宏观数据（CPI/PMI）超 3 个月标 "数据可能过时"。v1.0 不实现，记为 v2.0 备选。

---

### 2.9 Generate-then-verify 后处理模式

**来源**: SourceScore VERITAS

**机制**: LLM 自由生成 → 后处理提取 atomic claim → 逐条验证

**我们的落地**: 不采用此模式。我们让 LLM 在生成时就输出结构化 Claim（structured output），而非事后提取。原因：事后提取需要 fuzzy alignment，容易丢失 field_ref。

---

### 2.10 Influence Mapping（数据→结论影响链）— v2.0 备选

**来源**: [ipto.ai Data Provenance](https://www.ipto.ai/articles/data-provenance-ai-agents) 五要素之 "Influence mapping"

**机制**: 记录检索数据如何影响最终输出，不仅是"数据来源"还有"数据如何影响结论"

**我们的空白**: 当前 ADR-0010 的 Claim 只记录 `field_ref`（数据来源），不记录"这个数据如何影响结论"。v1.0 不实现，记为 v2.0 备选。

---

## 3. 关键论文数据汇总

以下数据来自 FinGround (arXiv:2604.23588)，用于支撑设计决策:

| 数据 | 值 | 来源 | 支撑的决策 |
|------|-----|------|-----------|
| 现有检测器漏检计算错误 | 43% | §1 Intro | 必须用公式重构，不能靠 NLI |
| 公式重构 vs SelfCheckGPT-adapted | +10–12 F1 | §5.4 | computational 类型独立路由的价值 |
| 6 类 vs 3 类分类法 | +4.3 F1 (p<0.01) | §3.2 | 采纳 6 类分类法 |
| 10 类 vs 6 类 | 无显著提升 (p=0.23) | §3.2 | 不需要更细分类 |
| 端到端计算型验证 F1 | 90.2% | §3.2 | 公式重构的精度上限 |
| Retrieval-equalized 幻觉率降低 | 68–76% (p<0.01) | §1 Intro | 原子化 claim 验证的整体价值 |
| 蒸馏 8B 模型 F1 | 91.4%（保留 96.2%） | §3.4 | v2.0 可蒸馏降低成本 |
| 蒸馏模型 p95 延迟 | 340ms/claim（18× 提升） | §3.4 | v2.0 生产部署可行性 |
| 计算型 claim 重生成产生新幻觉 | 34% | §1 Intro | 验证需要 claim-type-aware routing |
| Dangling citations | 23% | §1 Intro | 我们用 PREP state 避免 RAG 错位 |

---

## 4. 与 FinGround 的关键差异

| 维度 | FinGround | 我们的项目 |
|------|-----------|-----------|
| 场景 | 通用金融文档 QA（RAG） | A 股投研分析（PREP + Agent） |
| 公式识别 | 从 47 个模板猜测 | `field_ref` 直接定位 `metrics/` 函数 |
| 操作数来源 | RAG 检索的表格单元格（23% dangling） | PREP 勾稽校验后的 state（无错位） |
| 容差 | ±0.5% | ±0.5%（相同） |
| 公式库 | 47 个模板 | `metrics/` 10 个模块（20+ 指标 + 杜邦） |
| 验证范围 | 全部 6 类 claim | 基本面强制，宏观/技术面/舆情分层，Risk Management 读 PREP 风控指标 |
| 部署 | 8B 蒸馏模型 vLLM | 纯 Python 纯函数（无需 GPU） |

**核心差异**: FinGround 是 RAG 场景（需要检索+识别），我们是 PREP 场景（数据已计算好，公式已写在 `metrics/` 里）。这使我们的重算更简单也更准确 —— 这是纯 LLM-only 项目无法复制的结构性优势。
