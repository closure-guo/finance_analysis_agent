# Tasks: toolize-price-levels

## 1. 价位预算工具

- [ ] 1.1 失败测试先行：calc_price_levels（高低点/ATR/支撑阻力/止损带/目标带，
       数据不足时字段缺失标注）
- [ ] 1.2 metrics/levels.py 实现 + compute_metrics 挂载写入 state.price_levels

## 2. Trader sanity 校验

- [ ] 2.1 失败测试先行：校验规则（价格关系/偏差上限/参考带）与三路路由
       （直通/打回/修正）
- [ ] 2.2 validate_trade_prices 节点 + after_validate_trade_prices 路由
       （打回 1 次 + 工具参考带修正，price_level_corrected 可观测）
- [ ] 2.3 trader context 注入 price_levels + 打回时附失败原因
- [ ] 2.4 图接线（trader → validate → …）+ 报告渲染修正标注

## 3. quick 快照与派生值

- [ ] 3.1 失败测试先行：search_stock 结果快照字段 + 数据缺失标注
- [ ] 3.2 search_stock 附带 price/pct_change（工具数据）
- [ ] 3.3 失败测试先行：派生值表（区间涨跌幅/距高低点回撤反弹，数据不足标注缺失）
- [ ] 3.4 metrics/technical.py calc_derived_series + technical analyst context 注入

## 4. 验证

- [ ] 4.1 uv run pytest / ruff / mypy 全绿
- [ ] 4.2 E2E 门禁回归（stub 链路含 sanity 节点路由）
- [ ] 4.3 人工验证报告落 tests/validation/（真实链路核对 price_levels 注入与
       修正标注可观测）
