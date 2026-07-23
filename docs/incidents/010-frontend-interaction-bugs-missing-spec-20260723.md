# 010: 测试全过但前端交互 bug 频出 — 缺少行为 spec 约束

**日期**: 2026-07-23
**状态**: 处理中（解决方案已立项，见「修复方案」）
**触发**: 开发者人工验证前端交互，发现大量 bug 且反复修改后依然存在；而此前 AI 声称单元测试与 e2e 全部通过

---

## 问题描述

AI 辅助开发与测试后宣称「测试全部通过」，但开发者手动验证前端交互时发现大量 bug，且经历多轮「修 bug」后问题依旧复发。交互层成为事故高发区。

核查测试体系后发现，「测试全过」的实际含义与「行为正确」之间存在系统性落差：

| # | 发现 | 证据 | 影响 |
|---|------|------|------|
| 1 | 前端零单元/组件测试 | `frontend/package.json` 无 test 脚本，无 vitest/jest/testing-library | 2120 行 `App.tsx` 巨石组件的所有交互逻辑零覆盖 |
| 2 | CI 只跑后端单测 | workflow 执行 `pytest tests/ --ignore=tests/e2e`；e2e job 仅手动触发 | 「全过」= 303 个后端单测通过，与前端无关 |
| 3 | 后端单测重度 mock | 19 个测试文件 98 处 mock + 合成数据 fixture | 测的是纯函数，测不到真实链路与交互 |
| 4 | e2e 测试形同虚设 | 8 个 `e2e_*.py` 文件名不匹配 pytest 收集规则，永不执行；部分 `test_*.py` 在模块顶层启动浏览器，无 dev server 时收集即报错 | e2e 防线实际不存在 |
| 5 | 幸存 e2e 为恒真断言 | 如 `assert page.locator("textarea").count() >= 1` 标注「提交后离开空状态」 | 断言恒真，什么都证明不了 |
| 6 | AI 以截图目检代替验证 | `.playwright-mcp/` 留存大量 console log 与截图 | 只能发现白屏级崩溃，发现不了状态竞争与边界交互 |

---

## 根因分析

### 直接原因：测试从实现反推，验证的是「代码按现状工作」

现有测试（包括 AI 生成的）均以代码现状为基准编写断言，天然只能证明「实现没有回归」，无法证明「交互符合预期」。当预期只存在于开发者脑中时，AI 写代码和写测试都无可对照的依据——修 bug 变成「换一种现状」，旧 bug 换个形式复发。

### 深层原因：缺少前端行为的 spec 约束

前端交互行为（SSE 流式渲染、会话切换、模式切换、状态流转）从未被任何文档定义。「正确行为是什么」这一基准的缺失，导致：

- **写代码时**：AI 凭通用经验生成交互逻辑，无人校验是否符合产品意图；
- **写测试时**：断言只能从实现反推，恒真断言（上表 #5）由此产生；
- **修 bug 时**：每次修复没有行为契约可回归，修 A 破 B、反复震荡。

### 对比 incident 005

005 是「测试污染 + 文档漂移」，本质同样是「没有可对照的行为基准」。010 是该问题在前端交互层的放大版——005 修复的是单个 bug，010 需要修复的是产生这类 bug 的体系。

---

## 修复方案

引入 SDD（Spec-Driven Development）规范体系，重构文档架构与开发流程，让行为契约成为代码与测试的共同依据。详细实施步骤见 `docs/openspec-superpowers-实施文档.md`，要点：

| # | 动作 | 内容 |
|---|------|------|
| 1 | 引入 OpenSpec delta spec 机制 | 基于 CONTEXT.md + 16 篇 ADR + 既有 incidents 反推构建 `openspec/specs/` 主规范库（系统当前行为的唯一真相）；行为变更走 delta 提案（ADDED/MODIFIED/REMOVED）→ 验证 → sync + archive；**优先补 `frontend/` 交互行为规范** |
| 2 | 引入 Superpowers 开发管线 | 替换 Matt Pocock skills（删除 `.claude/skills/`、`.trae/skills/`、`skills-lock.json`），以红-绿 TDD、review 关卡、verification-before-completion 补上行为级验证纪律 |
| 3 | 重构文档架构 | 保留 CONTEXT.md / ADR / incidents / design；新增 `openspec/` 契约层与 `docs/superpowers/` 任务耗材层；按实施文档 §6 改写 CLAUDE.md 为路由 + 红线规则 |
| 4 | 规范开发流程 | 落地任务路由表（新功能 / A 类 bug / B 类 bug / 架构决策 / 小改动分流）与 archive 硬关卡（tasks.md 全勾 + 验证通过 + 人工验证报告落 `tests/validation/`） |

**验收**：按实施文档 §9 检查清单逐项完成，并以 incident 005 的模拟 delta 提案完整跑通「提案 → 执行 → 验证 → sync + archive」全流程作为管线验证。

**确立的红线**（写入 CLAUDE.md）：

- 没有先写失败测试的代码，删除重写
- 「测试全过」不等于「行为正确」；交互行为变更必须有人工验证环节
- 修改任何已有行为前必须先查 `openspec/specs/` 主规范库

---

## 关联

- [005](005-garp-dupont-test-pollution-20260604.md) 测试污染与文档漂移（同根源问题的前次局部表现）
- [007](007-sidebar-invalid-date-20260716.md)、[008](008-deep-analysis-stuck-akshare-20260716.md) 前端/交互类 bug 的典型个案
- `docs/openspec-superpowers-实施文档.md` 修复方案的完整实施计划
