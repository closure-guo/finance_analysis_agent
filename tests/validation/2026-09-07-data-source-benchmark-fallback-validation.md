# 验证报告: data-source-benchmark-fallback

**日期**: 2026-09-07
**验证人**: [agent]（真实数据运行验证，东财风控真实场景触发回退）
**关联 delta**: openspec/changes/data-source-benchmark-fallback/

## 验证范围

`fetch_index_kline` 在东方财富 `index_zh_a_hist` 失败时回退新浪 `stock_zh_index_daily`，返回列归一化为主源同构中文列。单元测试 9 项（mock）+ 真实数据验证 1 项。

## 单元测试结果（tests/data/test_akshare_client.py）

| 用例 | 断言 | 结果 |
|---|---|---|
| test_em_success_no_sina_call | 东财正常时直接返回、不调用新浪 | ✅ |
| test_em_exception_falls_back_to_sina | 东财抛 ConnectionError → 回退新浪，列含 日期/收盘，调用 `stock_zh_index_daily(symbol="sh000300")` | ✅ |
| test_em_empty_falls_back_to_sina | 东财空 DataFrame → 回退新浪 | ✅ |
| test_both_fail_returns_empty | 双源失败返回空、不抛异常 | ✅ |
| test_sina_missing_optional_cols_ok | 新浪缺 volume 列不报错、无对应中文列 | ✅ |
| TestSinaIndexSymbolMapping × 4 | 000300→sh000300 / 000001→sh000001 / 399001→sz399001 / 399006→sz399006 | ✅ |

回归：`tests/data/ tests/nodes/test_fetch.py tests/outcome/{test_track_record_job,test_track_record_metrics,test_job,test_settle}.py` → 104 passed。

## 真实数据验证（真实回退触发）

2026-09-07 实跑 `fetch_index_kline("000300", days=5)`：

- 东财 `index_zh_a_hist` 3 次重试全部 ConnectionError（东财 TLS 指纹风控，与 incident 024 一致）
- 回退分支触发：新浪 `stock_zh_index_daily("sh000300")` 成功
- 返回 5 行真实沪深 300 日 K，列名已归一化：`日期/开盘/最高/最低/收盘/成交量`
- 数据截至 2026-09-04（最近交易日），`收盘` 序列：4625.086 / 4611.439 / 4547.956 / 4552.578 / 4548.050

## 结论

主源失败 → 回退 → 归一化列名的完整链路在真实风控场景下验证通过，下游消费者（calc_risk 的 `收盘`、outcome 的 `日期`+`收盘`）零改动可用。双源失败仍返回空 DataFrame，与现状语义一致。
