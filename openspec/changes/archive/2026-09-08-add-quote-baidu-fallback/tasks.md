# Tasks: add-quote-baidu-fallback

## 1. 失败测试（先行，先红）

- [x] 1.1 `tests/data/test_akshare_client.py`：东财失败 → 调用百度取 market_cap/PB + 腾讯取 price，返回含三字段
- [x] 1.2 百度市净率失败不影响总市值（部分成功）
- [x] 1.3 全部回退失败 → 仅名称 + ERROR 日志
- [x] 1.4 东财正常不触发回退（既有用例回归）

## 2. 实现

- [x] 2.1 `fetch_stock_quote` 东财失败后补百度估值（总市值/PB）+ 腾讯日线 price，逐项独立 try/except

## 3. 验证与收尾

- [x] 3.1 `uv run pytest tests/data/test_akshare_client.py` 全绿（33 passed）
- [x] 3.2 `uv run ruff check` + mypy（无新增）
- [x] 3.3 实跑验证：东财被墙环境下 quote 恢复 market_cap=1846.54/PB=14.52/price=632.0
- [x] 3.4 `openspec validate --strict add-quote-baidu-fallback`
- [x] 3.5 archive 前 tasks 全勾 + 门禁通过