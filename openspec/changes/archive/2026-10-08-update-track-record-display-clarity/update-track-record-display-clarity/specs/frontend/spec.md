# Delta for frontend

## MODIFIED Requirements

### Requirement: 观点日志标题与状态 tab

战绩页观点表 SHALL 增加区块标题「观点日志」(副标题注明:每条 = 一次分析结论;当前持有 = 仍在判定窗口内，窗口长短见「窗口」列)与三个状态 tab:**当前持有 / 已判定 / 全部**。缺省 SHALL 为「当前持有」(status=open);tab 映射:当前持有 → status=open,已判定 → status=resolved(非 open 全集),全部 → 不过滤。切换 tab SHALL 重置分页并按服务端过滤重新拉取;当前 active tab SHALL 有视觉标识;表格行数变化时徽标(当前 tab 的 total)SHALL 随响应更新。副标题 SHALL NOT 硬编码具体窗口天数（窗口口径由「窗口」列逐行承载，旧口径 252 行同样被副标题覆盖，不得产生「均在 20 日窗口内」的误导）。
(Previously: 副标题为「当前持有 = 仍在 20 日判定窗口内」——硬编码 20 日，对混入的 252 旧口径 open 行不成立（update-track-record-display-clarity 审计 §一）。)

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

#### Scenario: 副标题不硬编码窗口天数

- **GIVEN** 当前持有 tab 内混有 T+20 与 T+252 两种窗口的 open 行
- **WHEN** 渲染区块副标题
- **THEN** 副标题 SHALL 表述为「仍在判定窗口内」且窗口长短指向「窗口」列
- **AND** SHALL NOT 出现「20 日判定窗口」字样
