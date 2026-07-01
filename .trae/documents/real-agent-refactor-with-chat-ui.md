# 真实 Agent 重构计划：从固定流程到自主 Agent + 聊天 UI

> **归档**: 本方案已被 [ADR-0011](../../docs/adr/0011-five-layer-architecture.md) 的 5 层多 Agent 架构方案替代。tool calling 方案（ADR-0010 Step 1）已撤销，改为 PREP 一次性注入 + 5 层辩论/决策架构。聊天 UI 方案暂不实施。本文档保留作为设计历史参考。

## Summary

将 `finance_analysis_agent` 从「固定流程伪 Agent」重构为「真正的工具调用 Agent」，同时将 UI 从表单改为聊天界面。核心变更：

1. **LLM 层**：升级 `llm.py` 支持 tool-calling（当前只返回 `str`，无 `tools` 参数）
2. **State 层**：添加 `messages` 字段 + 聊天相关字段（当前无对话记忆）
3. **Tools 层**（新建）：粗粒度 `prepare_financial_data` tool + 细粒度查询 tools（复用现有 `metrics/` 和 `data/` 模块）
4. **Agent 层**（新建）：快速问答 Agent + 深度研究 Agent，基于 LangChain v1 `create_agent` + ReAct 循环
5. **Grounding 机制**：确定性引用校验器（ADR-0010 Step 3）—— 报告中每个数字反查 state 字段，派生指标用 `metrics/` 纯函数重算验证
6. **Graph 层**：用 Agent 循环替换固定管线，支持模式路由 + 引用校验重试循环
7. **UI 层**：用 `gr.Chatbot` 聊天界面完全替换现有表单，支持快速/深度两种模式 + 流式输出 + 文件下载

本计划严格对齐 **ADR-0010**（工具使用重构 + reflection + 确定性引用校验）和 **ADR-0009**（工具使用优先于辩论）。

***

## Current State Analysis

### 当前架构（伪 Agent）

当前系统是一个 **固定的 LangGraph 管线**，不是真正的 Agent：

```
START → check_cache →[HIT]→ validate →[PASS]→ compute_metrics → route_to_agent
       →[MISS]→ fetch_data → validate ─┘
                                                    ↓
                              [comprehensive] → Send(fa_analyze) ‖ Send(ia_analyze)
                              [financial]     → Send(fa_analyze)
                              [investment]    → Send(ia_analyze)
                                                    ↓
                              [comprehensive] → merge → generate_file → END
                              [其他]          → generate_file → END
```

**关键问题**（来自 ADR-0009 诊断）：

- `llm.py:23` 的 `call_llm` **没有** **`tools`** **参数**，只接受 `prompt: str`，返回 `str`
- LLM 无法主动查询数据 —— 所有上下文由 `_build_context` 在调用前一次性格式化塞入 prompt
- LLM 无法动态决策 —— 看到数据不足时无法发起工具调用补取，只能编造或写「数据缺失」
- `state.py` 的 `AnalysisState(TypedDict, total=False)` **没有** **`messages`** **字段**，无对话记忆
- `app.py` 是**表单式 UI**（股票搜索 + 分析类型下拉 + 下载按钮），`graph.invoke()` 阻塞调用，无流式

### 已有可复用资产

| 资产                                   | 位置                                                        | 复用方式                       |
| ------------------------------------ | --------------------------------------------------------- | -------------------------- |
| PREP 链（cache→fetch→validate→compute） | `nodes/cache.py`, `fetch.py`, `validate.py`, `compute.py` | 封装为粗粒度 tool                |
| `run_prep()` 同步编排器                   | `mcp_server.py:28-41`                                     | 粗粒度 tool 的实现基础             |
| 8 个 AKShare 数据获取方法                   | `data/akshare_client.py`                                  | 细粒度 tool 的数据源              |
| 10 个指标纯函数模块                          | `metrics/*.py`                                            | 细粒度 tool 的计算引擎 + 引用校验的重算基础 |
| 事件管线（3 级 fallback）                   | `events/pipeline.py`                                      | 细粒度 tool                   |
| 格式化器（纯函数）                            | `formatters.py`                                           | tool 返回值格式化                |
| 报告模板                                 | `templates/*.md`                                          | 最终报告渲染                     |
| 导出管线                                 | `export/*.py`                                             | docx/pptx 导出               |
| 5 个 MCP tools（已有 tool 封装模式）          | `mcp_server.py:68-153`                                    | tool 封装的参考模式               |

### 依赖版本（来自 `uv.lock`）

| 包                | 已安装版本     | 说明                                      |
| ---------------- | --------- | --------------------------------------- |
| `langgraph`      | 1.2.0     | 支持 v1 API                               |
| `langchain-core` | 1.4.0     | langgraph 依赖                            |
| `langchain`      | **未安装**   | 需新增，`create_agent` 在 `langchain.agents` |
| `litellm`        | ≥1.0.0    | DeepSeek 调用                             |
| `gradio`         | ≥5.0.0    | 支持 `gr.Chatbot`                         |
| `pydantic`       | 已安装（传递依赖） | 结构化输出                                   |

***

## Competitor Research & ADR Alignment

### 竞品调研结果（Trae WebSearch + MCP web\_search\_prime，2026-06-19 重新调研）

通过 Trae 内置 WebSearch 工具和 MCP web\_search\_prime 工具调研了同类金融 AI Agent 的架构、grounding / fact-checking 设计、以及聊天 UI 模式。以下是详细发现：

#### 1. FinDebate (arXiv:2509.17395) — 多 Agent 辩论金融分析

**架构**：两阶段设计

- **阶段一：5 个专业分析师 Agent 并行**（Earnings Analyst / Market Predictor / Sentiment Analyst / Valuation Analyst / Risk Analyst），每个 Agent 从各自维度分析，产出多维度洞察
- **阶段二：3 个辩论 Agent 单轮协作**：
  - **Trust Agent**：用证据增强原始报告，强化论证逻辑，但**禁止改变方向**（如从看涨改为看跌）
  - **Skeptic Agent**：从风险管理视角挑战报告，识别潜在风险
  - **Leader Agent**：综合 Trust 和 Skeptic 的输入，产出最终投资建议

**关键设计原则**：

- **单轮辩论优于多轮**：多轮辩论导致观点趋同（collapse）
- **立场锁定**：辩论阶段各 Agent 坚持初始观点不退缩
- **RAG-grounded**：每个论点必须由检索到的文档支持
- **错误率降低 18%**

**对本计划的启发**：ADR-0009 已参考此论文作为延后辩论的设计基线。本计划不实现辩论，但 Agent 的 system prompt 可借鉴其「角色专业化 + 立场锁定」思路。未来辩论落地时的 5+3 架构已在此论文中验证。

#### 2. FinSight / 玉兰·融观 (RUC, arXiv:2510.16844) — 专家级金融研报生成

**三大核心技术创新**：

- **CAVM (Code Agent with Variable Memory)**：将外部数据、工具、Agent 统一抽象为可编程变量空间。Agent 通过编写和执行 Python 代码灵活调用变量。赋予系统极高的自主性。
- **迭代式视觉增强 (Actor-Critic)**：LLM 作为 Actor 编写绘图代码，VLM 作为 Critic 从数据准确性、标签清晰度、美观度多维度评估 → 生成-评估-修正闭环迭代
- **双阶段写作框架**：先生成 Chain-of-Analysis (CoA) 作为核心洞察，再以 CoA + 原始数据为基础写长篇报告 + 自我反思润色

**战绩**：AFAC2025 冠军（1289 队第一），超越 GPT-5 w/Search、OpenAI Deep Research、Gemini-2.5-Pro Deep Research。报告平均 20,000+ 字，50+ 图表。（注：ICLR 2026 投稿已撤回，但 arXiv 版本 v1 仍可参考其架构设计）

**对本计划的启发**：

- **双阶段写作**模式适用于深度研究 Agent：先产出分析要点（CoA），再扩展为完整报告
- **Actor-Critic 模式**启发了我们的引用校验设计：校验器就是 Critic，但它用确定性程序而非 VLM
- **CAVM 的变量空间理念**与我们的 tool 返回值结构化存储一致——tool 返回值既供 LLM 阅读，也供校验器重算

#### 3. V7 Go Fact-Checking Agent — 商业级金融事实核查产品

**6 步核查流水线**（与本计划引用校验器高度对标）：

1. **Automated Claim Extraction**：从文档中提取所有事实声明、断言、数据点
2. **Cross-Reference Validation**：将每条 claim 与内部知识库、源文档、历史记录交叉验证
3. **Inconsistency Detection**：标记文档内矛盾和与已知事实的冲突
4. **Citation Verification**：验证引用的来源是否真正支持所述声明（检查误引、错引、断章取义）
5. **Data Accuracy Checks**：验证数值、财务数据、日期、统计量（捕获转置错误和计算错误）
6. **Confidence Scoring**：为每条验证结果分配置信度（fully verified / partially supported / unverified）

**输出格式**：Extracted Claims → Verification Status → Supporting Evidence → Confidence Scores → Flagged Inconsistencies → Citation Validation Results → Data Accuracy Assessment → Unverified Claims → Conflicting Information → Recommended Actions

**对本计划的启发**：

- 我们的 `CitationReport` 设计应参考 V7 的输出格式：每条 claim 包含 **verification status + supporting evidence + confidence score**
- **Claim Extraction** 对应我们的 `StructuredReport` 中的 `Claim` 对象
- V7 的 **Cross-Reference Validation** 对应我们的 `computational` claim 重算校验
- **Confidence Scoring** 启发我们：校验报告应量化差异（如 `delta = stated_value - ground_truth`），而不仅是 PASS/FAIL

#### 4. Gradio Agent UI 模式（官方指南实践）

通过 Gradio 官方 Agent 指南（gradio.org.cn/guides/agents-and-tool-usage）确认了以下 UI 模式：

**`ChatMessage`** **+** **`metadata`** **完整字段**：

- `title`：折叠面板标题（如 `"🛠️ 调用工具: query_metric"`）
- `status`：`"pending"` 显示加载指示器且默认展开；`"done"` 默认折叠
- `log`：标题旁的辅助文字（如 API 名称）
- `duration`：执行耗时（秒），显示在标题旁括号内
- `id` / `parent_id`：支持思考步骤嵌套

**工具调用展示**：

```python
ChatMessage(role="assistant", content=step.action.log,
            metadata={"title": f"🛠️ 调用工具: {step.action.tool}",
                      "status": "done", "duration": 0.34})
```

**思考过程展示**（实时更新）：

```python
ChatMessage(role="assistant", content=thought_buffer,
            metadata={"title": "⏳ 思考中", "status": "pending"})
```

**引用展示**：单独的 assistant 消息，折叠面板展示来源：

```python
history.append({
    "role": "assistant",
    "content": "\n".join([f"• {cite}" for cite in citations]),
    "metadata": {"title": "📚 数据溯源", "status": "done"}
})
```

**流式输出**：LangGraph 的 `astream()` + `astream_events()` 支持 token 级流式，Gradio `Chatbot(type="messages")` 原生支持增量更新。**注意**：Gradio 4.x+ 需 `demo.queue().launch()` 才能可靠流式。

**对本计划的启发**：

- 聊天 UI 中 Agent 的工具调用过程用 `metadata={"title": "🛠️ 调用工具: query_metric", "status": "done"}` 展示
- 思考过程用 `status="pending"` 实时展示，完成后切换为 `"done"`
- 深度研究模式的引用校验结果用 `metadata={"title": "📚 数据溯源"}` 折叠展示
- 流式输出使用 `graph.astream()` 替换阻塞 `graph.invoke()`，配合 `demo.queue()`

#### 5. FinGround (arXiv:2604.23588) — 金融幻觉检测与 grounding 的核心学术参考

**三阶段 verify-then-ground 流水线**：

1. **Finance-Aware Hybrid Retrieval**：对文本和表格进行金融感知的混合检索
2. **Atomic Claim 分解 + 六类分类验证**：将 LLM 回答分解为原子 claim，按六类金融分类法（numerical / temporal / entity-attribute / comparative / regulatory / **computational**）路由到不同验证策略，其中 computational claim 使用**公式重算**验证
3. **Grounded Regeneration**：仅重写不支持的 claim，附带段落级和表格单元格级引用

**关键数据**：

- 在 retrieval-equalized 评估下（所有基线获得相同检索结果），atomic verification 额外降低 68-76% 幻觉率（p<0.01）
- 相对 GPT-4o 实现 78% 幻觉率降低
- 8B 蒸馏检测器保留 91.4% F1，单 claim 延迟降低 18 倍，部署成本 $0.003/query
- **计算型 claim 公式重算比 LLM 评审高 +18.9 F1**（这是 ADR-0010 拒绝 LLM-as-Judge 的核心依据）

**对本计划的启发**（ADR-0010 Step 3 的直接学术背书）：

- 我们的 `Claim` 对象应采用六类分类法，特别是区分 `computational` 类型
- `computational` claim 用 `metrics/` 纯函数重算验证，而非 LLM 评审
- `CitationReport` 应支持段落级 + 表格单元格级引用粒度
- 蒸馏小模型思路暂不采用（我们用纯 Python 程序，零幻觉），但未来可考虑

#### 6. VeNRA (arXiv:2603.04663) — 零幻觉神经符号金融推理

**核心架构**：

- **Universal Fact Ledger (UFL)**：严格类型化的结构化事实账本，替代模糊的向量检索。解决「Net Income」与「Net Sales」因语义相近被混淆的问题
- **Double-Lock Grounding 算法**：语义 grounding + 数值 grounding 双重锁定，数学化保证数据正确性
- **LLM 永远不做数学**：Architect LLM 生成确定性 Python trace，3B Sentinel 模型法医级审计执行轨迹
- **Adversarial Simulation 训练**：程序化破坏黄金金融记录来模拟生产级错误（Logic Code Lies、Numeric Neighbor Traps）

**关键数据**：

- 1.2% 幻觉率（接近零幻觉）
- 3B 参数 Sentinel 模型超越 70B+ 模型的错误检测能力
- 28 倍延迟优化

**对本计划的启发**：

- tool 返回值应结构化存储（UFL 理念），校验器从结构化数据重算
- 「LLM 永远不做数学」与 ADR-0010 的设计哲学完全一致
- Double-Lock 思路启发：校验器应同时检查「语义对齐」（claim 描述的字段是否存在）和「数值对齐」（重算值是否匹配）

#### 7. 其他竞品/论文发现

| 竞品/论文                                                                   | 核心机制                                                                                                                      | 对本计划的启发                                                          |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| **FISCAL / MiniCheck-FISCAL** (arXiv:2511.19671, NeurIPS 2025 Workshop) | 7B 参数金融事实核查模型，专注数值型 claim 验证。合成数据训练，单 token 预测 + 可解释置信度。超越 GPT-3.5，接近 GPT-4o/Claude-3.5                                   | 启发：轻量级验证器可行。但本计划用纯 Python 更轻量（零参数），FISCAL 是未来「语义型 claim 验证」的可选增强 |
| **VERAFI** (arXiv:2512.14744)                                           | 神经符号 Agentic 框架，结合密集检索 + cross-encoder reranking + 金融工具 Agent + 自动推理策略（GAAP 合规、SEC 要求、数学验证）。传统检索仅 52.4% 事实正确率，VERAFI 大幅提升 | 启发：合规性验证（GAAP/SEC）可作为未来 tool 扩展。当前先聚焦数值正确性，合规检查是后续 ADR           |
| **FinVet** (arXiv:2510.11654)                                           | Dual RAG + fact-checking，置信度加权投票，source attribution + confidence scores                                                   | 启发：引用校验报告应包含置信度/差异度量化                                            |
| **FINLFQA** (EMNLP 2025)                                                | Clause-level attribution：evidence（支撑段落）+ knowledge（领域知识）+ code（Python 计算片段）                                               | 启发：引用应区分「原始数据来源」和「计算公式来源」                                        |
| **Claude for Financial Services**                                       | MCP 协议实现 Fact Grounding，自动比对 AI 生成值与原始数值。Orchestrator-Subagent + Handoff 机制                                               | 启发：grounding 核心是「AI 说的数」vs「工具返回的数」的程序化比对                         |
| **金融分析师智能体案例** (CSDN)                                                   | 三层幻觉抑制：源头抑制（数据全来自工具）+ 过程抑制（低 temperature）+ 结果校验（输出必须匹配工具返回）                                                               | 本计划的工具调用 + 确定性校验 = 源头抑制 + 结果校验                                   |
| **Aliyun 分析Agent**                                                      | 对话式数据问答 + 报告生成 + 智能解读                                                                                                     | 启发：快速模式的对话式问答体验设计                                                |

### ADR 对齐

| ADR                        | 状态       | 本计划对应                                                                                               |
| -------------------------- | -------- | --------------------------------------------------------------------------------------------------- |
| **ADR-0009** (延后辩论，优先工具重构) | Accepted | 本计划整体就是 ADR-0009 的落地。辩论机制不在本计划范围                                                                    |
| **ADR-0010** (工具使用重构)      | Accepted | 本计划严格遵循 ADR-0010 的三步设计：Step 1 create\_agent + tools → Step 2 reflection middleware → Step 3 确定性引用校验 |
| **ADR-0002** (纯 LLM Agent) | 被修正      | ADR-0010 修正了「纯 LLM」被解读为「无工具」的偏差。本计划将 Agent 从「纯 LLM 消费者」升级为「工具调用者」                                   |
| **ADR-0008** (MCP Server)  | 保持       | MCP Server 保持不变，PREP 子图作为唯一数据入口的设计原则在本计划中通过 tool 复用 PREP 产物来延续                                      |

***

## Proposed Architecture

### 整体架构图

```
用户聊天消息 + 模式选择（快速 / 深度研究）
        │
        ▼
┌─────────────────────────────────────────────────────┐
│                    新 Graph                          │
│                                                      │
│  START → route_by_mode                               │
│    ├── quick_mode ──→ quick_agent ←──→ tools_node    │
│    │                     │                    │      │
│    │                     └──(无 tool_calls)──→ END   │
│    │                                                  │
│    └── deep_research ──→ research_agent ←──→ tools   │
│                              │                │      │
│                              └──(report_ready)→      │
│                                       citation_check │
│                                    ┌──────┴──────┐  │
│                                    │             │  │
│                                 (PASS)         (FAIL)│
│                                    │             │  │
│                              render_report    反馈失败 │
│                                    │         claims  │
│                              export_docx       回到   │
│                                    │         research │
│                                    END        _agent  │
└─────────────────────────────────────────────────────┘
```

### 两种模式设计

#### 快速模式（Quick Mode）

- **定位**：一问一答，轻量级
- **Agent**：轻量 ReAct Agent，绑定细粒度 tools
- **流程**：用户提问 → Agent 决定调哪些 tool → 获取数据 → 直接回答
- **输出**：自然语言回答（含简单来源标注，如「根据 2024 年年报...」）
- **无结构化输出**：不需要 Claim 对象，不需要引用校验
- **无文件导出**

#### 深度研究模式（Deep Research）

- **定位**：产出完整报告，带 grounding 机制
- **Agent**：完整 ReAct Agent，绑定粗粒度 `prepare_financial_data` tool + 细粒度 tools
- **流程**：
  1. Agent 调用 `prepare_financial_data` 获取全量数据
  2. Agent 按需调用细粒度 tools 补充查询
  3. Agent 生成**结构化报告**（Claim 对象列表 + 叙述文本）
  4. **确定性引用校验器**校验所有 Claim
  5. 如有 FAIL → 反馈给 Agent 修正 → 重新校验（最多 3 轮）
  6. 全部 PASS → 渲染最终报告（行内引用 + 溯源附录）
  7. 导出 docx/pptx
- **输出**：完整 Markdown 报告 + docx/pptx 文件

### Tools 设计（粗粒度 + 细粒度混合）

#### 粗粒度 Tool（深度研究模式优先使用）

| Tool 名                   | 签名                                                                | 复用模块                    | 作用                                                      |
| ------------------------ | ----------------------------------------------------------------- | ----------------------- | ------------------------------------------------------- |
| `prepare_financial_data` | `(stock_code: str, peer_codes: list[str] \| None = None) -> dict` | `mcp_server.run_prep()` | 运行完整 PREP 链（cache→fetch→validate→compute），返回全量指标 + 原始数据 |

#### 细粒度 Tools（快速模式 + 深度研究补充）

| Tool 名               | 签名                                                  | 复用模块                                         | 作用                             |
| -------------------- | --------------------------------------------------- | -------------------------------------------- | ------------------------------ |
| `query_metric`       | `(stock_code: str, metric_name: str) -> dict`       | `metrics/*` + `data/akshare_client.py`       | 查询单个指标（如 ROE、资产负债率）的历史值 + 红黄绿灯 |
| `get_stock_quote`    | `(stock_code: str) -> dict`                         | `akshare_client.fetch_stock_quote`           | 实时行情（价格、市值、PE、PB）              |
| `get_key_events`     | `(stock_code: str) -> list[dict]`                   | `events/pipeline.fetch_key_events`           | 关键非财务事件（3 级 fallback）          |
| `decompose_roe`      | `(stock_code: str) -> dict`                         | `metrics/dupont.py`                          | 3 层杜邦分解                        |
| `compare_with_peers` | `(stock_code: str, metric_name: str) -> dict`       | `metrics/relative.py`                        | 同业对比（PE/PB 相对估值）               |
| `get_valuation`      | `(stock_code: str) -> dict`                         | `metrics/garp.py` + `relative.py`            | 估值信息（PE/PB/GARP）               |
| `get_statement_line` | `(stock_code: str, item: str, period: str) -> dict` | `data/akshare_client.py`                     | 查原始报表科目（用于追溯）                  |
| `flag_anomaly`       | `(stock_code: str) -> dict`                         | `metrics/traffic_light.py`                   | 列出所有红灯/异动指标                    |
| `get_health_score`   | `(stock_code: str) -> dict`                         | `metrics/traffic_light.compute_health_score` | 健康度评分（4×25 分）                  |

**Tool 实现策略**：

- 细粒度 tools 通过 `DataCache` 缓存数据，避免重复 AKShare 调用
- 每个细粒度 tool 独立获取所需数据（不强制跑完整 PREP 链）
- 粗粒度 `prepare_financial_data` 复用 `mcp_server.run_prep()` 逻辑
- 所有 tool 返回值通过 `formatters.py` 的纯函数格式化为 LLM 可读 Markdown
- 返回值同时包含结构化数据（供引用校验器使用）

### Grounding 机制设计（ADR-0010 Step 3 落地）

#### 结构化输出

深度研究 Agent 的输出从「自由 Markdown」改为**结构化 Claim 对象 + 叙述文本**：

```python
from pydantic import BaseModel
from typing import Literal

class Claim(BaseModel):
    claim_type: Literal["numerical", "temporal", "entity", "comparative", "regulatory", "computational"]
    field_ref: str           # state 字段路径，如 "solvency_metrics.资产负债率" 或 "dupont_tree.L1.turnover"
    stated_value: float | str
    interpretation: str

class ReportSection(BaseModel):
    title: str
    narrative: str           # 该章节的叙述文本（含行内引用标记 [1], [2]...）
    claims: list[Claim]      # 该章节涉及的所有数据声明

class StructuredReport(BaseModel):
    stock_name: str
    stock_code: str
    sections: list[ReportSection]
    executive_summary: str
```

#### 确定性引用校验器

纯 Python 实现（不调 LLM），可进 CI：

| claim\_type            | 校验方式                                         | 复用模块                                      |
| ---------------------- | -------------------------------------------- | ----------------------------------------- |
| `numerical` / `entity` | `abs(state[field_ref] - stated_value) < tol` | 直接读 state                                 |
| `computational`        | 识别公式 → 取操作数 → 用 `metrics/` 纯函数重算 → 比对        | `metrics/dupont.py`, `profitability.py` 等 |
| `comparative`          | 两侧 numerical 校验 + 比较方向校验                     | 复用 numerical                              |
| `temporal`             | 数值校验 + 时间窗口存在性校验                             | 直接读 state                                 |
| `regulatory`           | 引用存在性（不在本项目数据范围，标 `unverifiable` 跳过）         | —                                         |

**校验流程**：

1. 从 `StructuredReport` 提取所有 `Claim` 对象
2. 对每个 Claim 按 type 校验
3. 产出 `citation_report`：每条 Claim 的 PASS/FAIL/UNVERIFIABLE + 差异值
4. 如有 FAIL：将失败 Claims 反馈给 Agent 修正
5. 全部 PASS（或 UNVERIFIABLE）：渲染最终报告

**行内引用 + 溯源附录**：

- 报告正文中每个数据点后标注来源：`[来源: 2024年资产负债表]` 或 `[来源: metrics/profitability.py ROE计算]`
- 报告末尾附「数据溯源附录」：列出所有 tool 调用记录 + 数据源 + citation\_report 摘要

### Reflection Middleware（ADR-0010 Step 2）

使用 LangChain v1 `@after_model` middleware 在 LLM 每次回复后注入自我审视：

```python
@after_model(state_schema=ResearchAgentState)
def research_reflection(state, runtime) -> dict | None:
    last = state["messages"][-1].content
    result = call_llm(REFLECTION_PROMPT.format(body=last), ...)
    passed = "[REFLECTION_PASSED]" in result
    return {"reflection": result, "reflection_pass": passed}
```

- reflection 是 LLM 自我审视（主观），确定性引用校验是程序比对（客观），两者互补
- reflection 检查「分析是否全面、逻辑是否通顺」，引用校验检查「数据是否正确」

***

## Implementation Phases

### Phase 1: Foundation — LLM + State + Dependencies

#### 1.1 添加 `langchain` 依赖

**文件**: `pyproject.toml`

在 `dependencies` 中添加：

```toml
"langchain>=1.0.0",
```

验证与 `langgraph==1.2.0` 和 `langchain-core==1.4.0` 的兼容性。

#### 1.2 升级 `llm.py` 支持 tool-calling

**文件**: `src/finance_agent/llm.py`

**变更**：

- 保留现有 `call_llm(prompt, system, ...)` 函数不变（非 Agent 路径回退，ADR-0010 明确要求保留）
- 新增 `call_llm_with_tools(messages, tools, tool_choice="auto", ...)` 函数：
  - 接受完整的 `messages` 列表（不是单个 prompt 字符串）
  - 传递 `tools=[...]` 给 `litellm.completion`
  - 返回完整的 message 对象（含 `content` + `tool_calls`），不是 `str`
- 创建 `create_agent` 所需的 thin model wrapper（内部调 `litellm.completion` 并支持 `tools` 透传）

**关键验证**：DeepSeek thinking 模式（`reasoning_effort` + `extra_body={"thinking":{"type":"enabled"}}`）与 tool-calling 的兼容性。`litellm.drop_params=True` 会静默丢弃不支持的参数，需要实际测试验证。如果不兼容，Agent 路径使用非 thinking 模式。

#### 1.3 升级 `state.py` 添加对话支持

**文件**: `src/finance_agent/state.py`

**变更**：

- 添加 `messages: Annotated[list, add_messages]` 字段（LangGraph agent 循环必需）
- 添加聊天相关字段：
  ```python
  # 聊天模式
  mode: str  # "quick" | "deep_research"
  # 引用校验
  structured_report: dict  # StructuredReport 序列化
  citation_report: dict    # 校验结果
  citation_pass: bool
  reflection: str
  reflection_pass: bool
  iteration_count: int     # 引用校验重试次数
  ```
- 保留所有现有字段（PREP 产物、指标、报告等）
- `query` 字段从 dead code 变为活字段（存用户聊天消息）

**关键**：需要从 `typing` 的 `TypedDict` 迁移到支持 `Annotated` reducer 的形式。`messages` 字段的 `add_messages` reducer 是 LangGraph 标准 agent 循环的前提。

### Phase 2: Tools Layer（新建 `src/finance_agent/tools/`）

#### 2.1 创建 `tools/__init__.py`

#### 2.2 粗粒度 Tool: `tools/prep_tool.py`

**文件**: `src/finance_agent/tools/prep_tool.py`

**作用**: 封装完整 PREP 链为一个 Agent 可调用的 tool

**实现**:

- 复用 `mcp_server.run_prep()` 的逻辑（cache → fetch → validate → compute）
- 返回全量指标 + 原始数据（JSON 序列化，DataFrame → records）
- 复用 `mcp_server._serialize()` 处理 pandas 类型
- 失败时返回结构化错误（不抛异常），让 Agent 决定如何处理

```python
from langchain_core.tools import tool

@tool
def prepare_financial_data(stock_code: str, peer_codes: list[str] | None = None) -> dict:
    """获取指定股票的完整财务数据（三大报表 + 全量指标 + 事件 + 行情）。
    用于深度研究模式。会自动缓存。"""
    # 复用 run_prep() 逻辑
```

#### 2.3 细粒度 Tools: `tools/query_tools.py`

**文件**: `src/finance_agent/tools/query_tools.py`

**作用**: 提供按需查询的细粒度 tools（快速模式主力 + 深度研究补充）

**实现要点**:

- 每个 tool 通过 `DataCache` 缓存，避免重复 AKShare 调用
- 查询类 tool（如 `query_metric`）需要先获取报表数据再计算指标
- 数据获取复用 `AKShareClient` 的 lazy singleton 模式（与 `nodes/fetch.py` 一致）
- 指标计算复用 `metrics/` 纯函数
- 返回值同时包含：结构化数据（dict）+ 格式化 Markdown（供 LLM 阅读）

**Tool 列表**（9 个）:

1. `query_metric(stock_code, metric_name)` — 单指标查询
2. `get_stock_quote(stock_code)` — 实时行情
3. `get_key_events(stock_code)` — 关键事件
4. `decompose_roe(stock_code)` — 杜邦分解
5. `compare_with_peers(stock_code, metric_name)` — 同业对比
6. `get_valuation(stock_code)` — 估值信息
7. `get_statement_line(stock_code, item, period)` — 原始报表科目
8. `flag_anomaly(stock_code)` — 红灯/异动
9. `get_health_score(stock_code)` — 健康度评分

#### 2.4 引用校验器: `tools/citation.py`

**文件**: `src/finance_agent/tools/citation.py`

**作用**: ADR-0010 Step 3 的确定性引用校验

**实现**:

- `Claim` Pydantic model（结构化输出）
- `StructuredReport` Pydantic model
- `verify_claims(report: StructuredReport, state: dict) -> CitationReport` 主函数
- 按 claim\_type 分派校验逻辑
- `computational` 类型：用 `metrics/` 纯函数从原始科目重算
- 产出 `CitationReport`：每条 claim 的 PASS/FAIL/UNVERIFIABLE + 差异值 + ground truth 值

**关键设计**:

- 纯 Python，不调 LLM，可进 CI
- 复用 `metrics/dupont.py`, `metrics/profitability.py` 等纯函数做重算
- 容差：原始科目 `tol=0.01`（绝对值），派生指标 `tol=0.5%`（相对值）

### Phase 3: Agent Layer（新建 `src/finance_agent/agents/`）

#### 3.1 创建 `agents/__init__.py`

#### 3.2 快速模式 Agent: `agents/quick_agent.py`

**文件**: `src/finance_agent/agents/quick_agent.py`

**实现**:

- 使用 `langchain.agents.create_agent` 创建
- 绑定细粒度 tools（9 个）
- System prompt：金融分析助手，可回答具体指标问题，回答时标注数据来源
- 不需要结构化输出
- 不需要 reflection middleware
- 轻量级，快速响应

#### 3.3 深度研究 Agent: `agents/research_agent.py`

**文件**: `src/finance_agent/agents/research_agent.py`

**实现**:

- 使用 `langchain.agents.create_agent` 创建
- 绑定粗粒度 `prepare_financial_data` + 全部细粒度 tools
- System prompt：深度研究分析师，产出完整报告
- **结构化输出**：使用 `response_format` 输出 `StructuredReport` 对象
- **Reflection middleware**：`@after_model` 注入自我审视（ADR-0010 Step 2）
- 接收引用校验失败反馈，修正报告

**State schema**（绕开 `create_agent(middleware=, state_schema=)` 互斥限制，ADR-0010 的方案）:

```python
class ResearchAgentState(AgentState):
    reflection: NotRequired[str]
    reflection_pass: NotRequired[bool]
    structured_report: NotRequired[dict]
    citation_report: NotRequired[dict]
    citation_pass: NotRequired[bool]
    iteration_count: NotRequired[int]
```

#### 3.4 Reflection Middleware: `agents/reflection.py`

**文件**: `src/finance_agent/agents/reflection.py`

**实现**:

- `@after_model(state_schema=ResearchAgentState)` 装饰器
- LLM 回复后自动调用一次 LLM 审视输出质量
- 检查：分析是否全面、逻辑是否通顺、是否遗漏关键指标
- 不达标则反馈塞回 messages 触发下一轮
- reflection 检查「主观质量」，确定性引用校验检查「客观数据」

#### 3.5 Prompts: 更新 `prompts/` 目录

**新增文件**:

- `prompts/quick_agent.md` — 快速模式 system prompt
- `prompts/research_agent.md` — 深度研究 system prompt
- `prompts/reflection.md` — reflection 审视 prompt

**保留文件**:

- `prompts/fa_analyze.md`, `ia_analyze.md` — 可作为 research\_agent 的参考素材（Agent 按需引用其中的分析框架）
- `prompts/synthesis.md` — 综合分析仍可能用到

**退役文件**:

- `prompts/fa_summary.md`, `ia_summary.md` — 摘要生成改为 Agent 自主完成

### Phase 4: Graph Restructure

#### 4.1 重写 `graph.py`

**文件**: `src/finance_agent/graph.py`

**新架构**:

```
START → route_by_mode
  ├── "quick"        → quick_agent_node → should_continue?
  │                      ├── "tools"  → quick_tools_node → quick_agent_node (loop)
  │                      └── "end"    → END
  │
  └── "deep_research" → research_agent_node → should_continue?
                         ├── "tools"    → research_tools_node → research_agent_node (loop)
                         └── "citation" → citation_check_node
                                           ├── "pass"    → render_report → export_files → END
                                           └── "fail"    → research_agent_node (with feedback, max 3 retries)
```

**关键变更**:

- 删除 `route_to_agent` 和 `after_agent` 路由函数
- 保留 `after_check_cache` 和 `after_validate` 作为 PREP tool 内部的数据质量门控
- 新增 `route_by_mode`、`should_continue`（检查 tool\_calls）、`after_citation`（检查校验结果）
- PREP 链不再作为固定图节点，而是作为 `prepare_financial_data` tool 的实现
- 使用 `ToolNode` 执行工具调用

#### 4.2 更新 `routing.py`

**文件**: `src/finance_agent/routing.py`

**变更**:

- 删除 `route_to_agent`, `after_agent`
- 保留 `after_check_cache`, `after_validate`（PREP tool 内部使用）
- 新增 `route_by_mode(state) -> str`：根据 `state["mode"]` 返回 `"quick"` 或 `"deep_research"`
- 新增 `should_continue(state) -> str`：检查最后一条 message 是否有 `tool_calls`，返回 `"tools"` 或 `"end"/"citation"`
- 新增 `after_citation(state) -> str`：检查 `citation_pass`，返回 `"render"` 或 `"retry"`

### Phase 5: UI Replacement

#### 5.1 重写 `app.py`

**文件**: `src/finance_agent/app.py`

**新 UI 结构**:

```
gr.Blocks(title="金融AI分析助手")
├─ gr.Markdown("# 金融AI分析助手")
├─ gr.Row()
│  ├─ gr.Column(scale=1)  [侧边栏设置]
│  │  ├─ api_key_input: gr.Textbox (type="password")
│  │  ├─ mode_selector: gr.Radio (["快速问答", "深度研究"], default="快速问答")
│  │  └─ gr.Accordion("高级选项", open=False)
│  │     └─ enable_web_search: gr.Checkbox (default True)
│  └─ gr.Column(scale=3)  [聊天区]
│     ├─ chatbot: gr.Chatbot (type="messages", height=600)
│     ├─ msg_input: gr.Textbox (placeholder="输入消息...")
│     └─ gr.Row()
│        ├─ send_btn: gr.Button("发送", variant="primary")
│        └─ clear_btn: gr.Button("清空对话")
└─ gr.Markdown("⚠️ 报告由AI自动生成...", elem_classes="disclaimer")
```

**关键变更**:

- 用 `gr.Chatbot(type="messages")` 替换 `gr.Markdown` 输出区
- 用 `gr.Textbox` + 发送按钮替换表单提交
- 模式选择从下拉框改为 Radio（快速问答 / 深度研究）
- 文件下载：深度研究模式下，报告生成后在聊天中显示下载链接
- 使用 `graph.astream()` 实现流式输出（替换阻塞的 `graph.invoke()`）
- 股票代码从聊天消息中解析（Agent 自主识别），或通过 `@` 提及指定
- API Key 保留在侧边栏设置中（不交给 Agent 对话）

**事件处理**:

- `send_btn.click → chat_handler(message, history, mode, api_key, ...)`:
  1. 将用户消息加入 history
  2. 构建 state（mode, messages, api\_key 等）
  3. `async for event in graph.astream(state):` 流式更新 chatbot
  4. 如果深度研究模式生成了文件，在最后一条消息附加下载链接
- `clear_btn.click → []`: 清空对话

#### 5.2 保留 `app_search.py`

股票搜索功能保留，但集成方式变化：

- 快速模式下，用户直接输入股票名称或代码，Agent 自主解析
- 可选：在输入框提供 `@` 补全功能（基于 `search_stocks`）

### Phase 6: Report Rendering & Export 适配

#### 6.1 新增 `render_report` 逻辑

**文件**: `src/finance_agent/agents/research_agent.py` 或 `src/finance_agent/tools/citation.py`

**作用**: 将校验通过的 `StructuredReport` 渲染为最终 Markdown 报告

**实现**:

- 遍历 `StructuredReport.sections`
- 每个 section：标题 + 叙述文本（含行内引用标记）
- 在叙述中插入行内引用：`[来源: 2024年资产负债表]` 或 `[来源: ROE计算]`
- 末尾追加「数据溯源附录」：tool 调用记录 + citation\_report 摘要
- 末尾追加免责声明（复用现有 `output.py` 的 `_DISCLAIMER`）

#### 6.2 适配 `export/` 模块

**文件**: `src/finance_agent/export/parser.py` (可能需要小调整)

- Markdown 解析器应能处理行内引用标记
- docx/pptx 导出器不需要大改（它们消费 Markdown）

#### 6.3 适配 `templates/` 模块

**文件**: `src/finance_agent/templates/financial_report.md`, `investment_report.md`

- 模板从固定章节结构改为更灵活的 section 组装
- 或者：Agent 直接生成完整 Markdown，不再使用模板拼接
- 决策：**Agent 直接生成完整报告 Markdown**（结构化 Claim 对象仅用于校验，不用于渲染）。模板退役但保留作为 Agent prompt 参考。

### Phase 7: Testing

#### 7.1 Tool 单元测试

**文件**: `tests/tools/test_prep_tool.py`, `tests/tools/test_query_tools.py`

- 测试每个 tool 的输入输出
- Mock `AKShareClient` 和 `DataCache`
- 验证返回值结构

#### 7.2 引用校验器单元测试

**文件**: `tests/tools/test_citation.py`

- 测试各类 claim\_type 的校验逻辑
- 构造 PASS/FAIL/UNVERIFIABLE 场景
- 验证 computational claim 的重算逻辑
- 使用 `tests/conftest.py` 的现有 fixtures

#### 7.3 Agent 集成测试

**文件**: `tests/agents/test_quick_agent.py`, `tests/agents/test_research_agent.py`

- Mock LLM 返回（模拟 tool\_calls + 最终回复）
- 验证 Agent 循环（tool call → tool result → final answer）
- 验证引用校验重试循环

#### 7.4 E2E 测试

**文件**: `tests/e2e/test_chat_ui.py`

- Playwright 测试聊天界面
- 测试快速模式和深度研究模式
- 验证文件下载

***

## File Change Summary

### 新建文件

| 文件路径                                          | 作用                                   |
| --------------------------------------------- | ------------------------------------ |
| `src/finance_agent/tools/__init__.py`         | Tools 包                              |
| `src/finance_agent/tools/prep_tool.py`        | 粗粒度 prepare\_financial\_data tool    |
| `src/finance_agent/tools/query_tools.py`      | 9 个细粒度查询 tools                       |
| `src/finance_agent/tools/citation.py`         | 确定性引用校验器 + Claim/StructuredReport 模型 |
| `src/finance_agent/agents/__init__.py`        | Agents 包                             |
| `src/finance_agent/agents/quick_agent.py`     | 快速模式 Agent                           |
| `src/finance_agent/agents/research_agent.py`  | 深度研究 Agent                           |
| `src/finance_agent/agents/reflection.py`      | Reflection middleware                |
| `src/finance_agent/prompts/quick_agent.md`    | 快速模式 system prompt                   |
| `src/finance_agent/prompts/research_agent.md` | 深度研究 system prompt                   |
| `src/finance_agent/prompts/reflection.md`     | Reflection prompt                    |
| `tests/tools/test_prep_tool.py`               | Tool 单元测试                            |
| `tests/tools/test_query_tools.py`             | Tool 单元测试                            |
| `tests/tools/test_citation.py`                | 引用校验器测试                              |
| `tests/agents/test_quick_agent.py`            | Agent 集成测试                           |
| `tests/agents/test_research_agent.py`         | Agent 集成测试                           |

### 修改文件

| 文件路径                           | 变更内容                                                                                      |
| ------------------------------ | ----------------------------------------------------------------------------------------- |
| `pyproject.toml`               | 添加 `langchain>=1.0.0` 依赖                                                                  |
| `src/finance_agent/llm.py`     | 新增 `call_llm_with_tools()` + model wrapper，保留 `call_llm()`                                |
| `src/finance_agent/state.py`   | 添加 `messages` + 聊天/校验字段，保留现有字段                                                            |
| `src/finance_agent/graph.py`   | 重写为双模式 Agent 循环图                                                                          |
| `src/finance_agent/routing.py` | 新增 `route_by_mode`, `should_continue`, `after_citation`，删除 `route_to_agent`/`after_agent` |
| `src/finance_agent/app.py`     | 表单 UI → 聊天 UI，阻塞 invoke → 流式 astream                                                      |

### 退役/保留文件

| 文件路径                                      | 处理                                         |
| ----------------------------------------- | ------------------------------------------ |
| `src/finance_agent/nodes/fa.py`           | **退役**：FA 分析逻辑融入 research\_agent + prompts |
| `src/finance_agent/nodes/ia.py`           | **退役**：IA 分析逻辑融入 research\_agent + prompts |
| `src/finance_agent/nodes/merge.py`        | **退役**：综合分析由 research\_agent 直接完成          |
| `src/finance_agent/nodes/cache.py`        | **保留**：PREP tool 内部使用                      |
| `src/finance_agent/nodes/fetch.py`        | **保留**：PREP tool 内部使用                      |
| `src/finance_agent/nodes/validate.py`     | **保留**：PREP tool 内部使用                      |
| `src/finance_agent/nodes/compute.py`      | **保留**：PREP tool 内部使用                      |
| `src/finance_agent/nodes/output.py`       | **改造**：export 逻辑保留，report 渲染逻辑改造           |
| `src/finance_agent/formatters.py`         | **保留**：tool 返回值格式化                         |
| `src/finance_agent/mcp_server.py`         | **保留**：MCP Server 不变                       |
| `src/finance_agent/metrics/*`             | **保留**：纯函数不变，tool 和校验器复用                   |
| `src/finance_agent/data/*`                | **保留**：AKShareClient 和 DataCache 不变        |
| `src/finance_agent/events/*`              | **保留**：事件管线不变                              |
| `src/finance_agent/export/*`              | **保留**：导出管线不变                              |
| `src/finance_agent/prompts/fa_analyze.md` | **保留为参考**：research\_agent prompt 引用其分析框架   |
| `src/finance_agent/prompts/ia_analyze.md` | **保留为参考**：同上                               |
| `src/finance_agent/templates/*`           | **退役**：Agent 直接生成完整 Markdown               |

***

## Assumptions & Decisions

### 关键假设

1. **DeepSeek tool-calling 兼容性**：DeepSeek 通过 OpenAI 兼容 API 支持 function calling。但 thinking 模式（`reasoning_effort` + `extra_body`）与 tool-calling 可能互斥。**验证方案**：Phase 1 中实际测试，如不兼容则 Agent 路径使用非 thinking 模式（`LLM_THINKING=disabled`）。
2. **`langchain>=1.0`** **与** **`langgraph==1.2.0`** **兼容性**：ADR-0010 指出需确认。`create_agent` 在 `langchain.agents` 中。**验证方案**：Phase 1 中 `uv add langchain` 后运行现有测试确认无破坏。
3. **`create_agent`** **+ middleware +** **`state_schema`**：ADR-0010 引用 GitHub #33217 的互斥限制，并提供绕开方案（装饰器级 `state_schema`）。**验证方案**：Phase 3 中实际测试 `@after_model(state_schema=...)` 是否工作。
4. **结构化输出（`response_format`）与 tool-calling 共存**：DeepSeek 可能不支持同时使用 `response_format` 和 `tools`。**备选方案**：如不兼容，Agent 先通过 tool\_calls 完成数据获取，最后一轮不传 tools 只传 `response_format` 输出结构化报告。

### 设计决策

1. **PREP 作为 tool 而非固定图节点**：用户明确要求「把 PREP 模块整体封装成一个 tool」。ADR-0010 原文说「PREP 子图保持不变，Agent 只在 PREP 完成后的 state 上做推理」。本计划调整为：PREP 作为 `prepare_financial_data` tool 供 Agent 按需调用，细粒度 tools 可独立获取数据（快速模式不强制跑完整 PREP）。这是对 ADR-0010 的合理演进 —— ADR-0010 没有考虑聊天 UI 和两种模式的需求。
2. **FA/IA 节点退役**：当前 `fa.py`/`ia.py` 的 3 阶段生成（body → summary → template）被 Agent 的 ReAct 循环替代。分析逻辑通过 system prompt 和 tools 保留。模板组装退役（Agent 直接生成完整 Markdown）。
3. **引用校验为确定性程序，非 LLM Agent**：用户称之为「critic agent」，但 ADR-0010 明确反对 LLM-as-Judge（「脆弱链，评审 LLM 自己也会幻觉」）。本计划的引用校验器是纯 Python 程序，复用 `metrics/` 纯函数重算。用户说的「通过 compute metrics 反推」正是此意。
4. **行内引用 + 溯源附录**：用户选择此项。报告正文中每个数据点标注来源，末尾附 tool 调用记录 + citation\_report 摘要。
5. **完全替换表单 UI**：用户选择此项。旧表单删除，API Key 保留在侧边栏设置。
6. **股票代码从聊天消息解析**：Agent 自主识别用户消息中的股票名称/代码（类似 ChatGPT 识别实体）。不再需要搜索框 + 下拉选择。

### 不在本计划范围

- **多 Agent 辩论**（ADR-0009 延后项）：Trust/Skeptic/Leader 辩论机制待工具使用 + grounding 落地后再评估
- **RAG 向量库**：Chroma 研报 RAG 是后续 ADR
- **LangSmith / Langfuse 可观测性**：独立关注点，不影响本计划架构
- **Human-in-the-loop 审批**：后续 ADR
- **DCF 绝对估值**：v2.0 功能，可作为新 tool 添加

***

## Verification Steps

### Phase 1 验证

1. `uv add langchain` 后运行 `uv run pytest tests/ --ignore=tests/e2e -x -q` 确认无破坏
2. `uv run python -c "from langchain.agents import create_agent; print('OK')"` 确认 API 可用
3. `uv run python -c "from finance_agent.llm import call_llm_with_tools; ..."` 测试 tool-calling 实际调用 DeepSeek

### Phase 2 验证

1. 每个 tool 单独测试：`uv run pytest tests/tools/ -v`
2. Mock AKShareClient，验证 tool 返回值结构
3. 验证 `prepare_financial_data` 能正确复用 PREP 链

### Phase 3 验证

1. `uv run pytest tests/agents/ -v`
2. Mock LLM 返回（模拟 tool\_calls），验证 Agent 循环
3. 验证引用校验器对 PASS/FAIL 场景的正确判断
4. 验证引用校验重试循环（FAIL → 反馈 → 修正 → PASS）

### Phase 4 验证

1. `uv run python tests/scripts/gen_graph_mermaid.py` 生成新图拓扑
2. 验证两种模式的路由正确性

### Phase 5 验证

1. `uv run python -m finance_agent.app` 启动聊天 UI
2. 手动测试快速模式：输入「茅台的 ROE 是多少」→ 验证 Agent 调用 `query_metric` → 返回带来源标注的回答
3. 手动测试深度研究：输入「全面分析茅台」→ 验证 Agent 调用 `prepare_financial_data` → 生成结构化报告 → 引用校验 → 导出 docx
4. `uv run pytest tests/e2e/ -v`（Playwright E2E）

### 全量验证

1. `uv run ruff check src/ tests/`
2. `uv run ruff format --check src/ tests/`
3. `uv run mypy src/`
4. `uv run pytest tests/ --ignore=tests/e2e -x -q`

