# Spec 冲突修复人工验证报告

**日期**: 2026-07-27
**Delta 提案**: fix-deep-search-result-conflict
**验证人**: 实施者

## 背景

add-search-banner delta sync 到主 spec 时，只以 ADDED 方式追加了 `Deep Mode Search Banner` 需求（声明"不再附加到 ToolCallBanner"），未 MODIFIED 覆盖旧的 `SSE Event: search_result (Deep Mode)` 需求（声明"结果在 ToolCallBanner 中展示"）。两条需求对同一事件给出互斥断言，导致主 spec 内部矛盾。

## 修复内容

用 MODIFIED 覆盖主 spec `openspec/specs/frontend/spec.md` 中的 `SSE Event: search_result (Deep Mode)` 需求：
- 描述改为"将搜索结果设置到 searchStatus/searchResults 属性，由独立搜索横幅展示"
- 场景断言改为"渲染搜索横幅 + 不再附加到 ToolCallBanner"
- 与 `Deep Mode Search Banner` 需求语义完全对齐

## 验证项

| # | 验证项 | 结果 |
|---|--------|------|
| 1 | 主 spec 中 `SSE Event: search_result (Deep Mode)` 已改写为搜索横幅展示 | 通过 |
| 2 | 与 `Deep Mode Search Banner` 需求语义一致，无互斥断言 | 通过 |
| 3 | `openspec validate fix-deep-search-result-conflict` 通过 | 通过 |
| 4 | 无代码改动（纯 spec 文本修正，实现已在 add-search-banner delta 落地） | 通过 |

## 备注

本 delta 为纯 spec 文本修正，无代码改动，无需 E2E 测试。
