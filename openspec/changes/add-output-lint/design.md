# Design: add-output-lint

## Approach

两处确定性后处理，均零 token：

1. **批注剥离（analysts.py）**：新增 `_strip_editor_notes(report: AnalystReport) -> AnalystReport`，`_parse_analyst_report` 重命名为 `_parse_analyst_report_raw` 后在入口包装——三条返回路径（正常解析 / #109 markdown 合成 / 解析失败降级）统一过剥离，覆盖 summary、plain_conclusion、key_findings、markdown 四个交付字段。正则 `（[^（）]{0,48}(?<!无)(?<!不)(?<!必)需修正）`：内容无嵌套括号、≤48 字符、以「需修正」紧邻右括号收尾；三个否定 lookbehind 排除「无需/不必/不需修正」；「需修正」不在收尾位置的括号（如「需修正后才成立」）天然不命中。claims 不剥离（引用校验契约另行治理，见 design 风险）。命中数经 `update_current_span(metadata={"editor_notes_stripped": n})` 可观测。

2. **数值格式化（compute.py）**：`_derive_pe_ttm` 唯一内插数值的缺失原因串 `f"TTM 归母净利润({ttm})非正"` → `f"TTM 归母净利润({ttm:.2f})非正"`（该链路全程亿元口径，与测试 SNAP_H1 单位一致；同文件 :436 的 `:.1f` 为既有先例）。

## Alternatives Considered

- 剥离放进 AnalystReport pydantic field_validator：否——把 lint 策略耦合进共享模型，且 model 层无法感知「仅分析师输出适用」的边界（辩论/裁决复用文本模型时会误伤）。
- 剥离正则放宽到「需修正/待修正/应更正」全变体：否——证据仅见「需修正」，窄规则先行，变体出现时按证据扩（避免无证据泛化引入误伤面）。
- 浮点格式化放渲染层（report.py）统一清洗：否——`_derive_pe_ttm` 原因串还会进 details/trace 等多处消费方，源头格式化一次覆盖全部下游；渲染层兜底留给未来有新泄漏点时再议。

## Risks

- 误伤面：括号 + 收尾 + ≤48 字符 + 否定排除四重约束，8 份存量报告中仅深南 1 处命中（赛轮/光大「需修正」用语均不满足形态），回归测试固化两类假阳性样本。
- claims 内若出现批注会原样进入引用校验：当前无证据（8 份报告 claims 零命中），不在本变更扩scope；若后续出现，按证据追加。
- `editor_notes_stripped` metadata 在无活跃 span 上下文时为 no-op（`update_current_span` 既有行为），不影响离线测试。
