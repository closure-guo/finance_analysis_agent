# citation-verification Specification Delta

## ADDED Requirements

### Requirement: 计算型声明重算注册表全覆盖

计算型 claim 的重算注册表 SHALL 覆盖 `metrics/` 模块的全部纯函数指标族（偿债、盈利、运营、现金流、杜邦、技术指标、风控指标），每个注册根键 SHALL 有独立的重算 fixture 测试（从原始报表数据重算，不依赖 LLM、不调外部接口）。未注册根键的计算型 claim SHALL 判 UNVERIFIABLE，且 SHALL 计入覆盖缺口指标供覆盖率审计。

#### Scenario: 已注册指标重算通过

- **GIVEN** Agent 报告含计算型 claim（如 `solvency_metrics.资产负债率.2024`），其根键已注册
- **WHEN** 执行校验
- **THEN** 系统 SHALL 从 state 原始数据经对应纯函数重算 ground-truth，按相对容差 0.5% 判定 PASS/FAIL

#### Scenario: 未注册根键显式降级

- **WHEN** 计算型 claim 的根键未在注册表中
- **THEN** 校验结果 SHALL 为 UNVERIFIABLE
- **AND** 该事件 SHALL 计入覆盖缺口计数，SHALL NOT 静默等同于 FAIL 或被忽略

#### Scenario: 容差语义不回归

- **WHEN** 注册表扩展后执行任意校验
- **THEN** 数值容差（绝对 0.01 / 相对 0.5%）与三态裁决（PASS/FAIL/UNVERIFIABLE）语义 SHALL 与既有契约一致

### Requirement: UNVERIFIABLE 占比监控

系统 SHALL 在每次引用校验完成后向 Langfuse 上报 Score `citation_unverifiable_ratio`（UNVERIFIABLE 占全部 claim 比例），关联 `langfuse_trace_id`。该指标 SHALL 作为数据层退化（数据源接口变更、事件管线降级、注册表覆盖缺口扩大）的先行监控信号。

#### Scenario: 占比上报

- **WHEN** citation_node 完成一次批量校验
- **THEN** 系统 SHALL 上报 `citation_unverifiable_ratio`（0-1 浮点）至 Langfuse，与既有 `citation_pass` 并列
- **AND** Langfuse 不可用时 SHALL 记 WARN 且不阻断业务管线

#### Scenario: 占比突升告警

- **GIVEN** `citation_unverifiable_ratio` 的滚动均值较基线上升超过阈值（默认 +10pp，可配置）
- **WHEN** 监控任务检测到突升
- **THEN** 系统 SHALL 产生告警记录，提示排查数据层或注册表覆盖缺口
