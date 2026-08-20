## MODIFIED Requirements

### Requirement: litellm 适配收口

`src/finance_agent/` 内仅 `llm/adapters/**` SHALL import litellm（CI grep 门禁，已收紧为仅 adapter）。evals judge SHALL 经 resolver/gateway 调用 LLM（不再直连 litellm.completion），judge purpose 解析保持 JUDGE_* 独立映射。adapter SHALL 白名单化参数发送：移除全局 `litellm.drop_params=True` 静默丢弃，业务请求中 capability 不支持的关键参数（tools/tool_choice=required/response_format=json_schema/未登记 provider_options key）MUST 显式抛 UnsupportedCapabilityError；历史依赖 drop_params 吸收的参数组合 MUST 经合同测试确认后显式声明或移除。
(Previously: adapter 保留全局 drop_params=True；evals/judges.py 直连 litellm.completion。)

#### Scenario: judge 经统一入口
- **WHEN** 评估跑批发起 judge 调用
- **THEN** 请求经 resolver 解析 judge purpose（JUDGE_* 环境映射）并由 gateway 下发，trace 带独立 environment 审计

#### Scenario: 关键参数不再静默丢弃
- **WHEN** 请求携带 capability 不支持的 tool_choice=required
- **THEN** 显式抛 UnsupportedCapabilityError，而非被静默 drop 后行为漂移

#### Scenario: 非关键参数白名单
- **WHEN** 请求携带 provider 已知可忽略的次要参数
- **THEN** adapter 按白名单显式剔除并记 trace warning，不触发报错
