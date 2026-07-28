## Why

add-search-banner delta 同步到主 spec 时，只以 ADDED 方式追加了 `Deep Mode Search Banner` 需求（声明"不再附加到 ToolCallBanner"），未 MODIFIED 覆盖旧的 `SSE Event: search_result (Deep Mode)` 需求（声明"结果在 ToolCallBanner 中展示"）。两条需求对同一事件（深度模式澄清阶段收到 search_result）给出互斥断言，导致主 spec 内部矛盾，违反"specs 是系统行为唯一真相来源"的契约。

## What Changes

- **MODIFIED** `SSE Event: search_result (Deep Mode)` 需求：将"附加到工具调用记录 + 在 ToolCallBanner 展示"改写为"设置 searchStatus/searchResults 属性 + 由独立搜索横幅展示"，与 `Deep Mode Search Banner` 需求对齐
- 移除旧的"摘要格式为'找到 N 条结果：前3条标题'"断言（已被搜索横幅的"搜索了 N 个网页"+ 可展开列表取代）
- 不涉及代码改动，仅修正 spec 文本以反映已落地的实现

## Capabilities

### New Capabilities
<!-- 无新增能力 -->

### Modified Capabilities
- `frontend`: 修正 `SSE Event: search_result (Deep Mode)` 需求，消除与 `Deep Mode Search Banner` 的语义冲突

## Impact

| 文件 | 改动 |
|------|------|
| `openspec/specs/frontend/spec.md` | 改写 `SSE Event: search_result (Deep Mode)` 需求的描述和场景断言 |

无代码改动，无 API 变更，无依赖影响。实现已在 add-search-banner delta 中落地，本次仅修正 spec 文本。
