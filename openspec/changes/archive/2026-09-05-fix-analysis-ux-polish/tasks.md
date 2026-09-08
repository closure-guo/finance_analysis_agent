# Tasks: fix-analysis-ux-polish

## 1. 已用时后端计时
- [x] 1.1 后端 `_persist_snapshot` 快照增 `pipeline_start_ts`（pipeline_runner.py）+ 测试（tests/test_pipeline_start_ts.py）
- [x] 1.2 前端 `types.ts` 快照类型增 `pipeline_start_ts?: number`
- [x] 1.3 计时源语义实现（streamStore updatePipelineSnapshot 以 pipeline_start_ts 为准，缺省回退本地）+ 组件测试（pipelineSummary.test.tsx）；spec 层由 enhance-pipeline-progress「节点已用时」覆盖（2026-09-05 归档），本 delta spec 不再重复

## 2. 工具执行中禁止输入
- [x] 2.1 发起前登记活跃读取器（streamStore refactor 后等价实现：submit/pump 在 fetch 前建立 activeReader 单读取器保证）
- [x] 2.2 quick 通道运行状态由 AG-UI runtime 判定（adopt-assistant-ui-thread/chat 迁移），单飞守卫等价生效
- [x] 2.3 组件测试（running-guard-toast.test.tsx：运行中 composer 切停止按钮、Enter 不发新请求）

## 3. warning 顶部 toast
- [x] 3.1 warningMessage 拆为 `fixed top-16 z-[60] left-1/2 -translate-x-1/2` 独立 toast（App.tsx）
- [x] 3.2 停止按钮容器与警告解耦
- [x] 3.3 组件测试（running-guard-toast.test.tsx：fixed/top-16/z-[60] 断言 + 3 秒自动消失；经可驱动的 409 路径触发同一 toast 容器）

## 4. 澄清回复格式
- [x] 4.1 定位流式丢单换行环节并补复现测试（multiline-list-stream.test.tsx）
- [x] 4.2 流式渲染与落库格式一致
- [x] 4.3 测试：流式多行列表渲染与落库一致（multiline-list-stream.test.tsx）

## 5. 验证
- [x] 5.1 后端 + 前端全量测试通过（2026-09-05：前端 489/489；后端 not-live 门禁全绿，live 用例按规范归 nightly）
- [x] 5.2 验证报告落 tests/validation/2026-09-05-fix-analysis-ux-polish-validation.md
- [x] 5.3 E2E 门禁（2026-09-05：stub 套件 20 passed / 2 skipped / 0 failed）
