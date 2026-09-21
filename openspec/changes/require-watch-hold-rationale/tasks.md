## 1. 契约与模型

- [x] 1.1 `TradeDecision` 支持 `inaction_reason` / `reeval_triggers`，噪声形态（null/单字符串/混合列表）清洗不炸管线（含单测）
- [x] 1.2 `AnalysisState` 新增检查键声明，过「节点产出键 ⊆ AnalysisState 声明与图通道」门禁

## 2. 强制回路

- [x] 2.1 trader 侧：watch/hold 缺理由首次 fail 打回一次（feedback 列缺失项、经 context 注入），仍缺放行 + 如实标注（含单测）
- [x] 2.2 终稿侧：`risk_judge` 终稿 watch/hold 缺理由打回一次，仍缺放行 + 如实标注（含单测）
- [x] 2.3 buy/sell 行为不受影响（价检语义回归测试全绿）

## 3. prompt 契约与发布

- [x] 3.1 `trader.md` 输出要求 + JSON 示例补 watch/hold 形态（含字段分工与 ≤3 条触发条件约束）
- [x] 3.2 `risk_judge.md` 继承要求（不得置空）
- [x] 3.3 `uv run python scripts/deploy_prompts.py` 发布通过（prompt-deploy-consistency 门禁可运行）

## 4. 报告渲染

- [x] 4.1 watch/hold 渲染「不行动原因」行 + 结构化「再评估触发条件」编号条目，替换「见理由」占位（含单测）
- [x] 4.2 字段缺失渲染「未申报」，历史形态决策对象兼容不抛异常（含单测）

## 5. 契约同步与全量验证

- [x] 5.1 stub 契约同步（`_STUB_TRADE_DECISION` hold 形态带字段，`test_stub_contract_sync` 绿）
- [x] 5.2 全量后端测试绿（`uv run pytest`）+ ruff/mypy 对触碰文件 0 新增问题
- [x] 5.3 真实链路验证：watch/hold 报告含结构化条目、缺失场景标注如实（依赖 docker/Langfuse，验证报告落 `tests/validation/`）

## 6. 收口

- [x] 6.1 `openspec validate require-watch-hold-rationale --strict` 通过
- [ ] 6.2 sync 主规范 + archive delta
- [x] 6.3 BACKLOG/metrics 台账按需登记（若涉及口径）
