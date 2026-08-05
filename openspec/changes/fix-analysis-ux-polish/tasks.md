# Tasks: fix-analysis-ux-polish

## 1. 已用时后端计时
- [ ] 1.1 后端 `_persist_snapshot` 快照增 `pipeline_start_ts`（取 `_pipeline_start_time` 毫秒）+ 测试
- [ ] 1.2 前端 `types.ts` 快照类型增 `pipeline_start_ts?: number`
- [ ] 1.3 前端 `selectSession` 重建 running 管线 `startedAt` 优先用 `snapshot.pipeline_start_ts`，缺省回退 `Date.now()` + 组件测试

## 2. 工具执行中禁止输入
- [ ] 2.1 `startAnalysis` 在 fetch 前补 `getStreamState(sessionId).abort = localAbort`（sessionId 已知时）
- [ ] 2.2 `quickChat` 同位置补 `getStreamState(currentSessionId).abort = localAbort`
- [ ] 2.3 组件测试：追问路径发起后 `isSessionRunning` 返回 true，发送被拦截

## 3. warning 顶部 toast
- [ ] 3.1 将 warningMessage 渲染从停止按钮容器拆出，改为 `fixed top-16 z-[60] left-1/2 -translate-x-1/2` 独立 toast
- [ ] 3.2 移除原容器对 warningMessage 的条件耦合；停止按钮容器逻辑不变
- [ ] 3.3 组件测试：警告以 fixed 顶部呈现且 z-index > 50

## 4. 澄清回复格式
- [ ] 4.1 定位实时流式丢 `\n` 环节（thinking 流/DSML 剥离路径），补复现测试
- [ ] 4.2 修复使流式渲染与落库格式一致
- [ ] 4.3 测试：流式多行列表渲染与落库一致

## 5. 验证
- [ ] 5.1 后端 + 前端全量测试通过
- [ ] 5.2 前后端重建，人工验证 4 项修复（报告落 tests/validation/）
- [ ] 5.3 E2E 门禁（交互变更）
