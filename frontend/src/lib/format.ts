// 公共格式化工具（polish-dark-mode-shortcuts：从 App.tsx 抽出，供 CommandPalette 复用）
// 格式化会话时间，对非法/缺失的 created_at 兜底，绝不返回 "Invalid Date"
export function formatSessionTime(ts: string | undefined | null): string {
  if (!ts) return '未知时间'
  const d = new Date(ts)
  if (isNaN(d.getTime())) return '未知时间'
  // 后端用 epoch 占位的脏数据（无法还原真实时间）。浏览器解析 ISO 字符串时
  // 可能按本地时区得到 epoch 之前的负值时间戳，所以用 <= 0 或年份 <= 1970 兜底。
  if (d.getTime() <= 0 || d.getFullYear() <= 1970) return '未知时间'
  return d.toLocaleString()
}
