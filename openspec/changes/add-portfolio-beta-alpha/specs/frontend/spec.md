# Delta for frontend

## ADDED Requirements

### Requirement: 总览 β/α 指标位

战绩页总览指标区 SHALL 新增两个指标位:「β 市场敞口」与「α 年化超额」。β 显示两位小数(如 0.85 / −1.20,无百分号);α 沿 Delta 组件带符号百分比格式;两格 SHALL 各配一句口径副标题(β:接近 1 满仓跟随大盘,负值=反向敞口;α:剔除大盘影响后的独立判断收益)。后端 beta/jensen_alpha 为 null(样本不足)时两格 SHALL 显示 "—" 且不渲染副标题数字误导。

#### Scenario: 正常渲染

- **GIVEN** overview 返回 portfolio.beta = 0.85、portfolio.jensen_alpha = 0.031
- **WHEN** 用户打开战绩页
- **THEN** 「β 市场敞口」格显示 0.85,「α 年化超额」格显示 +3.10%
- **AND** 两格副标题可见

#### Scenario: 样本不足置空

- **GIVEN** overview 返回 beta/jensen_alpha 为 null
- **WHEN** 用户打开战绩页
- **THEN** 两格显示 "—",页面其余指标不受影响

#### Scenario: 负 β 展示

- **GIVEN** overview 返回 beta = −1.20(净空结构)
- **WHEN** 用户打开战绩页
- **THEN** β 格显示 −1.20,不带百分号
