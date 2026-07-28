# Tasks: fix-deep-search-result-conflict

## 1. Spec 修正

- [x] 1.1 Sync delta spec 到主 spec：用 MODIFIED 版本覆盖 `openspec/specs/frontend/spec.md` 中的 `SSE Event: search_result (Deep Mode)` 需求
- [x] 1.2 验证主 spec 内部无冲突：`SSE Event: search_result (Deep Mode)` 与 `Deep Mode Search Banner` 语义一致
- [x] 1.3 `openspec validate fix-deep-search-result-conflict` 通过

## 2. 验证

- [x] 2.1 人工验证报告落 tests/validation/（确认 spec 冲突已消除）
