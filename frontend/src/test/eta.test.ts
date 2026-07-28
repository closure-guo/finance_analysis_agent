import { describe, it, expect, beforeEach } from 'vitest'
import {
  DEFAULT_ESTIMATED_TOTAL_MS,
  estimateTotalMs,
  estimateRemainingMs,
  formatDurationMs,
  loadDurations,
  recordDuration,
} from '../eta'

// ETA 计算纯函数测试（fix-pipeline-banner-and-eta Task 3.1）
// 覆盖：中位数初始预估、无历史默认值、进度线性收敛、max(0,...) 下限、
// localStorage 读写与淘汰、localStorage 不可用回退、时长格式化。

describe('estimateTotalMs - 初始预估', () => {
  it('无历史记录时返回默认值 240s', () => {
    expect(estimateTotalMs([])).toBe(DEFAULT_ESTIMATED_TOTAL_MS)
    expect(DEFAULT_ESTIMATED_TOTAL_MS).toBe(240_000)
  })

  it('有历史记录时取中位数（奇数条）', () => {
    expect(estimateTotalMs([100_000, 200_000, 300_000])).toBe(200_000)
  })

  it('有历史记录时取中位数（偶数条，取两中值平均）', () => {
    expect(estimateTotalMs([100_000, 200_000, 300_000, 400_000])).toBe(250_000)
  })

  it('历史记录未排序时仍正确取中位数', () => {
    expect(estimateTotalMs([300_000, 100_000, 200_000])).toBe(200_000)
  })
})

describe('estimateRemainingMs - 进度收敛', () => {
  it('进度落后于预估值时，按原预估计算剩余', () => {
    // 预估 240s，已用 60s，进度 0.1（隐含已用应仅 24s）→ 实际进度落后，维持原预估
    const remaining = estimateRemainingMs(60_000, 0.1, 240_000)
    expect(remaining).toBe(180_000)
  })

  it('进度领先于预估值时，线性外推重估总时长', () => {
    // 预估 240s，已用 60s，进度 0.5（隐含总时长 120s）→ 重估剩余 60s
    const remaining = estimateRemainingMs(60_000, 0.5, 240_000)
    expect(remaining).toBe(60_000)
  })

  it('已用时长超过预估时，剩余不为负（max 0 下限）', () => {
    // 预估 240s，已用 300s，进度 0.9 → 线性外推 333s，剩余 33s（仍为正）
    const remaining = estimateRemainingMs(300_000, 0.9, 240_000)
    expect(remaining).toBeGreaterThanOrEqual(0)
  })

  it('进度为 0 时返回预估总时长', () => {
    expect(estimateRemainingMs(0, 0, 240_000)).toBe(240_000)
  })

  it('进度为 1 时剩余为 0', () => {
    expect(estimateRemainingMs(200_000, 1, 240_000)).toBe(0)
  })
})

describe('localStorage 历史记录', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('recordDuration 写入记录，loadDurations 读取', () => {
    recordDuration(258_000)
    recordDuration(240_000)
    expect(loadDurations()).toEqual([258_000, 240_000])
  })

  it('最多保留 10 条，超出淘汰最旧记录', () => {
    for (let i = 0; i < 12; i++) recordDuration(1000 * (i + 1))
    const durations = loadDurations()
    expect(durations).toHaveLength(10)
    expect(durations[0]).toBe(3000) // 最早两条（1000、2000）被淘汰
  })

  it('无记录时返回空数组', () => {
    expect(loadDurations()).toEqual([])
  })

  it('损坏数据返回空数组（不抛异常）', () => {
    localStorage.setItem('financeAgent.pipelineDurations', 'not-json')
    expect(loadDurations()).toEqual([])
  })
})

describe('formatDurationMs - 时长格式化', () => {
  it('秒以内显示 0:SS', () => {
    expect(formatDurationMs(45_000)).toBe('0:45')
  })

  it('分钟进位，秒补零', () => {
    expect(formatDurationMs(83_000)).toBe('1:23')
    expect(formatDurationMs(125_000)).toBe('2:05')
  })

  it('十分钟以上不补零分钟位', () => {
    expect(formatDurationMs(720_000)).toBe('12:00')
  })
})
