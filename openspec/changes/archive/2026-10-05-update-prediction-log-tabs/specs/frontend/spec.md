# Delta for frontend

## ADDED Requirements

### Requirement: 观点日志标题与状态 tab

战绩页观点表 SHALL 增加区块标题「观点日志」(副标题注明:每条 = 一次分析结论;当前持有 = 仍在 20 日判定窗口内)与三个状态 tab:**当前持有 / 已判定 / 全部**。缺省 SHALL 为「当前持有」(status=open,与总览卡观点总数同口径);tab 映射:当前持有 → status=open,已判定 → status=resolved(非 open 全集),全部 → 不过滤。切换 tab SHALL 重置分页并按服务端过滤重新拉取;当前 active tab SHALL 有视觉标识;表格行数变化时徽标(当前 tab 的 total)SHALL 随响应更新。

#### Scenario: 缺省当前持有

- **GIVEN** 库内有 57 条 open 与 51 条已判定观点
- **WHEN** 用户进入战绩页
- **THEN** 「当前持有」tab 为 active,请求携带 status=open,表格仅显示 open 记录,分页 total 为 57

#### Scenario: 切换已判定

- **WHEN** 用户点击「已判定」tab
- **THEN** 请求携带 status=resolved,分页重置为第 1 页,total 更新为已判定子集大小

#### Scenario: 全部审计视图

- **WHEN** 用户点击「全部」tab
- **THEN** 请求不携带 status 参数,表格显示全部状态记录
