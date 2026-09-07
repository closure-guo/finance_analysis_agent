# Design: ehr-style-claim-direction

## Context

EHR 细粒度校验（arXiv 2512.16189）把断言表达为命题元组 p=(e,a,v,t) + 否定/方向独立申报，比对在元组层完成，不依赖校验时文本推断。本项目 Claim 现有字段体系源于迭代累积：field_ref（解析指针）、stated_value/_b（值）、metric_name/period（harden-citation-semantic-coverage 增补）、claim_type/source_type/interpretation（初代）。分桶报告实证：新时代 FAIL 主因 semantic_term_mismatch（73.7%），方向语义靠 11 词方向词表在普查侧从文本猜（残留风险 2.22%）。

## Goals / Non-Goals

**Goals**
- direction 成为 claim 的一等字段（EHR 元组的第五元），校验在元组层完成
- 方向词表降级为未申报兜底并冻结词表（补 3 词后不再扩）
- claim 字段体系按 EHR 语义建立可读映射文档（entity/attribute/value/time/direction ↔ 现有字段）

**Non-Goals**
- 不重命名/删除任何现有字段（解析指针 field_ref 是机器契约，改名会破坏 benchmark/trace 兼容；只做语义映射文档）
- 不动 metric_vocab.py 词表契约（单一词表红线不变）
- 不改 claim_benchmark v1.1 冻结基准（direction 是新增校验分支，基准测的是既有校验器准度）

## Decisions

1. **加字段而非改字段**：direction 新增为 `Literal["positive","negative","flat"] | None`。None = 旧格式，显式降级计覆盖缺口——复用 metric_name/period None 的既有先例，旧 trace/旧 benchmark 数据零迁移。
2. **新桶 direction_mismatch 与 value_mismatch 同级**：进入定向重试目标（数值对了方向错了，最值得打回修正的类别）。不计入 internal_inconsistency 复用，保持分桶报告口径连续。
3. **方向词表兜底只降级不删除**：D2/D4 自动补登记的 claim 无法申报 direction（机器补的），必须保留文本兜底路径，否则 coverage 普查大面积回退。补 3 词后冻结，扩张须走评估依据。
4. **sign 语义**：`direction="negative"` 表示「正文以正向数值表述负向事实」；判定式 `sign(stated_value) * (1 if direction=="positive" else -1 if direction=="negative" else 0) == sign(ground_truth)`，flat 时跳过符号检查。comparative 的基期端（stated_value_b）本期不做方向检查（真值符号语义未定义，留待后续 delta）。

## Risks / Trade-offs

- prompt 增加 direction 必填 → 模型申报负担 +1，短期可能推高 path/semantic 桶误报（申报错误取代方向词误报）→ 用分桶脚本复测归因
- 方向词表兜底与 direction 双路径并存 → 匹配语义二义（申报了 direction 的 claim 正文方向词不命中怎么办）→ 规格已定：已申报 claim 不走词表，杜绝双判
