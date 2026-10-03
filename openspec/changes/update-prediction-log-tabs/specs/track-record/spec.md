# Delta for track-record

## MODIFIED Requirements

### Requirement: 观点列表过滤

`GET /api/v1/track-record/predictions` 的 `status` 参数 SHALL 支持组值 `resolved`:传 `status=resolved` 时返回全部非 open 状态(resolved_win/resolved_loss/resolved_neutral/avoidance/unresolvable 及后续新增的非 open 终态)的记录;其余取值 SHALL 保持精确匹配语义不变。分页 total SHALL 反映过滤后子集。
(Previously: status 仅精确匹配单一状态值。)

#### Scenario: resolved 组过滤

- **WHEN** 请求 `?status=resolved`
- **THEN** 响应仅含非 open 状态记录,total 为该子集大小

#### Scenario: 精确匹配语义不变

- **WHEN** 请求 `?status=open` 或 `?status=resolved_win`
- **THEN** 行为与既有精确匹配一致
