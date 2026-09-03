## Why

`citation_coverage` 首跑（harden-citation-semantic-coverage 归档后）经 20 条人工终裁（2026-09-02，验证报告附录 A）暴露两类问题：**普查自身噪声**——模板/脚手架文本、方向词符号、约数、阈值式复述被误判为黑数字（约 9 条本应 accept）；**纪律缺口未有效收口**——state 可校验数字（anomalies/比较基期/可重算计算值）因 LLM 未申报而裸奔（7 条 + 1400亿）。另确认**无一条为编造错误数字**，工具抓到的主要是噪声与漏登记。v3 的目标：让普查信号干净、让可校验数字不再裸奔，且不降低验证标准。

## What Changes

- **普查规则修正（噪声消除）**：
  - 排除模板/脚手架结构性文本（position_size 档位说明等）；
  - 方向词（下滑/下降/增长/上升）语境下符号不敏感匹配；
  - 容差 0.5% → 2%（普查是召回工具不是裁判）；
  - 「超/约/近 X」阈值式复述按不等式匹配。
- **补 claim 机制（纪律收口，验证标准不降）**：
  - state anomalies 确定性自动补登记：数值 + 指标名同句共现 且 state 可定位真值 → 自动生成 claim；取整感知容差（|stated−truth| ≤ 0.5 个百分点）；field_ref 指向结构化真值（growth_rates.{dim}.{metric}），字符串只定位不验证（防循环验证）；
  - comparative 基期值强制走 field_ref_b/stated_value_b 双端建档；
  - 可重算计算值（如 FCF 同比）补 computational claim；
  - 事件数字（新闻/公告）豁免纪律：不建数值 claim，正文内联注明来源，普查标记 event_covered 而非 unmatched。

## Capabilities

### New Capabilities
- （无新增 capability；全部归入既有 citation-verification）

### Modified Capabilities
- `citation-verification`: coverage 普查口径（豁免清单/容差/符号/不等式/事件标记）与 claim 补登记契约（anomaly 自动补登记、comparative 基期 field_ref_b、computational 补建、event_covered 豁免）

## Impact

- `src/finance_agent/citation_coverage.py`（普查正则/容差/符号/豁免）
- `src/finance_agent/citation_node.py` 或新补登记模块（anomaly 自动补 claim）
- `src/finance_agent/nodes/compute.py`（anomalies 结构化来源，只读）
- `src/finance_agent/models.py`（DebateMessage/Claim：comparative field_ref_b 启用）
- `src/finance_agent/citation.py`（comparative 基期校验语义）
- prompt（analysts：比较值双端申报、事件来源内联）——改动后需 `deploy_prompts.py` 发布
- 测试：citation_coverage / citation / citation_node / anomaly 补登记 fixtures
- 评估：spotcheck 生成器重跑（tests/scripts/coverage_spotcheck_material.py），A/F/E 类应消失
