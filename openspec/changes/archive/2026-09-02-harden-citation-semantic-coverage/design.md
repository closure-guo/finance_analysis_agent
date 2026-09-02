# Design: harden-citation-semantic-coverage

## Decisions

### D1: 覆盖率先做"数字普查"，不做"语义覆盖率"

ALCE 的 Citation Recall 用语义判断"每句话是否被引用支撑"。本系统只实现其确定性近似：从 markdown 正文正则提取数值（含百分比/金额/倍数形态，归一化"约 45%"/"45.2%"→ 45.2），逐一对照全部 claim 的 stated_value（容差内视为已认领）。

- **为什么够用**：本系统的幻觉风险集中在数值（claim 分布数值+计算型占 45%+），定性表述的覆盖率由 L2 judge 抽检承担；
- **豁免清单**：编号类（"三大报表""5 层架构"）、评级刻度、页码不计入普查，豁免规则进 fixture 测试钉死；
- **阈值**：`citation_coverage` 只监控告警（默认 <0.8 告警），不进 after_citation 路由——首版只观察不拦截，避免覆盖率口径未稳定前误伤管线。

### D2: 术语一致性用枚举 + 字符串恒等检查，不上 NLI

前提已成立：Bug B 修复后 context 标注、state 键、field_ref 同一词表。`metric_name` 从指标枚举（metrics 注册表键 + 中文别名映射）选择，校验规则：`metric_name` 解析到的规范键必须等于 field_ref 末端键。

- **为什么不上 NLI**：证据是结构化的，词表已统一，语义问题被设计收敛为字符串问题；引入模型反而带来 88-91% 的判定误差和不可解释性；
- **逃逸残余**：LLM 连 metric_name 一起填错且错得与 field_ref 自洽（引用净利率字段、声称净利率、但 context 语境是毛利率）——此残余由基准集 semantic_mismatch 子集测量，不试图在机制上消灭。

### D3: 重试按桶分流，而非取消重试

分桶沿用 triage 口径：

| 桶 | 路由 |
|---|---|
| value_mismatch（值级 FAIL，gt 存在且超容差） | **定向重试**：只重跑产出该 claim 的分析师（Send 单点派发），其余复用 |
| 格式/契约类 FAIL（路径不可解析、术语不一致、内部不一致） | 不触发重试，记 incident 候选（重试无收益，实测三轮停滞 35%→38%→31%） |
| UNVERIFIABLE | 不触发重试（现行行为不变） |

- 定向重试上限仍为 3（iteration_count 语义不变）；
- 重试上下文附带失败 claim 明细 + ground_truth，这是与旧"盲目重跑"的关键区别——给 LLM 改错所需的信息。

### D4: context 语义声明走"生成时注入"，不靠 prompt 自然语言要求

在 context 构建代码里为每个数组/序列数据块自动附加机器生成的语义头（如 `# 序列: 升序, index -1 = 最新交易日(2026-08-28), 共60期`），与 `data-ordering-citation-contract` 的"展示从 index 0 开始"契约同源。prompt 自然语言要求（"请注意数组是升序"）作为冗余但非主防线——自然语言约束正是期次错位事故的失效点。

### D5: Claim schema 兼容

`metric_name`/`period` 设 default None，旧 session 的 analyst_reports 反序列化不炸；为 None 时术语/期次检查跳过并计入覆盖率缺口（与未注册根键同策略：显式降级 + 计数，不静默 PASS）。

## Risks / Trade-offs

- **正则普查口径**：金额单位（亿/万/元）、百分比小数位差异 → 归一化函数必须 fixture 钉死，首批结果人工抽查 20 条；
- **覆盖率阈值误报**：定性章节（风险段落）数字密度低且多豁免类 → 分章节统计，只看数据密集章节；
- **定向重试的状态依赖**：分析师输出间存在交叉引用时单点重跑可能产生新旧混排 → 重跑后其 claim 全部重新校验，下游辩论节点输入以重跑后版本为准；
- **schema 演进**：Claim 加字段影响 Langfuse 历史 trace 回放兼容 → rejudge 对缺字段按 D5 降级。

## Open Questions

- `citation_coverage` 告警阈值 0.8 是否按章节分档？→ 首版运行两周后依分布定；
- 术语枚举词表是否暴露给前端报告渲染做高亮？→ 后续前端 delta 再议。
