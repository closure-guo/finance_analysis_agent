# Proposal: add-output-lint

## Why

10-05 八份报告二轮质检（issue #244）发现两类输出层缺陷：深南电路(002916)分析师把自我修正批注「（低于MA20约1.9%需修正）」泄漏进报告终稿关键发现；南方航空(600029)口径披露节原样输出未舍入浮点「TTM 归母净利润(-13.060000000000002)非正」。两类均为零 token 可拦的确定性后处理，但当前管线无任何拦截。

## What Changes

- 分析师 LLM 输出装配为 AnalystReport 时，对 summary / plain_conclusion / key_findings / markdown 四个交付字段执行确定性批注剥离：仅命中「括号内以『需修正』收尾」的形态（≤48 字符），「无需/不必/不需修正」否定形态与无括号的辩论用语不误伤；命中数进 trace metadata
- 估值缺失诚实文案中内插的数值统一格式化（亿元口径两位小数），MUST NOT 输出未舍入浮点尾巴

## Capabilities

### New Capabilities
- （无）

### Modified Capabilities
- `llm-output-contract`: ADDED「分析师输出批注剥离」——分析师结构化输出装配后的确定性后处理，属输出合同家族
- `valuation-signal-integrity`: MODIFIED「估值缺数据的诚实文案」——补充内插数值格式化约束

## Impact

- `src/finance_agent/nodes/analysts.py`（`_parse_analyst_report` 装配后剥离）
- `src/finance_agent/nodes/compute.py`（`_derive_pe_ttm` 缺失原因串格式化）
- 下游连带：引用校验（claims 不受影响，剥离只作用于四个展示字段）、辩论与裁决文本不触碰
