# Tasks: adopt-assistant-ui-chat

## 1. 基座准备
- [ ] 1.1 `npx assistant-ui@latest create -t langgraph` 生成参考实现（独立目录，不并入仓库）
- [ ] 1.2 现有项目 `npx assistant-ui@latest init`，从参考实现搬运 Thread/Composer/Reasoning/ToolFallback/ActionBar 组件

## 2. SSE adapter
- [ ] 2.1 枚举后端全部 SSE 事件类型，定义消息部件映射表
- [ ] 2.2 实现 translate 纯函数 + 逐事件类型单测（含未知事件忽略）
- [ ] 2.3 接入 runtime，打通流式/中断/刷新重建路径

## 3. 组件接入
- [ ] 3.1 Thread 消息区替换（流式、滚动跟随、中断保留）
- [ ] 3.2 思考折叠卡 + 工具调用卡（含运行中拦截语义迁移）
- [ ] 3.3 Composer 输入区替换 + 消息操作（复制/重新生成）

## 4. 独有部件
- [ ] 4.1 管线时间线、ECharts、导出入口封装为自定义消息部件并挂载

## 5. 验证
- [ ] 5.1 既有前端测试无修改通过（仅允许更新选择器）
- [ ] 5.2 人工验证三模式/追问/停止/澄清拦截，报告落 tests/validation/
- [ ] 5.3 E2E 门禁
