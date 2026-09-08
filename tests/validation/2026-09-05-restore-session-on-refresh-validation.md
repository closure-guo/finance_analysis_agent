# 人工验证报告: restore-session-on-refresh

**日期**: 2026-09-05
**验证人**: ZCode agent（真实 Chromium GUI 实测 + 组件/E2E 证据归集）
**关联 delta**: openspec/changes/restore-session-on-refresh/
**E2E 门禁**: stub 套件 `npx playwright test --grep-invert "@live"` → 20 passed / 2 skipped / 0 failed（2026-09-05，@live 按规范归 nightly 不进门禁）

## 验证环境

- 后端 TESTING=1（独立测试库 data/gui-test-sessions.db，LLM stub）
- 前端 vite dev server，Chromium 1280×800 / 375×667
- 测试会话经 /api/test/seed 造数（display_name「GUI verify session」，completed）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 刷新后自动恢复已完成的会话 | 部分（组件测试 restore-session-on-refresh.test.tsx） | 刷新后恢复会话视图 | GUI 实测：会话视图刷新后自动恢复，报告摘要卡（深度分析报告 · 打开报告）、消息历史（user/assistant）、输入栏齐全 | ✅ |
| 刷新后自动恢复进行中的会话 | 是（refresh-resume-accept.spec.ts，stub 套件通过） | 恢复后断点续传，无重复缺失 | E2E 门禁绿 + 组件测试断言恢复路径 | ✅（E2E） |
| 持久化会话已删除时回退空态 | 是（组件测试：restore 404 → 空态回退） | 回退空态首页不报错 | 组件测试断言 | ✅（组件测试） |
| 无持久化会话时保持空态首页 | 是（组件测试） | 保持空态 | 组件测试断言 | ✅（组件测试） |
| currentSessionId 生命周期同步 | 部分（session-created-ref-sync.test.tsx / select-session-stale-guard.test.ts 均绿） | 刷新/切换后 ref 同步 | 组件测试全绿 | ✅ |

## 异常记录

无失败项。注：本 delta 为 2026-08-05 提案、#48（430b004）实现；其行为此后被 persist-full-session-timeline、resume-stream-on-session-switch 等后续 delta 持续加固，相关 E2E spec（refresh-resume-accept、session-switch-resumption）均在 2026-09-05 stub 门禁中通过。

## 结论

- [x] 全部通过，可 archive
