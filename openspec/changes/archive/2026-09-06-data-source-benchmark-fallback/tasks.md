# Tasks: data-source-benchmark-fallback

## 1. 失败测试（先行，先红）

- [x] 1.1 `tests/data/test_akshare_client.py` 新增 `TestFetchIndexKlineFallback`：mock ak，东财 `index_zh_a_hist` 抛异常时断言回退调用 `stock_zh_index_daily("sh000300")`，返回列含 `日期`/`收盘`
- [x] 1.2 东财返回空 DataFrame 时同样触发回退（空→回退分支）
- [x] 1.3 东财正常返回时 SHALL NOT 调用新浪（主源优先）
- [x] 1.4 双源均失败返回空 DataFrame 且不抛异常
- [x] 1.5 新浪回退列重命名断言：`date→日期`、`close→收盘` 数值一致；缺 `amount`/`turnover` 不报错
- [x] 1.6 `_to_sina_symbol` 指数映射：`000300→sh000300`、`399001→sz399001`

## 2. 实现

- [x] 2.1 `fetch_index_kline` 增加新浪 `stock_zh_index_daily` 回退分支（`_to_sina_symbol(index_code)`），复用 `fetch_kline` 的 rename 模式归一化列名，升序 + tail(days)
- [x] 2.2 若 `_to_sina_symbol` 无法覆盖指数前缀，补指数符号映射（复用股票规则：`000300` 以 `0` 开头 → `sz`，需按 spec 断言调整；若实际需 `sh000300` 则加指数特判）

## 3. 验证与收尾

- [x] 3.1 `uv run pytest tests/data/test_akshare_client.py -k FetchIndexKlineFallback` 全绿
- [x] 3.2 `uv run ruff check src/finance_agent/data/akshare_client.py tests/data/test_akshare_client.py`
- [x] 3.3 `uv run mypy src/finance_agent/data/akshare_client.py`
- [x] 3.4 实跑 `fetch_index_kline("000300")` 验证新浪回退真实数据（人工/脚本验证，记录到 `tests/validation/`）
- [x] 3.5 `openspec validate --strict data-source-benchmark-fallback`
- [x] 3.6 archive 前确认 tasks 全勾 + 门禁通过
