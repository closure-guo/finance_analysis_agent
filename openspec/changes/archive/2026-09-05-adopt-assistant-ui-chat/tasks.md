# Tasks: adopt-assistant-ui-chat

## 1. 基座准备
- [x] 1.1 `npx assistant-ui@latest create -t langgraph` 生成参考实现（独立目录，不并入仓库）→ 实施偏差：基座由 add-assistant-ui-thread 已奠定（@assistant-ui/react@0.15.17 已入仓、官方原语范式已验证），本 change 沿用同一策略（见 tests/validation 验证报告·实施偏差 1）
- [x] 1.2 现有项目 `npx assistant-ui@latest init`，从参考实现搬运 Thread/Composer/Reasoning/ToolFallback/ActionBar 组件 → 以 `src/chat/AnalysisThread.tsx` + `adapter.ts`（原语级自建，源码入仓）承载

## 2. SSE adapter
- [x] 2.1 枚举后端全部 SSE 事件类型，定义消息部件映射表（docs/superpowers/plans/2026-08-30-adopt-assistant-ui-chat.md）
- [x] 2.2 实现 translate 纯函数 + 逐事件类型单测（含未知事件忽略）（src/chat/adapter.ts + src/test/chat/adapter.test.ts，31 例）
- [x] 2.3 接入 runtime，打通流式/中断/刷新重建路径（useExternalStoreRuntime）

## 3. 组件接入
- [x] 3.1 Thread 消息区替换（流式、滚动跟随、中断保留）
- [x] 3.2 思考折叠卡 + 工具调用卡（含运行中拦截语义迁移）
- [x] 3.3 Composer 输入区替换 + 消息操作（复制/重新生成）

## 4. 独有部件
- [x] 4.1 管线时间线、ECharts、导出入口封装为自定义消息部件并挂载

## 5. 验证
- [x] 5.1 既有前端测试无修改通过（仅允许更新选择器）（399/399，零修改）
- [x] 5.2 人工验证三模式/追问/停止/澄清拦截，报告落 tests/validation/
- [x] 5.3 E2E 门禁（e2e/ 基建 P1–P4 已落地；2026-09-05 补跑 stub 套件 20 passed / 2 skipped / 0 failed）
