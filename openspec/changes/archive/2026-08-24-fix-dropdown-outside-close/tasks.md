# Tasks: fix-dropdown-outside-close

> 约定：TDD 红线——先写失败测试再实现。每任务完成后跑对应测试验证。
> 涉及文件：
> - 前端：`frontend/src/useClickOutside.ts`（新增）、`frontend/src/App.tsx`（EmptyState ~931 行、ChatInputBar ~1739 行）
> - 测试：前端 `frontend/src/test/`（Vitest + RTL）

## 1. 前端：可复用点击外部关闭 hook

- [x] 1.1 新建 `frontend/src/useClickOutside.ts`：文档级 `mousedown` 监听——任一子下拉框展开时才挂载，事件目标不在容器 ref 内则触发 `onOutside`，卸载时清理监听
- [x] 1.2 失败测试：容器内点击不触发 onOutside；容器外点击触发；卸载后监听被清理

## 2. 前端：EmptyState（空状态首页）接入

- [x] 2.1 失败测试：空状态模式下拉框展开 → 点击下拉框外部区域 → 下拉框关闭，当前模式不变、不触发发送
- [x] 2.2 失败测试：空状态 LLM 切换下拉框展开 → 点击外部区域 → 下拉框关闭，当前 profile 不切换
- [x] 2.3 失败测试：同一输入栏互斥展开——模式下拉框展开时点击 LLM 触发按钮 → 模式关闭、LLM 展开；反向同样生效
- [x] 2.4 失败测试：再次点击同一触发按钮 → 下拉框收起；点击下拉框选项 → 执行对应动作并关闭
- [x] 2.5 实现：`rowRef` 挂到「模式切换 + LLM 切换」共同所在容器 div（含触发按钮与弹层）；触发按钮 onClick 互斥改写（模式触发先关 LLM、LLM 触发先关模式，再 toggle 自己）；接入 useClickOutside

## 3. 前端：ChatInputBar（会话底部输入栏）接入

- [x] 3.1 失败测试：会话视图模式下拉框展开 → 点击外部区域 → 下拉框关闭，当前模式与会话不变、不触发新会话
- [x] 3.2 失败测试：会话视图 LLM 切换下拉框展开 → 点击外部区域 → 下拉框关闭，当前 profile 不切换
- [x] 3.3 失败测试：互斥展开与 Trigger toggle（会话视图）
- [x] 3.4 实现：`rowRef` + onClick 互斥改写 + useClickOutside 接入（同 EmptyState 模式）

## 4. 回归与既有行为

- [x] 4.1 capability 门禁（`canEnterMode`）不回归：门禁不允许的模式选项仍禁用、点击不生效
- [x] 4.2 无 LLM profile 时点击 LLM 切换 → 仍引导打开设置面板（现有行为不回归）
- [x] 4.3 `cd frontend && npm test` 全绿（36 文件 / 325 用例）+ `npx tsc -b` 通过

## 5. E2E 与人工验证

- [x] 5.1 E2E 测试（真实浏览器，禁止 mock 被测系统）：空状态与会话视图下，模式/LLM 下拉框展开后点击页面其他位置关闭、同一输入栏两个下拉框互斥展开、再次点击触发按钮收起（真实浏览器人工 E2E 完成，证据截图落 `tests/e2e/dropdown-outside-close-*.png`；standalone `e2e/` Playwright 自动 spec 待 §5.6 P1–P4 基础设施落地后补齐）
- [x] 5.2 人工验证报告落 `tests/validation/2026-08-24-fix-dropdown-outside-close-validation.md`
- [x] 5.3 `openspec validate fix-dropdown-outside-close` 通过（exit 0）