# Tasks: update-agent-prompt-cycle-fit

## 1. 数据时效守卫

- [ ] 1.1 `akshare_client.py` `fetch_macro_indicators` 追加 as_of_date + freshness（阈值 90 天，各指标独立计算，解析失败默认 stale 并 warning）
- [ ] 1.2 新增守卫单测：M2/LPR 新鲜→fresh、PMI/CPI 滞后→stale、月字符串/ISO 日期两种格式、拉取失败仍返回空列表、字段向后兼容
- [ ] 1.3 macro context 组装处消费 freshness（数据滞后时以确定性方式附加"滞后至 YYYY-MM"标注，而非仅依赖 LLM 自觉）

## 2. 分析师提示词周期感知

- [ ] 2.1 fundamental_analyst.md 方法论改为"同业相对 + 周期调整"表述（ROE 15%/负债率 60% 等降级为参考阈值）
- [ ] 2.2 technical_analyst.md 补"强趋势中 RSI/KDJ 钝化、以 MA 趋势为主"提示
- [ ] 2.3 macro_analyst.md 补 M1/M2 剪刀差判读 + 数据滞后降级语义

## 3. 契约测试与验证

- [ ] 3.1 契约测试更新：断言方法论周期感知关键词（fundamental/technical/macro 各若干），`uv run pytest` 通过
- [ ] 3.2 `uv run ruff check` + `uv run mypy` 通过
- [ ] 3.3 全量回归（非 live）通过

## 4. 发布与评估

- [ ] 4.1 Langfuse 发布 ver=3（如启用）并确认与本地一致
- [ ] 4.2 人工抽查/可选 eval 对照周期适配收益；验证报告落 tests/validation/