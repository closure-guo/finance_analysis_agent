# Delta for llm-output-contract

## ADDED Requirements

### Requirement: 分析师输出批注剥离

分析师 LLM 输出经解析合同装配为 AnalystReport 时，SHALL 对 summary、plain_conclusion、key_findings、markdown 四个交付字段执行确定性批注剥离：命中「括号内以『需修正』收尾」的自我修正批注（括号内容 ≤48 字符且无嵌套括号）SHALL 整体移除（含括号本身）；「无需修正/不必修正/不需修正」否定形态（「需修正」紧邻前字符为「无/不/必」）与未被括号包裹的辩论/叙述用语 MUST NOT 被剥离；剥离命中数 SHALL 进 trace metadata（`editor_notes_stripped`）。批注剥离 MUST NOT 应用于辩论、裁决、交易决策等其他 LLM 文本。

#### Scenario: 自我修正批注被剥离

- **GIVEN** 技术分析师 key_findings 含「收盘价高于MA20约1.9%的偏离反向（低于MA20约1.9%需修正）」（2026-10-05 深南电路 002916 实例）
- **WHEN** AnalystReport 装配执行批注剥离
- **THEN** 该条目 SHALL 变为「收盘价高于MA20约1.9%的偏离反向，…」（批注含括号整体移除，其余文字保留）
- **AND** trace metadata SHALL 记录 `editor_notes_stripped` ≥ 1

#### Scenario: 否定形态不误伤

- **GIVEN** 某交付字段含「（中报口径无需修正）」
- **WHEN** 批注剥离执行
- **THEN** 该括号内容 SHALL 原样保留

#### Scenario: 辩论用语不触碰

- **GIVEN** 文本含「需修正其『多空证据实质均衡』的定性」（未被括号包裹，2026-10-05 赛轮轮胎辩论用语）
- **WHEN** 批注剥离执行
- **THEN** 该文本 SHALL 原样保留

#### Scenario: 非收尾形态不误伤

- **GIVEN** 括号内容为「该结论需修正后才成立」（「需修正」不在括号收尾位置）
- **WHEN** 批注剥离执行
- **THEN** 该括号内容 SHALL 原样保留
