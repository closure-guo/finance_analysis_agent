# Tasks: data-ordering-citation-contract

## 1. 复现测试（先行，先红）

- [x] 1.1 新 `tests/test_macro_order_fix.py`：mock akshare 宏观接口返回降序数据（首行新、尾行旧），断言 `fetch_macro_indicators()["cpi"][0]` 为最新一期且共 6 条（修复前取到 2008 → 红）
- [x] 1.2 断言 `_build_macro_context` 展示的最新 3 期从 index 0 开始（`records[:3]`；修复前 `[-3:]` 取到最老 → 红）
- [x] 1.3 断言 `_build_fundamental_context` 的「近3年」为最新 3 年（2025/2024/2023；修复前 tail(3) 取到 2021-2023 → 红）
- [x] 1.4 （如有）断言 citation `_resolve_field_ref` 对 `macro_indicators.cpi.0` 解析到完整列表 index 0（与 context 一致）

## 2. 实现（按契约修复）

- [x] 2.1 `src/finance_agent/data/akshare_client.py` `fetch_macro_indicators`：`_safe_macro` 内显式 `sort_values(首列, ascending=False)` 后 `head(6)`（替换 `tail(6)`）
- [x] 2.2 `src/finance_agent/nodes/analysts.py` `_build_macro_context`：`records[-3:]` → `records[:3]`
- [x] 2.3 `src/finance_agent/nodes/analysts.py` `_build_fundamental_context`：`df.tail(3)` → `df.head(3)`、`indicators.tail(3)` → `indicators.head(3)`
- [x] 2.4 核实财务三表 fetch（`_sina_report`/`_trim_years`）与 `financial_indicators`（compute_metrics）顺序符合降序契约；如未显式排序则补（记录偏离）

## 3. 验证与收尾

- [x] 3.1 `uv run pytest tests/ --ignore=tests/e2e -m "not live"` + `ruff check` + `mypy`（基线对比）全绿
- [x] 3.2 实跑对账（2026-09-07）：基本面引用最新期（ROE 15.77% 等）、无 2008 旧期误引、管线正常无重试风暴；宏观数据源本次不可用如实报告（排序修复由 9 例单测覆盖）；验证报告 tests/validation/2026-09-07-real-run-four-deltas-validation.md
