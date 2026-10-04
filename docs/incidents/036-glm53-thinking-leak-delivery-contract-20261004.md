# Incident 036: 纯文本交付物零契约——glm-5.3 思考独白原文进报告「研究聚焦」段

**日期**: 2026-10-04
**状态**: 已修复（delta `add-output-contract-guard` 已实施，PR #221 合并 + 部署 + 拓荆真实验证收口，见 `tests/validation/2026-10-04-add-output-contract-guard-validation.md`）
**关联**: [017（同根因：reasoning 吃满 max_tokens）](017-ark-glm-reasoning-token-starvation.md)、[019（截断治理）](019-llm-output-truncation-governance.md)、[001（LLM 输出失真）](001-llm-hallucination-20260601.md)、PR #215-#219（LLM_* 切 bigmodel glm-5.3）

## 症状

第五版拓荆科技报告（`reports/拓荆科技_688072_20261004_171013_report.md`）开篇「研究聚焦」段是模型的英文内部独白，草稿在 "PE_ttm 85." 处中途截断：

> The user wants a 150-200 character (Chinese characters) research focus summary
> for 拓荆科技 (Piotech), synthesizing the analysis outputs. Key points to weave
> in: ... Important constraint: ... Draft:
>
> "综合裁决为中性（置信度0.50）……PE_ttm 85.

同报告另有两处伴生缺陷（第五轮评审发现并经核实）：
- 正文「合同负债48.52亿元」与快照 51.31 亿打架——查无出处的虚构数字逃逸进交付物
- 置信度 0.50→0.50→0.60→0.70 逐级通胀；fund_manager span 尾部同样泄露独白
  （"Confidence drift: 0.7 vs 0.6, deviation 0.1 < 0.15 … Let me finalize the
  JSON."），仅因 JSON 解析器挡住而未进交付物

## 根因（四层叠加）

1. **模型行为**：glm-5.3 在 content 通道输出任务独白+草稿而非仅最终摘要。
   **间歇性**：同日 14:49 中远海能报告（同模型）干净；14:25 拓荆 run 的
   report span 同样泄露（未活到交付）。换模型以来 3 次摘要调用泄露 2 次。
2. **预算挤占**：`_build_focus_summary` 传 `max_tokens=400`，Langfuse usage
   显示 output 恰为 400 整——英文独白吃满预算，草稿截断。`complete_text`
   内置续写（`llm-output-resume`：finish_reason=length → 续写）但未触发；
   finish_reason 未入观测 metadata 无法确证（疑端点报 stop），属遥测缺口。
3. **零校验直通**：`src/finance_agent/nodes/report.py:330-343` 拿到响应仅
   `.strip()` 即 verbatim 嵌入 `## 研究聚焦\n\n{summary}`，无任何格式校验。
4. **raw_reasoning 回退坑**：report.py:340 `resp = text or
   meta.get("raw_reasoning") or ""`——content 为空时**主动**把 reasoning
   当交付文本（legacy 行为保留）。对思考型模型是等着引爆的设计。

## 为什么 017/019 治理没拦住

017（方舟 GLM reasoning 吃满 max_tokens）修在**预算派生层**，019 治理
（resume/续写）修在**完整性层**——都在网关。续写救的是「截断」，救不了
「内容本身违约」：就算续写成功，交付的仍是泄露独白的加长版。
`llm-output-contract` spec 只覆盖 JSON 结构化路径（extract_json → Pydantic
→ repair），纯文本直通交付物的路径不在契约内。

## 处置

1. OpenSpec delta `add-output-contract-guard`：`llm-output-contract` 新增
   「纯文本交付物输出合同」——泄露模式/非目标语言占比/句中截断的确定性校验，
   命中定向重试，重试仍违约回退结构化拼接；禁止 raw_reasoning 作为交付回退
2. `complete_text` 观测 metadata 补 `finish_reason`/`resume_count`（截断归因）
3. 流程纪律：换模型先跑固定回归集（拓荆五版历史输入）对比输出再进生产
4. P1（独立 delta，未立项）：数字逃逸扫描（正文数字 vs 快照交叉核对）；
   置信度漂移阈值 0.15 → 0.05 或强制对齐 RM 值

## 教训

- 输出契约层此前全靠旧模型「自觉」遵守格式——换模型即裸奔。确定性校验
  （泄露模式/语言占比/截断）不依赖模型自觉，是契约该兜的底
- 结构化合同只护 JSON 路径；「LLM 文本直接进交付物」是同等风险的裸奔面，
  必须同权重设防
- 伴生缺陷（48.52 亿、置信度通胀）与泄露同源于「交付前无确定性交叉核对」，
  修契约时一并设计，但按归因桶分开立项（026 纪律）
