# Proposal: adopt-assistant-ui-chat

## Why

1. **聊天区是手写代码的 bug 高发区**：流式逐字渲染、自动滚动、中断续传、思考流与正文混排等细节极多，手写实现已积累多个交互缺陷（见 fix-analysis-ux-polish）。
2. **观感落后**：现有消息区与 Kimi 等同类产品差距明显，而 refactor-ui-design-system 只完成了设计系统打底，聊天主区未动。
3. **已有成熟组件可复用**：assistant-ui 提供经过大量生产验证的 Thread/Composer/Reasoning/Tool 组件，官方提供 LangGraph 模板，可直接作为实现基座，无需从零手写流式渲染。

## What Changes

- 以 assistant-ui 官方 LangGraph 模板为基座，引入 Thread/Composer/Reasoning/ToolFallback/ActionBar 组件（源码入仓 `frontend/src/components/`）。
- 新增 **SSE runtime adapter**：单一翻译层，将后端现有 SSE 事件（chat_token、thinking、工具调用、管线节点、report_ready 等）映射为 assistant-ui 消息部件；后端事件协议不变。
- 思考过程渲染为折叠卡片（流式中显示"思考中"，完成可展开）；工具调用渲染为卡片（loading/完成/可展开）。
- 输入区替换为 assistant-ui Composer：Enter 发送、Shift+Enter 换行、生成中变为停止按钮。
- 消息 hover 操作：复制、重新生成。
- 项目独有功能以自定义消息部件挂载保留：管线进度时间线、ECharts 图表、报告导出入口。

非目标（Out of scope）：

- 不改变后端 SSE 事件协议、会话管理与 session-store 语义。
- 不做空态首页/建议卡片、不做折叠侧边栏（均为后续独立 change）。
- 不改变报告 Markdown 渲染与导出逻辑，仅改挂载方式。
- 不引入 AG-UI 等协议层改造。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `frontend`: 聊天消息区整体替换为 assistant-ui 渲染；新增 SSE adapter 契约；思考/工具调用的展示形态变更；交互行为（三模式、追问、停止、运行中拦截）语义不变。

## Impact

- **前端**：`frontend/src/` 新增 assistant-ui 组件与 runtime adapter；消息区相关手写组件下线。
- **依赖**：@assistant-ui/react 及相关包、framer-motion、lucide-react。
- **测试**：既有前端测试 SHALL 无修改通过；新增 adapter 事件映射单测（逐事件类型）。
- **验证**：交互核心路径变更，人工验证报告落 `tests/validation/`；按红线需 E2E 门禁。
