# Design: redesign-pipeline-hierarchical-timeline

## Context

前置 delta `fix-pipeline-banner-and-eta` 落地后，事件流已完备：每个图节点均有 node_start/node_complete 对、节点级计时、动态 ETA。本 delta 解决的是**信息架构**问题：现有 6 阶段圆点把 21 个图节点压成 6 个状态点，Layer I 的 4 并行分析师、Layer II/IV 的多轮串行辩论全部不可见。

经方案讨论（分层时间轴 vs 泳道图 vs 极简进度条），选定**分层时间轴**：

- 与现有卡片+聊天流风格一致，改动可控
- 直接暴露"当前在哪个子节点、运行多久"，消除"Layer II 卡住"的感知
- 为未来辩论层并行化预留视觉表达空间

现状约束：Layer I 的 4 个分析师通过 LangGraph Send 扇出并行执行，`graph.stream` 的 updates chunk 中 4 个分析师结果可能合并到达，事件层需能区分 4 个并行子节点。

## Goals / Non-Goals

**Goals:**

- 6 层 layer 节点 + 可展开子节点列表的分层时间轴，状态图标/耗时/当前高亮齐全
- Layer I 4 个分析师按各自真实事件独立驱动状态，修复摘要文案错位
- 当前活跃节点内联显示实时思考摘要（单行预览），点击展开完整 timeline
- 自动滚动定位当前运行节点

**Non-Goals:**

- 不改后端图结构、节点编排、LLM 调用逻辑
- 不改报告渲染区与对话流 UI
- 不做泳道图/甘特图
- 不做辩论层并行化（incident 008 架构项）

## Decisions

### D1: 组件结构

**决策**：新增 `frontend/src/PipelineTimeline.tsx` 独立组件，取代 `App.tsx` 中 `PipelineCard` 的进度区（Layer I 卡片区与日志折叠区保留并适配）。组件树：

```
PipelineTimeline
├─ LayerRow (×6)              — 状态图标 + 层名 + 层耗时 + 展开箭头
│   └─ NodeRow (×N, 可展开层)  — 状态图标 + 角色名 + 节点耗时/已运行时长
│       └─ InlineThinking     — 当前节点单行实时摘要 / 点击展开完整 timeline
└─ EtaRow                     — 已用时 + 预估剩余（复用上一 delta）
```

**备选**：直接在 App.tsx 内联扩展 PipelineCard——被否决，App.tsx 已超 1600 行，新组件独立可测。

### D2: 状态模型

**决策**：前端维护 `layerTree: LayerNode[]`，每个 LayerNode 含 `status`、`startedAt/completedAt` 与 `children: NodeState[]`。node_start/node_complete 事件驱动纯函数 `applyNodeEvent(layerTree, event)`（放 `timeline.ts` 或新 `pipelineTree.ts`），组件纯渲染。状态单调流转：pending→running→completed/failed。

Layer→子节点映射表（前端静态配置，与后端 LAYER_STEPS 对齐）：

- PREP: check_cache, fetch_data, compute_metrics, validate_financials, verify_citations
- Layer I: fundamental_analyst, technical_analyst, macro_analyst, sentiment_analyst（并行）
- Layer II: bull_r1, bear_r1, bull_r2, bear_r2, research_manager
- Trader: trader
- Risk: aggressive_r1, neutral_r1, conservative_r1, risk_judge（或按实际图节点）
- Fund: fund_manager

### D3: Layer I 并行事件拆分

**决策**：后端在 `graph.stream` 迭代中，当 updates chunk 的键包含并行分析师函数名（或 LangGraph 的 task id）时，为每个分析师单独发 node_start/node_complete，节点 ID 用图节点名（如 `fundamental_analyst`）。`api.py` 的 `LAYER_STEPS` 相应扩展为 21 节点全量映射（现状已有），前端映射表与其对齐。

**备选**：事件携带 `parent: layer1` + 子标签——被否决，直接用语义化节点 ID 更简单，且与 thinking_token 的 node 字段天然对齐。

**兼容性**：若个别 chunk 无法拆分到具体分析师，回退为整层 node_complete（前端整层标记完成），不阻塞。

### D4: 展开/折叠默认值

**决策**：当前运行层自动展开，已完成层默认折叠（显示层摘要行），未来层折叠。用户手动展开/折叠的偏好覆盖默认，单次会话内记忆。Layer I 期间默认展开（4 卡片是本设计核心卖点）。

### D5: 思考摘要内联

**决策**：当前 running 节点的 NodeRow 下方内联一行最新思考文本（取该节点 thinking item 末尾 80 字符，流式更新，等宽截断），点击 NodeRow 展开该区域渲染完整 TimelineRenderer。已完成节点的 timeline 折叠，保留"查看思考"入口。

### D6: 自动滚动

**决策**：当前运行节点变化时，`scrollIntoView({block:'nearest', behavior:'smooth'})`；若用户最近 3s 内有手动滚动交互则暂停自动滚动（避免拉扯）。

## Risks / Trade-offs

- [Layer I 并行 chunk 拆分依赖 LangGraph stream 输出细节，版本升级可能变化] → 拆分逻辑集中一处并配单测；无法拆分时回退整层完成
- [层级展开内容多导致消息卡片过长] → 默认折叠已完成层；当前节点摘要仅单行
- [与旧会话历史数据（无节点级事件）渲染兼容] → 历史会话无 layerTree 数据时回退渲染旧版摘要（或仅显示 6 层终态），不报错
- [21 节点全部展示信息过载] → 层折叠机制 + 角色名中文化（NODE_DISPLAY_NAMES 复用）

## Migration Plan

前端组件替换为增量部署。后端事件拆分先行（对旧前端无害：旧前端按 node_complete 的 progress 字段更新，额外事件被忽略）。新旧 UI 切换无需 feature flag——直接替换，E2E 验证。

## Open Questions

- Layer I 分析师卡片的"摘要文案"（如"宏观分析完成"）是否保留在新 NodeRow 中，还是由节点耗时+状态图标取代？→ 倾向保留一句话摘要，由 node_complete 的 content 提供，实施时确认。
