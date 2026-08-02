// 管线 ETA 动态预估模块（fix-pipeline-banner-and-eta Task 3.2）。
// 初始预估取历史运行耗时中位数（localStorage），运行中随实际进度线性收敛，
// 避免硬编码静态文案（原 ~90s 与实际 ~258s 严重失真）。

// 无历史记录时的默认预估总时长（参考 incident 008 实测 ~258s 取整）
export const DEFAULT_ESTIMATED_TOTAL_MS = 240_000

const STORAGE_KEY = 'financeAgent.pipelineDurations'
const MAX_HISTORY = 10

// 读取历史运行耗时（毫秒）。数据损坏或 localStorage 不可用时返回空数组。
export function loadDurations(): number[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((v): v is number => typeof v === 'number' && v > 0)
  } catch {
    return []
  }
}

// 写入一次完整运行耗时，最多保留 10 条（超出淘汰最旧）。
export function recordDuration(durationMs: number): void {
  if (durationMs <= 0) return
  try {
    const durations = [...loadDurations(), durationMs].slice(-MAX_HISTORY)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(durations))
  } catch {
    // localStorage 不可用（隐私模式等）：静默跳过，不阻塞功能
  }
}

// 初始预估总时长：历史记录中位数；无历史用默认值。
export function estimateTotalMs(durations: number[]): number {
  if (durations.length === 0) return DEFAULT_ESTIMATED_TOTAL_MS
  const sorted = [...durations].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

// 预估剩余时长（毫秒）。
// 当实际进度比例 p 超过 已用时长/预估总时长 隐含的进度时，用 已用时长/p 线性外推重估总时长；
// 剩余 = max(0, 重估总时长 - 已用时长)。
export function estimateRemainingMs(elapsedMs: number, progress: number, estimatedTotalMs: number): number {
  if (progress >= 1) return 0
  let total = estimatedTotalMs
  if (progress > 0) {
    const impliedByProgress = elapsedMs / progress
    // 实际进度领先于预估 → 线性外推收敛总时长
    if (impliedByProgress < total) total = impliedByProgress
  }
  return Math.max(0, total - elapsedMs)
}

// 格式化毫秒为 M:SS（秒补零）
export function formatDurationMs(ms: number): string {
  const totalSec = Math.round(ms / 1000)
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  return `${min}:${String(sec).padStart(2, '0')}`
}
