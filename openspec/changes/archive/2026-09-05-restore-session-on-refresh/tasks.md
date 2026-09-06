# Tasks: restore-session-on-refresh

## 1. 复现测试（TDD 先行）

- [x] 1.1 新增前端测试 `frontend/src/test/restore-session-on-refresh.test.tsx`：localStorage 预置 `fa_current_session_id` 指向进行中会话，mock `/api/sessions` 与 `/api/sessions/{id}`，断言 mount 后自动选中该会话并重建消息（无需手动点击）
- [x] 1.2 测试「持久化会话已删除」分支：mock `/api/sessions` 返回列表不含该 id，断言清除 localStorage 并停留空态首页
- [x] 1.3 测试「无持久化会话」分支：localStorage 无该 key，断言显示空状态首页（现有行为不回归）
- [x] 1.4 运行测试确认 1.1/1.2 失败（复现），1.3 通过

## 2. currentSessionId 持久化

- [x] 2.1 在 App.tsx 新增 `persistCurrentSession(id: string | null)` 辅助函数：非 null 写 `fa_current_session_id`，null 时移除该项
- [x] 2.2 找出 `setCurrentSessionId` 全部调用点（选中会话、session_created、删除当前会话、新建分析等），同步调用 `persistCurrentSession`，确保 currentSessionId 变化即持久化
- [x] 2.3 封装统一的 `setAndPersistSession(id)` 替换直接 `setCurrentSessionId` 调用，避免遗漏

## 3. mount 自动恢复

- [x] 3.1 在 mount 初始化 effect 中，`loadSessions()` 首次成功后读取 `fa_current_session_id`
- [x] 3.2 校验该 id 是否在加载到的会话列表中：不存在则清除 localStorage、停留空态；存在则调用 `selectSession(id)` 恢复
- [x] 3.3 用 `restoredRef = useRef(false)` 保证自动恢复仅执行一次，后续 loadSessions 触发不重复恢复
- [x] 3.4 确认 selectSession 对 running 会话经 resumeStream 重连事件流（复用现有逻辑，不新增通道）

## 4. 验证

- [x] 4.1 `cd frontend && npx vitest run` 全部通过（含新增测试）
- [x] 4.2 `cd frontend && npx tsc --noEmit` 无类型错误
- [x] 4.3 E2E 门禁（2026-09-05：stub 套件 20 passed / 2 skipped / 0 failed，refresh-resume-accept.spec 在门禁内）
- [x] 4.4 人工验证（2026-09-05：GUI 实测已完成恢复 + 组件/E2E 覆盖其余 scenario，报告 tests/validation/2026-09-05-restore-session-on-refresh-validation.md）
