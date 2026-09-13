## MODIFIED Requirements

### Requirement: 交易价位 sanity 校验

系统 SHALL 在 Trader 产出后运行确定性校验：long 须 stop<entry<target（short 对
称）；entry 距最新收盘偏差 ≤ 配置上限（默认 15%）；stop/target 落在工具参考带内
（±2ATR 放宽带）。校验 SHALL NOT 由 LLM 执行。

buy/sell 决策 SHALL 申报数值价位：entry_price、stop_loss、target_price 任一缺失
（None、≤0）SHALL 视为价位不合法——首次 SHALL 打回并要求申报数值价位（打回
feedback SHALL 列明缺失项）；已打回一次仍缺失 SHALL 放行并如实标注（`price_check`
note 记录「已打回仍未申报」，报告端按「未提供」渲染，不静默、不虚构数值）。
watch/hold 决策无价位要求，维持直通。

#### Scenario: 首次不合法打回

- **GIVEN** Trader 首次产出的价位不通过校验
- **WHEN** 路由判定
- **THEN** SHALL 携带失败原因与 price_levels 参考带打回 Trader 重出（上限 1 次）

#### Scenario: 二次不合法工具修正

- **GIVEN** 打回后产出的价位仍不通过校验
- **WHEN** 路由判定
- **THEN** 系统 SHALL 按工具参考带修正价位
- **AND** 置 `price_level_corrected=true` 与修正原因（报告与 trace 可观测，不静默）

#### Scenario: 合法价位直通

- **WHEN** 价位通过全部校验
- **THEN** SHALL 原样放行，不产生修正标注

#### Scenario: buy/sell 价位缺失首次打回

- **GIVEN** Trader 产出 action=buy 或 sell，且 entry/stop/target 任一缺失（None 或 ≤0）
- **WHEN** 路由判定
- **THEN** SHALL 判 fail 并打回，feedback SHALL 列明缺失项并要求申报数值价位
- **AND** SHALL NOT 静默跳过校验

#### Scenario: 价位缺失打回后仍未申报放行

- **GIVEN** 已打回一次（price_check_attempts ≥ 1）后 buy/sell 决策价位仍缺失
- **WHEN** 路由判定
- **THEN** SHALL 放行（避免死循环）并在 price_check note 如实记录「已打回仍未申报」
- **AND** 报告端渲染「未提供」，SHALL NOT 虚构或估算数值

#### Scenario: watch/hold 无价位要求

- **GIVEN** Trader 产出 action=watch 或 hold
- **WHEN** 路由判定
- **THEN** SHALL 直通（价位缺失不触发打回）
