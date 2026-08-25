# Delta for Macro Data Freshness

## ADDED Requirements

### Requirement: 宏观数据时效标记

宏观数据管道（`fetch_macro_indicators`）MUST 在返回的每个指标下附带数据时效元数据：最新数据日期（as_of_date）与时效状态（fresh/stale），阈值以最新数据日期距今 3 个月为界。

#### Scenario: 指标数据新鲜

- **GIVEN** 指标（如 M2、LPR）最新数据日期在当前日期 3 个月内
- **WHEN** fetch_macro_indicators 被调用
- **THEN** 该指标返回 freshness=fresh
- **AND** 返回 as_of_date 为该指标最新记录的真实日期

#### Scenario: 指标数据滞后

- **GIVEN** 指标（如 PMI、CPI 接口）最新数据日期距今超过 3 个月
- **WHEN** fetch_macro_indicators 被调用
- **THEN** 该指标返回 freshness=stale
- **AND** 返回 as_of_date 为滞后记录的真实日期（不与其他较新指标混淆）

#### Scenario: 拉取失败无时效信息

- **GIVEN** 指标拉取失败（接口异常或返回空）
- **WHEN** fetch_macro_indicators 被调用
- **THEN** 该指标返回空列表（沿用现状，不因守卫改变失败语义）

#### Scenario: 字段向后兼容

- **GIVEN** 既有调用方消费 macro_indicators state 字段
- **WHEN** fetch_macro_indicators 返回结构追加时效字段
- **THEN** 既有字段名与记录结构保持不变，新增键（as_of_date/freshness）可被新消费方读取，既有消费方不受影响