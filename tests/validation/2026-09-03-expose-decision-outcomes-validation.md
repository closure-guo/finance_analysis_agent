# 人工验证报告: expose-decision-outcomes

**日期**: 2026-09-03
**验证人**: [agent 自动验证 + 待人工抽查]
**关联 delta**: openspec/changes/expose-decision-outcomes/
**E2E 门禁**: tests/e2e/playwright/playwright-report/（decisions.spec.ts 2 例全绿；全量套件中 11 例失败均为既有问题，见「异常记录」）

## 验证结果

| Scenario | E2E 已覆盖？ | 预期行为 | 实际结果 | 通过 |
|---|---|---|---|---|
| 侧边栏「决策战绩」入口 → /decisions | 是（decisions.spec.ts #1） | 折叠态图标点击后 URL 变为 /decisions 且渲染页面 | E2E 实测通过 | ✅ |
| 直达 /decisions 渲染 + 空态 + 返回聊天 | 是（decisions.spec.ts #2） | 空态提示可见，点击「返回聊天」回跳会话页 | E2E 实测通过 | ✅ |
| 汇总卡 + 列表渲染、null 占位「—」 | 否（组件测试覆盖） | 胜率/均值/收益/超额正确呈现，未结算字段显示「—」 | vitest decisionCenter.test.tsx 6 例全绿 | ✅ |
| 收益红涨绿跌 | 否（组件测试覆盖） | 正收益红色、负收益绿色 | vitest 断言 className 含 red/green | ✅ |
| 状态/股票过滤联动走 API 参数 | 否（组件测试覆盖） | 过滤变化后请求带 status/ticker 参数 | vitest 断言 fetch URL 含参数 | ✅ |
| 跳转来源会话 | 否（组件测试覆盖） | 点击行触发 onOpenSession(sessionId)；会话缺失时前端兜底不崩溃 | vitest 断言回调参数；selectSession 对缺失会话返回不抛错 | ✅ |
| 战绩数字与 decision_log 一致 | 否 | API 聚合口径：胜率/均值只基于已结算、excess null 剔除 | pytest 8 例（store）+ 5 例（API）覆盖统计口径 | ✅ |
| 非法 status 返回 422 | 否 | bogus 状态被拒绝 | pytest test_filter_and_invalid_status | ✅ |

## 待人工抽查项（E2E 覆盖不到的主观体验）

- [ ] 折叠态侧边栏图标（chart-line）与下载管理/设置图标并排的实际观感、tooltip「决策战绩」文案
- [ ] 有真实决策数据（非空库）时页面密度与表格可读性（需先有已结算决策）
- [ ] 点击决策行跳转会话的体感（当前为整树测试 + selectSession 复用，未在真实浏览器连点验证）

## 异常记录

1. **全量 E2E 套件 11 例失败，均为既有问题，与本 delta 无关**：
   - `downloads.spec.ts:23` 引用 `sidebar-downloads` testid——该 testid 已被前端重构移除（现仅有 `sidebar-downloads-collapsed`），属 stale spec，前置已存在
   - `search-banner.spec.ts` / `thinking-banner.spec.ts` 共 6 例为 @live 套件（需真实 LLM 慢速流式），stub 后端无法满足，CI nightly 才跑
   - `concurrent-streaming-integrity`、`debug-explore`、`explore` 为 waitForTimeout 时序依赖的技术债（playwright.config.ts 注释已标注）
2. **后端全量 pytest 4 例失败**：`test_outcome_live.py` / `test_trace_content_live.py` 均带 `@live` 标记，CI 门禁 `-m "not live"` 剔除，非本 delta 引入
3. **App.tsx 提交含既有未提交 WIP**（fix-session-switch-flash 的 sessionSwitching 逻辑，会话开始前已在工作区），与本次改动同文件，随 commit 一并入库

## 结论

- [x] 功能实现 + 自动化验证通过（后端门禁全绿、前端 454 全过、E2E decisions spec 全绿、ruff/tsc 干净、mypy 无新增错误）
- [ ] 待人工抽查项完成后方可 archive（详见「待人工抽查项」）
