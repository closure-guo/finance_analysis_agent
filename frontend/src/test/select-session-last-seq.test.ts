import { describe, it, expect } from 'vitest'
import { resumeAfterSeqFromSnapshot } from '../App'

// 回归：selectSession 快照恢复路径曾用 Math.max(frontLastSeq, backLastSeq) 推进 after_seq。
// 后端 last_seq 是 journal 全量 max，远超前端渲染进度时，resumeStream 跳过前端未渲染的
// 中间事件，导致流式文字内容缺失（如「寒武纪（688256）」变「武（256」）。
// 两 session 同时运行时后端事件增长更快、backLastSeq 更大 → 必然跳过更多 → 必然发生。
// 修复：前端 lastSeq（实际渲染进度）优先，仅 0 时用后端 last_seq 兜底。

describe('resumeAfterSeqFromSnapshot（快照恢复 after_seq 计算）', () => {
  it('前端 lastSeq > 0 时用它续传，不被后端 max 超前推进', () => {
    // 前端渲染到 seq=50，后端 journal 已到 seq=100
    // 修复前 Math.max(50,100)=100 → 跳过 51-100 → 内容缺失
    expect(resumeAfterSeqFromSnapshot(50, 100)).toBe(50)
  })

  it('前端 lastSeq = 0（从未收到事件）时用后端 last_seq 兜底', () => {
    expect(resumeAfterSeqFromSnapshot(0, 100)).toBe(100)
  })

  it('前端已追平后端时从当前位置续传', () => {
    expect(resumeAfterSeqFromSnapshot(100, 100)).toBe(100)
  })

  it('对比：旧 Math.max 会错误跳过未渲染事件（文档化根因）', () => {
    const frontLastSeq = 50
    const backLastSeq = 100
    // 旧代码 Math.max 行为：after_seq=100，跳过 51-100 的未渲染事件
    expect(Math.max(frontLastSeq, backLastSeq)).toBe(100)
    // 修复后：after_seq=50，resumeStream 收到 51-100 并 append 到快照消息
    expect(resumeAfterSeqFromSnapshot(frontLastSeq, backLastSeq)).toBe(50)
  })
})
