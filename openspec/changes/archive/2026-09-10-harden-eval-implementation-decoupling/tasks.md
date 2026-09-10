# Tasks: harden-eval-implementation-decoupling

## 1. 工具注册表解耦

- [x] 1.1 新建 `src/finance_agent/tool_registry.py`（AGENT_TOOL_NAMES + 单名常量）
- [x] 1.2 `agent_factory` 6 处注册名引用 registry 常量；`toolcall/measure.py` 默认允许集 = `AGENT_TOOL_NAMES`（保留 allowed 参数覆盖）
- [x] 1.3 双向一致性测试（注册名 ⊆ registry ⊆ 注册名，扫描 agent_factory 常量引用）

## 2. section 词典冻结

- [x] 2.1 `sections.py` 加 `SECTION_SYNONYMS_VERSION`；冻结测试锁定 keys+版本、同义词非空不重复
- [x] 2.2 dataset must_cover ⊆ 词典 + prompt 章节词交叉一致性测试；**实测发现词典缺「舆情」，已补同义词**（bad case 驱动追加范例）

## 3. 幻觉率真值 source 校验

- [x] 3.1 `require_data_source`：data_map 缺 source 拒绝测量（ValueError）；CLI 与 run_offline 均生效
- [x] 3.2 既有幻觉率测试 data_map 全部补 source（snapshot:test）；新增 source 校验测试 3 条

## 4. settle golden 判例

- [x] 4.1 golden schema TYPES 加 `settlement_rule`；样本 `g-fin-0301-0303`（止损 hit_stop/目标 hit_target/超期 expired，自包含 decision+kline+人工裁决）
- [x] 4.2 `gates.judge_settlement` 复用 production `evaluate_decision` 复算（唯一来源）；run_entries 支持新类型；测试对照 3 判例

## 5. 回归

- [x] 5.1 evals 全量 391 绿（新增 tool_registry/sections_frozen/hallucination_source/settlement 测试）+ ruff clean
- [x] 5.2 golden gate 本机 13/13 PASS、exit=0；`openspec validate --strict` 通过