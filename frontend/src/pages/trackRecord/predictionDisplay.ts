// 方向/判定规则中文映射单一真源（update-track-record-display-clarity）：
// 列表与详情共用，避免两处漂移；原始英文值由调用方以 title 辅助保留供排查。
export const DIRECTION_LABEL: Record<string, string> = {
  long: '看多',
  short: '看空',
  neutral: '中性',
}

export const RESOLUTION_RULE_LABEL: Record<string, string> = {
  expiry: '到期结算',
  superseded: '被新观点替代·提前结算',
  duplicate_of_day: '同日重复关闭',
  stale_no_market: '长期无行情',
}
