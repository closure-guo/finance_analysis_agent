# Proposal: harden-eval-implementation-decoupling

## Why

构造性一致/同源风险清查（前序分析）剩余四项评估资产与实现共享规则或共享数据源，导致「尺子与被测物一起长、无法发现规则本身变化」：① toolcall 评估允许集硬编码、与 agent 工具注册漂移；② 幻觉率真值可能与报告同一抓取管道（同源自证）；③ section_coverage 同义词词典与 prompt 章节命名同仓共同演化；④ settle 结算规则无独立 golden 判例。本 delta 将四项评估与实现的耦合解除/锚定。

## What Changes

- **toolcall 允许集解耦**：新增 `src/finance_agent/tool_registry.py` 权威工具名集合，`agent_factory` 注册名与 `toolcall/measure.py` 默认允许集均从它派生（参数 override 保留）
- **幻觉率真值独立快照标注**：`data_map` 文件必须带 `source`（快照来源/时点），缺 source 拒绝测量；真值来源与报告数据管道解耦的约定
- **section 词典冻结**：`sections.py` 加 `SECTION_SYNONYMS_VERSION`；冻结测试锁定词典内容；prompt 章节词与词典的交叉一致性测试（prompt 新增章节词而词典未覆盖 → 红）
- **settle 结算 golden 判例**：golden 集新增 `settlement_rule` 类型样本（止损/目标/超期判定 vs 人工裁决），gate 增加 settle 判定器复用 `evaluate_decision`

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `assertion-golden-set`: TYPES 增加 `settlement_rule`；gate 增加 settle 判定
- `agent-evaluation-suite`: toolcall 允许集 SHALL 从权威工具注册派生（评估与实现同源但同源点是注册表而非各写各的）
- `evaluation`: section 词典 SHALL 冻结版本并接受 prompt 变更回归测试；幻觉率真值 SHALL 带独立快照来源

## Impact

- 新增 `src/finance_agent/tool_registry.py`
- `evals/toolcall/measure.py`、`evals/sections.py`、`evals/hallucination/measure.py`、`evals/golden/schema.py`、`evals/golden/gates.py`
- `src/finance_agent/agent_factory.py`（注册名引用 registry）
- 样本：golden 集新增 settle 判例 3-5 条
- 测试：toolcall/sections/hallucination/golden