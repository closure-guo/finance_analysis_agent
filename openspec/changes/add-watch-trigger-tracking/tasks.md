# Tasks: add-watch-trigger-tracking

- [x] `TradeDecision` 新增 `trigger_high`/`trigger_low`（宽松清洗，不抛异常）+ 单测
- [x] 终稿完整性检查扩展：watch 终稿缺触发位打回一次、仍缺放行 + 如实标注 + 单测
- [x] `trader.md`/`risk_judge.md` prompt 加触发位申报纪律（方向语义 + 与 reeval_triggers 并存；合同测试 88+16 绿）
- [ ] `scripts/deploy_prompts.py` Langfuse 发布——合并后 ops 窗口执行（容器 env 前置），未发布前 eval 门禁拒绝运行
- [x] 价位门禁：结构化触发位方向校验（空洞 anomaly，共用一次打回预算，fail-open）+ 单测
- [x] K 线采集携带触发位 + 服务端 PNG 画「上破触发/下破触发」参考线 + 单测
- [x] 前端 K 线组件渲染触发位参考线（与入场/止损/目标可区分样式）
- [x] 报告「交易决策」节：触发位行（缺失如实「未申报」）+ 入池跟踪声明行 + 数据真空提示行（阈值配置化）+ 单测
- [x] `predictions` 表 ALTER 加 `session_id`/`trigger_high`/`trigger_low` 列 + ingest 落库 + 存量 NULL 不追溯 + 单测
- [ ] E2E spec 覆盖 watch 报告 K 线触发位参考线渲染——**如实注记：§5.6 Playwright e2e/ 基建未建设（P1-P4 pending）**，本 delta 以前端 vitest 契约（653/653 绿，含触发位 markLine 正反用例）+ 人工浏览器验证替代，不静默勾选
- [ ] 复跑一只 watch 标的端到端验证：报告触发位行 / K 线虚线 / predictions 行三处一致可见
- [ ] 人工验证报告落 `tests/validation/`
