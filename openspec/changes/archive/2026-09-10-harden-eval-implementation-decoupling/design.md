# Design: harden-eval-implementation-decoupling

## Context

四项「评估与实现同源」风险需解除/锚定。核心原则：**同源不可怕，可怕的是各自维护一份副本**——允许集、词典、结算逻辑都应只有一个权威点（注册表/冻结版本/production 实现），评估侧引用而非复制。

## Approach

1. **工具注册表（tool_registry.py）**：`AGENT_TOOL_NAMES = frozenset({"web_search","batch_web_search","search_stock","run_deep_analysis"})` 为唯一权威；`agent_factory` 的 `_trace_tool("web_search")` 等注册名改用常量（字符串字面量保留但以 registry 为准）；`toolcall/measure.py` 默认 `DEFAULT_ALLOWED_TOOLS = AGENT_TOOL_NAMES`（保留 `allowed` 参数覆盖）。测试：扫描 `agent_factory` 注册名 ⊆ registry，registry ⊆ 实际注册名（双向一致）。
2. **section 词典冻结**：`sections.py` 加 `SECTION_SYNONYMS_VERSION = 1`；`tests/evals/test_sections.py` 冻结测试锁定 `SECTION_SYNONYMS` 快照（dict 序列化比对）；prompt 交叉测试：正则扫 `prompts/*.md` 的 `## 章节` 标题词，未被词典任一 value 覆盖时红（覆盖不了的英文标题词显式列入 allowlist）。
3. **幻觉率真值 source**：`evals/hallucination/measure.py` 校验 `data_map.get("source")`，缺失则打印错误退出；CLI `--data` 文件要求含 source。测试：无 source → 拒绝。
4. **settle golden 判例**：golden schema TYPES 加 `settlement_rule`；样本 `g-fin-0301-0303`（止损触发/目标触发/超期）用简化行情序列 + 决策 + 人工裁决；`gates.py` 加 `judge_settlement(decision, bars, expected)`——构造 `evaluate_decision` 所需输入（从 `tests/outcome/test_settle.py` fixture 借行情构造方式），比对关键结算字段。golden `run_entries` 支持新类型。

## Alternatives Considered

- **toolcall 允许集从 trace 学习**：过度设计，注册表即权威源足够。
- **settle 判例放 tests 而非 golden**：golden 是「人工裁决 + 可审计」的家，与事故回归同层，放 golden 统一 gate。

## Risks

- **风险 1：prompt 交叉测试过严（英文章节词无词典）**。对策：allowlist 显式放行已知英文/特殊标题，其余必须入词典。
- **风险 2：settle 判例行情构造与 production 不一致**。对策：判例用「简化但确定」的合成行情（单边趋势/单根大阴/一字板），`evaluate_decision` 输入契约从 test_settle fixture 对齐。
- **风险 3：registry 与 agent_factory 扫描不一致导致 CI 抖动**。对策：双向断言 + registry 变更走显式提交。