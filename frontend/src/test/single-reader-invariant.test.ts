import { describe, it, expect } from 'vitest'
import { ensureSingleReader } from '../App'

// 回归：两个会话同时流式输出时文字错乱/丢失。
//
// 根因（用户实测确认后端跨会话隔离正常，问题在前端）：
// App.tsx 的 assistantMsgIdRef / pipelineMsgRef / streamingSessionIdRef / abortRef
// 是页面级单例，不属于任何会话。所有 SSE reader（startAnalysis / resumeStream / quickChat）
// 读写同一组 ref，隐性前提是「页面内同一时刻只有一条 reader」。
//
// 但三个入口都直接 `abortRef.current = newController` 覆盖旧值，而不先 abort 它：
//   - resumeStream (line ~1644)
//   - quickChat (line ~2100)
//   - startAnalysis (line ~831)
// 一旦旧 reader 仍活跃（abort 是异步的，await reader.read() 不会立即返回），
// 其 controller 引用丢失 → 无人能再 abort 它 → 旧 reader 继续运行并写
// 全局 assistantMsgIdRef 指向的同一条消息 → 两条流的 token 交叉写入 → 必然串字。
//
// 修复：ensureSingleReader 在赋值前 abort 现存 controller，硬保障 single-reader 不变量。

describe('ensureSingleReader（全局 single-reader 不变量）', () => {

  it('存在活跃的旧 controller 时应 abort 它', () => {
    const oldAbort = new AbortController()
    const newAbort = new AbortController()

    expect(oldAbort.signal.aborted).toBe(false)
    ensureSingleReader(oldAbort, newAbort)

    expect(oldAbort.signal.aborted).toBe(true)   // 旧 reader 被中断
    expect(newAbort.signal.aborted).toBe(false)  // 新 reader 保持活跃
  })

  it('返回新 controller 供调用方赋值', () => {
    const newAbort = new AbortController()
    expect(ensureSingleReader(null, newAbort)).toBe(newAbort)
  })

  it('旧 controller 为 null（首次启动）时不报错', () => {
    const newAbort = new AbortController()
    expect(() => ensureSingleReader(null, newAbort)).not.toThrow()
    expect(newAbort.signal.aborted).toBe(false)
  })

  it('旧 controller 已 abort 时不重复 abort', () => {
    const oldAbort = new AbortController()
    oldAbort.abort()
    let abortCount = 0
    oldAbort.signal.addEventListener('abort', () => { abortCount++ })

    ensureSingleReader(oldAbort, new AbortController())
    expect(abortCount).toBe(0)  // 已 abort，监听器不再触发
  })

  it('关键回归：连续启动多条 reader 时只有最后一条活跃', () => {
    // 模拟两会话同时流式输出：sessionA 的 reader 启动后
    // sessionB 的 reader 启动（如用户切换会话触发 resumeStream）
    const readerA = new AbortController()
    let globalAbortRef: AbortController | null = readerA

    const readerB = new AbortController()
    globalAbortRef = ensureSingleReader(globalAbortRef, readerB)

    const readerC = new AbortController()
    globalAbortRef = ensureSingleReader(globalAbortRef, readerC)

    // A 和 B 都被中断，只有 C 活跃 —— single-reader 不变量成立
    expect(readerA.signal.aborted).toBe(true)
    expect(readerB.signal.aborted).toBe(true)
    expect(readerC.signal.aborted).toBe(false)
    expect(globalAbortRef).toBe(readerC)
  })

  it('对比：旧逻辑（直接覆盖不 abort）会让旧 reader 失控', () => {
    // 文档化 bug：旧代码 `abortRef.current = newController`
    const readerA = new AbortController()
    let globalAbortRef: AbortController | null = readerA

    const readerB = new AbortController()
    globalAbortRef = readerB   // 旧逻辑：直接覆盖

    // readerA 仍活跃，且引用已丢失 —— 无人能再 abort 它
    // 它会继续读 SSE 并写全局 assistantMsgIdRef → 与 readerB 串字
    expect(readerA.signal.aborted).toBe(false)  // bug：旧 reader 失控
    expect(globalAbortRef).toBe(readerB)

    // 新逻辑下 readerA 会被正确中断
    const readerA2 = new AbortController()
    ensureSingleReader(readerA2, new AbortController())
    expect(readerA2.signal.aborted).toBe(true)
  })

  it('被 abort 的 reader 其 fetch signal 可被下游感知（验证中断可传播）', () => {
    const oldAbort = new AbortController()
    let notified = false
    oldAbort.signal.addEventListener('abort', () => { notified = true })

    ensureSingleReader(oldAbort, new AbortController())

    // reader 循环中的 `if (abortCtrl.signal.aborted) break` 能感知到中断
    expect(notified).toBe(true)
    expect(oldAbort.signal.aborted).toBe(true)
  })
})
