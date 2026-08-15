# data-fetching Specification

## Purpose
数据取数契约：时间序列数据的排序约定与取数窗口，确保分析师与校验方看到一致且最新的数据。

## ADDED Requirements

### Requirement: 时间序列数据降序排列（index 0 = 最新）

进入分析 state 的时间序列数据（宏观指标、财务三表、财务指标等）SHALL 按「降序、index 0 = 最新一期」排列，使分析师与 citation 校验方对同一索引引用到同一数据元素。

#### Scenario: 宏观指标最新一期在 index 0

- **WHEN** `fetch_macro_indicators` 取到宏观数据（如 CPI/PMI/M2/LPR）
- **THEN** 返回的每条序列的 `[0]` SHALL 为最新一期（如 2026 年数据），而非最老一期（如 2008 年数据）

#### Scenario: 财务三表最新年报在 index 0

- **WHEN** 财务三表（资产负债表/利润表/现金流量表）进入 state
- **THEN** 数据 SHALL 按「降序、最新年报在前」排列，`head(N)` 即最新 N 年

### Requirement: fetch 层显式排序（不依赖数据源隐藏顺序）

数据抓取层 SHALL 在返回前显式按日期列排序（降序），使「index 0 = 最新」契约不依赖 akshare 等数据源的内部顺序（即使数据源改变排序方式，契约仍成立）。

#### Scenario: 显式排序保证顺序

- **WHEN** 任一时间序列抓取完成（即使数据源返回顺序不确定）
- **THEN** 系统 SHALL 显式按日期列排序为降序后返回

### Requirement: 宏观指标取数窗口

宏观指标（CPI/PMI/M2/LPR）SHALL 每次取最近 6 期，供分析师 context 与 citation 校验使用。

#### Scenario: 取最新 6 期

- **WHEN** `fetch_macro_indicators` 执行
- **THEN** 每个指标 SHALL 返回最近 6 期数据（index 0 = 最新）
