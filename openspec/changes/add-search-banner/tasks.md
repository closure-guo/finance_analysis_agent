# Tasks: add-search-banner

## 验收 Checklist

- [x] 快速模式搜索横幅渲染：收到 search_start 事件时，助手消息中显示"正在搜索：{query}"搜索横幅（脉冲动画）
- [x] 快速模式搜索结果展示：收到 search_result 事件时，搜索横幅显示"搜索了 N 个网页"，可展开查看网页列表（标题 + URL + 摘要 + favicon）
- [x] 快速模式搜索失败展示：收到 search_error 事件时，搜索横幅显示错误状态
- [x] 深度模式搜索横幅渲染：澄清阶段的 search_result 事件以独立搜索横幅展示（而非 ToolCallBanner 摘要）
- [x] 搜索横幅可折叠：默认折叠搜索结果列表，点击展开/收起
- [ ] 搜索横幅与思考横幅/工具调用横幅视觉协调，不重叠
- [ ] 人工验证报告落 tests/validation/
