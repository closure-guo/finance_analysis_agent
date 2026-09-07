# Proposal: ehr-style-claim-direction

## Why

citation_fail 分桶报告（reports/citation-fail-bucket-report-20260905.md）实证两个问题：
① 新时代 FAIL 主因是 semantic_term_mismatch（73.7%），根因之一是 claim 缺 direction 独立字段——校验器被迫从正文文本猜方向（11 词方向词表为过渡态补丁，语料实证残留风险 2.22%）；② claim 字段体系（field_ref/field_ref_b/stated_value/stated_value_b/metric_name/period）命名与语义混杂，建模者难以理解。工业界定量域先进实践（EHR 细粒度校验，arXiv 2512.16189）将断言表达为 entity/attribute/value/time 四元组 + 否定/方向独立申报，方向不靠校验时文本推断。

## What Changes

- **BREAKING**：Claim 模型重组为 EHR proposition 风格五元组语义（不删除现有字段，新增+重命名别名过渡）：
  - 新增 `direction: Literal["positive","negative","flat"] | None = None`——数值型/计算型 claim 必填申报方向（None = 旧格式降级，校验器跳过方向检查并计覆盖缺口，显式不静默）
  - 现有字段保留为解析层机器指针，文档按 EHR 语义重命名映射：entity=标的（隐含）+ attribute=`metric_name`+`field_ref`、value=`stated_value`（+`stated_value_b` 基期）、time=`period`、direction=新增
- 校验器方向检查：direction 已申报时，`sign(stated_value) × direction == sign(ground_truth)` 方向不符 → FAIL（新桶 `direction_mismatch`）
- 方向词表规则（`citation_coverage.py` _DIRECTION_WORDS 11 词）**退役为兜底**：仅当 claim 未申报 direction 时才启用文本推断；补负增长/跌幅/收窄 3 词（语料 Top 漏网）
- 分析师 prompt（fundamental/technical/sentiment/debaters）加 direction 申报纪律并 `deploy_prompts.py` 发布
- D6 打回反馈携带 direction 申报提示

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `citation-verification`: Claim 结构新增 direction 申报；方向一致性校验新桶 direction_mismatch；方向词表降级为未申报时的兜底
- `agent-prompt-contracts`: 分析师 prompt 的 claim 申报纪律新增 direction 必填（数值型/计算型）
- `citation-retry-policy`: 定向重试反馈模板携带 direction 申报提示（D6 打回与 value_mismatch 重试共用）

## Impact

- 影响文件：`src/finance_agent/citation.py`（Claim 模型 + 校验逻辑）、`src/finance_agent/citation_coverage.py`（方向词兜底降级 + 3 词）、`src/finance_agent/nodes/citation_node.py`（打回反馈）、4 个分析师 prompt、`metric_vocab.py`（不动，词表契约不变）
- 兼容性：direction=None 的旧 claim 不报错，走兜底词表路径并计覆盖缺口（对齐既有 metric_name/period None 的显式降级先例）
- 评估影响：claim_benchmark v1.1 冻结基准不受影响（基准只测校验器准度，direction 检查是新增分支）；CI 门禁照常
- E2E 门禁：不适用（无前端 UI/SSE/会话状态变更）
