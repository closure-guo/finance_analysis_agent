# Tasks: clear-valuation-chain-debts

- [x] D1 GARP 诚实分桶推广到 growth/ROE/负债率（NaN 视同缺失；缺数文案「X 数据缺失（未参与比较）」+ details X_missing；既有真实比较失败文案不变）——TDD 覆盖 None/NaN/真实失败/通过四态 × 三指标
- [x] D2 fetch_peer_data 实现（逐标的复用 fetch_stock_quote 回退链、单标的失败跳过、全失败 None、DataFrame name/PE/PB）+ fetch 层接线消费与缓存语义核查——TDD 覆盖 ADDED requirement 四场景
- [x] D3 fetch_quarterly_income 出口 NaN → None 归一（环比/同比/营收同比数值列）
- [x] D4 报告披露节改编号章节（next_title 机制）+「暂缺」去单位后缀
- [x] D5 api.py SSE 进度健康度取值修正（hs.get("total")）
- [x] D6 图通道门禁扩展 fetch_data 产出键（latest_period_snapshot 等声明+通道断言）
- [x] 回归：ruff / mypy 基线 / 定向套件全绿；688072 实跑抽验相对估值段与 GARP 缺数文案（东财可用时顺带核验主源路径披露节量级——上一 delta 保留意见）
- [x] 人工验证报告落 tests/validation/，openspec validate --strict 通过
