# Tasks: kline-tencent-fallback

## 1. 失败测试（先行，先红）

- [x] 1.1 `tests/data/test_akshare_client.py` 新增：东财 + 新浪均抛异常 → 回退腾讯 `stock_zh_a_hist_tx("sh600519", adjust="qfq")`，返回列归一化（`日期`/`收盘`）
- [x] 1.2 新浪失败、腾讯成功：列重命名断言（date→日期、close→收盘 数值一致）
- [x] 1.3 东财成功时不调用新浪/腾讯（既有用例回归）
- [x] 1.4 三级全失败返回空 DataFrame 不抛异常

## 2. 实现

- [x] 2.1 `fetch_kline` 新浪失败后补腾讯 `stock_zh_a_hist_tx` 分支（`_to_sina_symbol` 前缀、qfq、rename_map 复用），升序 + tail(days)

## 3. 验证与收尾

- [x] 3.1 `uv run pytest tests/data/` 全绿
- [x] 3.2 `uv run ruff check` + mypy
- [x] 3.3 实跑验证：模拟东财+新浪失败（或直接调 fetch_kline 看腾讯回退真实数据）
- [x] 3.4 `openspec validate --strict kline-tencent-fallback`
- [x] 3.5 archive 前 tasks 全勾 + 门禁通过