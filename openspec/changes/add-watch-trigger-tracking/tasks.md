# Tasks: add-watch-trigger-tracking

- [ ] `TradeDecision` 新增 `trigger_high`/`trigger_low`（宽松清洗，不抛异常）+ 单测
- [ ] 终稿完整性检查扩展：watch 终稿缺触发位打回一次、仍缺放行 + 如实标注 + 单测
- [ ] `trader.md` prompt 加触发位申报纪律（方向语义 + 与 reeval_triggers 并存），并执行 `scripts/deploy_prompts.py` 发布
- [ ] 价位门禁：结构化触发位方向校验（空洞 anomaly，共用一次打回预算，fail-open）+ 单测
- [ ] K 线采集携带触发位 + 服务端 PNG 画「上破触发/下破触发」参考线 + 单测
- [ ] 前端 K 线组件渲染触发位参考线（与入场/止损/目标可区分样式）
- [ ] 报告「交易决策」节：触发位行（缺失如实「未申报」）+ 入池跟踪声明行 + 数据真空提示行（阈值配置化）+ 单测
- [ ] `predictions` 表 ALTER 加 `session_id`/`trigger_high`/`trigger_low` 列 + ingest 落库 + 存量 NULL 不追溯 + 单测
- [ ] E2E spec 覆盖 watch 报告 K 线触发位参考线渲染（交互类变更门禁）
- [ ] 复跑一只 watch 标的端到端验证：报告触发位行 / K 线虚线 / predictions 行三处一致可见
- [ ] 人工验证报告落 `tests/validation/`
