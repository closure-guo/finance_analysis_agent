# 人工验证报告

本目录存放 **archive 验收证据**：每次变更（新功能 / 修 bug）完成后的人工验证报告，
证明"行为符合预期"，是 OpenSpec archive 的硬性前置条件。

> **边界说明**：本目录是单次变更的验收证据（测试是否通过、行为是否符合预期），随 delta 生命周期归档。
> **系统性问题**（反复复发、方法论缺陷、架构缺陷）的复盘请落 `docs/incidents/`——
> 那里记录"为什么会出问题、如何防止再发"，供团队长期参考避坑。
> 一个 bug 若既是系统性问题又需验证报告，两边都放，incident 引用 validation，不重复内容。

## 命名规范

```
YYYY-MM-DD-<change-id>-validation.md
```

- `YYYY-MM-DD`：验证日期
- `<change-id>`：对齐 openspec delta 目录名（如 `add-e2e-core-specs`）或 bug 简述

## 内容要求

按 `docs/project-workflow.md` §验收项，报告需包含：

| 必填项 | 说明 |
|--------|------|
| 验证范围 | 覆盖哪些 Requirement / 修复点 |
| E2E 门禁结果 | 每个 Scenario 的预期 vs 实际，是否通过 |
| 单元测试结果 | 相关测试文件、用例数、通过率 |
| Spec 偏差记录 | 与 spec 不一致处及风险评估（如有） |
| 结论 | 全部通过可 archive / 存在失败需修复 |

## 关联

- `docs/project-workflow.md` 验收流程与硬关卡
- `docs/incidents/` 系统性问题复盘
- `openspec/changes/` delta 提案与 archive
