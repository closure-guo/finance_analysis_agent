# Design: fix-dropdown-outside-close

## Context

「模式切换」与「LLM 切换」下拉框存在于两处组件、共 4 个实例：`EmptyState`（空状态首页输入框上方，`dropdownOpen` / `llmDropdownOpen`）与底部输入栏（会话视图 `ChatInputBar`，`modeDropdownOpen` / `llmDropdownOpen`）。当前开合状态只由触发按钮的 `onClick` 切换（`frontend/src/App.tsx` 约 990-1057、1795-1864 行），无任何「点击外部关闭」处理，展开后下拉框常驻覆盖页面。设置弹窗（`SettingsModal`）已有「点击遮罩关闭」语义，本修复与之一致。

## Goals / Non-Goals

**Goals:**
- 4 个下拉框实例统一获得「点击下拉框以外区域即关闭」行为
- 同一输入栏内两个下拉框互斥展开（打开一个自动关闭另一个）
- 触发按钮再次点击的 toggle 行为、选项点击执行动作并关闭的行为保持不变
- 用 Vitest + RTL 组件测试覆盖新行为，与既有前端测试同目录

**Non-Goals:**
- 键盘 Esc 关闭、`aria-expanded` 无障碍属性与焦点管理（本次不加，避免范围膨胀）
- `SettingsModal` 内的原生 `<select>`（浏览器原生自带关闭行为，不在缺陷范围）
- 修正既有 frontend spec 中「Mode Locking After Session Creation / Chat Input Bar 输入栏模式切换锁定」与当前实现在会话视图可展开模式下拉框之间的描述漂移（存量问题，另行处理）

## Decisions

**D1: 统一「点击外部关闭」hook，而非两组件各写一套。**
新增 `frontend/src/useClickOutside.ts`，导出 `useClickOutside(ref, onOutside)`：当任一子下拉框处于展开状态时，在 `document` 上挂 `mousedown` 监听（冒泡阶段），事件目标不在 `ref.current` 内则调用 `onOutside` 关闭所有下拉框；空状态下不挂监听，组件卸载时清理。两组件各取一个 `rowRef` 挂到「触发器按钮 + 弹层」共同所在的 `relative` 容器 div 上（EmptyState 约 990 行、ChatInputBar 约 1795 行的容器），共用同一 `onOutside` 同时关闭两个 open state。
> 选 `mousedown` 而非 `click`／`pointerdown`：`mousedown` 先于默认行为触发，不阻止点击事件的原始作用（点击输入框仍能聚焦、点击会话仍能选中），且 jsdom 对 `MouseEvent` 兼容性最佳、RTL 测试无 polyfill 顾虑；触屏场景非本目标。

**D2: 互斥展开收敛在触发按钮 `onClick`，而非监听层。**
两处组件的触发按钮 onClick 改为「先关对方、再 toggle 自己」：
- 模式触发按钮：`onClick={() => { setLlmDropdownOpen(false); setDropdownOpen(v => !v) }}`
- LLM 触发按钮：`onClick={() => { setDropdownOpen(false); setLlmDropdownOpen(v => !v) }}`
原 toggle 语义不变（再次点击同一按钮仍收起），新增强制互斥，与 D1 的事件监听互不干扰。

**D3: 规避经典的「点击触发按钮关不开」竞态。**
文档级监听若只挂在弹层 div 上，点击触发按钮会先命中外部关闭再被 onClick 重新打开，导致下拉框永远关不掉。对策：`rowRef` 必须挂在包含「触发按钮 + 弹层」两者的容器上（两处组件的触发器与弹层均在同一 `relative` 容器内，天然满足）；监听器对容器内点击直接放行，交由按钮 onClick 决定 toggle，语义与现状完全一致。

## Risks / Trade-offs

- **触发按钮竞态回归**：若 ref 误挂在弹层单独 div 而非包裹容器上，会出现「点触发按钮关不上」的反向 bug。→ 对策：D3 已明确 ref 挂载位置，测试用例「再次点击触发按钮收起」与「点击选项执行动作并关闭」可拦截该回归。
- **点击穿透失效**：若监听器 `preventDefault`/`stopPropagation` 会破坏「点击外部同时执行该区域的正常动作」。→ 对策：只做「目标不在容器内 → 关闭」判定，不拦截事件默认行为与传递；测试中额外断言点击外部后输入框可聚焦等原有交互不受影响（可选加断言）。
- **jsdom 事件差异**：RTL 用 `fireEvent.mouseDown`（`MouseEvent`）模拟，与实现选型一致，无 polyfill 需求。
- **行为契约边界**：capability 门禁（`canEnterMode`）禁用项、无 profile 时点击 LLM 引导打开设置面板等既有逻辑不在本次改动范围，改动只触达 open state 的打开/关闭路径。