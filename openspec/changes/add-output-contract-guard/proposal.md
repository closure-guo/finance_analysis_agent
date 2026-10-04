# Proposal: add-output-contract-guard

## Why

2026-10-04 第五版拓荆报告交付级事故（incident 036）：换 glm-5.3 后「研究聚焦」段把模型英文任务独白原文交付并中途截断（"The user wants a 150-200 character … Draft: … PE_ttm 85."）。根因是**纯文本直通交付物的路径不在 `llm-output-contract` 覆盖内**——现有输出合同只管 JSON 结构化路径（extract_json → Pydantic → repair），而报告开篇摘要这类「LLM 文本直接嵌入用户可见交付物」的路径零校验，输出格式此前全靠旧模型自觉遵守，换模型即裸奔。换模型以来 3 次摘要调用泄露 2 次（间歇性），且网关层续写机制救「截断」救不了「内容违约」。

## What Changes

- `llm-output-contract` 新增「纯文本交付物输出合同」requirement：泄露模式 / 非目标语言占比 / 句中截断的**确定性**校验；命中定向重试 1 次；重试仍违约回退调用方既有结构化兜底；MUST NOT 将原始模型输出嵌入交付物
- 关闭 `report.py` 的 raw_reasoning 交付回退坑（`resp = text or meta.get("raw_reasoning")`）——reasoning 仅进 trace 观测，永不作为交付文本
- `complete_text` 观测 metadata 补 `finish_reason` / `resume_count`（截断归因遥测，incident 036 中无法确证续写为何未触发的直接原因）
- 新增共享校验器（纯函数），供后续所有「LLM → 交付物」路径复用

## Capabilities

- **Modified Capabilities**: llm-output-contract

## Impact

- `src/finance_agent/nodes/report.py`（`_build_focus_summary` 接入校验、移除 raw_reasoning 回退）
- `src/finance_agent/llm/gateway.py`（`complete_text` 观测字段补充）
- 新增 `src/finance_agent/llm/output_guard.py`（共享校验器）
- 测试：`tests/` 新增泄露拦截 / 直通不误伤 / 截断处置 / raw_reasoning 禁回退四类单测
- 不改变 gateway 请求路径与 resume 机制（完整性层与正确性层分层，互不替代）
