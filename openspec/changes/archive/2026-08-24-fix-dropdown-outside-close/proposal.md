# Proposal: fix-dropdown-outside-close

## Why

「模式切换」与「LLM 切换」两个下拉框（空状态首页 + 会话底部输入栏，共 4 处实例）展开后，点击页面其他位置不会关闭——下拉框只靠触发按钮的 `onClick` 切换开合，展开后常驻覆盖输入区或内容区，必须再次点击触发按钮才能收起。这与标准下拉交互习惯不符（同类浮层的设置弹窗已有「点击遮罩关闭」语义），是纯前端交互缺陷。

## What Changes

- **「模式切换」下拉框**（空状态首页 + 会话底部输入栏）：展开后点击下拉框以外的页面区域即关闭；点击选项仍执行原有动作（空状态切模式 / 会话中开启新会话）并关闭
- **「LLM 切换」下拉框**（空状态首页 + 会话底部输入栏）：展开后点击下拉框以外的页面区域即关闭；点击 profile 选项仍执行切换并关闭
- **同一输入栏内两个下拉框互斥展开**：打开其中一个时自动关闭另一个，避免下拉框弹层重叠
- 行为覆盖范围与已有实现一致：无 profile 时点击 LLM 切换仍引导打开设置面板；模式选项的 capability 门禁（`canEnterMode`）逻辑不变

## Capabilities

### New Capabilities

（无新增 capability——归属既有 `frontend` 能力）

### Modified Capabilities

- `frontend`: 新增「下拉框浮层 dismiss」交互契约——模式切换与 LLM 切换下拉框在首页与底部输入栏两处视图下的点击外部关闭、互斥展开行为（LLM 切换下拉框此前无任何行为契约覆盖，本次一并定义）

## Impact

- **前端代码**：
  - [App.tsx](file:///d:/WorkSpace/finance_analysis_agent/frontend/src/App.tsx) — `EmptyState`（`dropdownOpen` / `llmDropdownOpen`）与底部输入栏 `ChatInputBar`（`modeDropdownOpen` / `llmDropdownOpen`）两处组件；新增统一「点击外部关闭 + 互斥展开」处理（`useRef` 容器引用 + `document` 级 `mousedown` 监听），抽取为可复用 hook，两组件共用
- **测试**：前端 Vitest 组件测试（RTL，`frontend/src/test/`）覆盖「点击外部关闭」与「互斥展开」；交互类变更，人工验证报告落 `tests/validation/`
- **无影响**：后端、API 契约、依赖均不变；无新 npm 依赖