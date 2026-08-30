# Proposal: add-citation-display

## Why

1. **校验成果不可见**：后端 citation.py 已实现 Claim 6 类分类 + computational 公式重算（FinGround 思路），但校验结果只进日志/Langfuse，用户看不到「这句话有数据支撑」。
2. **信任是金融报告的核心卖点**：引用可见 + 校验状态可见是区别于普通聊天产品的关键体验。
3. **对齐 Kimi 引用形态**：行内上标编号、hover 预览、来源列表是成熟交互模式。

## What Changes

- 后端（citation-verification）：引用校验结果结构化下发——随报告/消息携带引用数组，每项含 `id`、`claim`、`source`、`verdict`（verified / failed / unchecked）、`detail`（来源或重算说明）。
- 前端：
  - 报告正文中的引用标记渲染为行内上标编号。
  - hover 上标显示预览卡：claim 摘要、来源、校验状态标识。
  - 报告末尾新增「引用与校验」列表：编号对应来源与校验状态。
  - 校验状态视觉：verified（绿）/ failed（红）/ unchecked（灰）。

非目标（Out of scope）：

- 不改变 Claim 分类法与校验算法本身。
- 不做来源网页在线预览/抓取。
- 不做引用导出单独格式（随报告既有导出走）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `citation-verification`: 新增「校验结果结构化下发」契约（事件/会话数据携带引用数组，向后兼容：旧数据无引用字段时前端不渲染标记）。
- `frontend`: 新增行内引用、预览卡与引用列表的展示契约。

## Impact

- **后端**：citation_node / 报告事件负载扩展（引用数组字段）。
- **前端**：Markdown 渲染管线扩展引用标记；预览卡与引用列表组件。
- **测试**：后端负载契约测试；前端标记渲染/预览卡/状态色标的组件测试。
- **验证**：人工验证报告落 `tests/validation/`。
