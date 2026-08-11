import { test, expect } from '@playwright/test'

/**
 * 复现：刷新页面后两会话并发流式输出 + 快速切换，文本/思考是否错乱
 *
 * 对应用户报告：「刷新页面会导致页面内容不同程度的出现错位，位置随机不固定」。
 * 与 concurrent-streaming-integrity.spec.ts 的差异：
 *   1. 在两会话都启动后、还在流式时执行 page.reload()，触发完整刷新恢复路径
 *      （localStorage 恢复当前会话 → selectSession → chat_history 重建 + resumeStream）
 *   2. 刷新后立即在两会话间快速切换，制造 selectSession 交错执行
 *   3. 对 stub 固定文本做字符级断言：思考（thinking）与回答（answer）都必须完整，
 *      且无对方会话的 query 字符串混入（串字检查）
 *
 * 后端 TESTING=1 走 StubLLMClient（固定文本），前端真实 Vite dev server，SSE 全链路真实。
 */

const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8001'
const FRONTEND = process.env.E2E_FRONTEND ?? 'http://localhost:5174'
const LLM_KEY = process.env.LLM_API_KEY || 'stub-key-for-testing'

// StubLLMClient 固定输出（src/finance_agent/harness/stub_llm_client.py）
const STUB_REASONING = '## 分析思路\n用户询问了一个测试问题，我需要给出简短回答。'
const STUB_ANSWER = '这是一段测试用的固定回复。用于验证流式渲染的增量累积。'

function makeQueries() {
  const tag = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return { queryA: `复现问题A-${tag}`, queryB: `复现问题B-${tag}` }
}

/** 快速来回切换 N 次，模拟用户刷新后切标签 */
async function rapidSwitch(page: import('@playwright/test').Page, names: [string, string], times: number) {
  for (let i = 0; i < times; i++) {
    const target = names[i % 2]
    const item = page.getByText(target, { exact: false }).first()
    if (await item.isVisible({ timeout: 2000 }).catch(() => false)) {
      await item.click()
      await page.waitForTimeout(250)
    }
  }
}

test.describe('刷新后并发流式错乱复现', () => {
  test.beforeEach(async ({ page }) => {
    page.on('pageerror', err => console.log('[PAGE ERROR]', err.message))
    await page.goto(FRONTEND)
    await page.evaluate((key) => {
      localStorage.setItem('fa_api_key', key)
      localStorage.setItem('fa_user_id', 'e2e-refresh-misalign')
    }, LLM_KEY)
    await page.reload()
    await page.waitForTimeout(500)
  })

  test('两会话并发 + 流式中途刷新 + 快速切换，文本与思考完整无串字', async ({ page }) => {
    test.setTimeout(240_000)
    const { queryA: QUERY_A, queryB: QUERY_B } = makeQueries()

    // ── 会话 A 发起 ──
    await page.getByPlaceholder(/输入/).fill(QUERY_A)
    await page.getByTestId('send-button').click()
    await expect(page.getByText(/分析思路|复现问题/i).first()).toBeVisible({ timeout: 30_000 })
    console.log('[复现] 会话 A 流式开始')

    // ── 立即新建会话 B（两流并发）──
    await page.getByRole('button', { name: /新建分析/ }).click()
    await page.waitForTimeout(200)
    await page.getByPlaceholder(/输入/).fill(QUERY_B)
    await page.getByTestId('send-button').click()
    await expect(page.getByText(/分析思路|复现问题/i).first()).toBeVisible({ timeout: 30_000 })
    console.log('[复现] 会话 B 流式开始，两流并发中')

    // 拿两个 session_id
    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
      display_name: string
      status?: string
    }>
    const sA = sessions.find(s => s.display_name === QUERY_A)
    const sB = sessions.find(s => s.display_name === QUERY_B)
    if (!sA || !sB) throw new Error(`未找到会话: A=${!!sA} B=${!!sB}`)
    console.log(`[复现] A=${sA.session_id} B=${sB.session_id}`)

    // ── 关键步骤：在两流都还在跑时刷新页面 ──
    // 刷新后：localStorage 恢复会话 B（当前视图），chat_history 重建 + resumeStream 续传
    console.log('[复现] 两流运行中刷新页面...')
    await page.reload()
    await page.waitForTimeout(800)

    // ── 刷新后立即快速切换，制造 selectSession 交错 ──
    console.log('[复现] 刷新后快速切换...')
    await rapidSwitch(page, [sA.display_name, sB.display_name], 8)

    // ── 等两任务完成（限时 60s，超时则落出状态诊断卡死形态）──
    console.log('[复现] 等待两任务完成...')
    let aStatus = 'unknown'
    let bStatus = 'unknown'
    const deadline = Date.now() + 60_000
    while (Date.now() < deadline) {
      const [rA, rB] = await Promise.all([
        page.request.get(`${API_BASE}/api/sessions/${sA.session_id}`),
        page.request.get(`${API_BASE}/api/sessions/${sB.session_id}`),
      ])
      const [dA, dB] = await Promise.all([rA.json(), rB.json()])
      aStatus = dA.status
      bStatus = dB.status
      if (/completed|clarifying/.test(aStatus) && /completed|clarifying/.test(bStatus)) break
      await page.waitForTimeout(1000)
    }
    console.log(`[复现] 终态: A=${aStatus} B=${bStatus}`)
    // 卡死诊断：落出两边 chat_history 长度与最后一条内容片段
    const dAFull = await (await page.request.get(`${API_BASE}/api/sessions/${sA.session_id}`)).json()
    const dBFull = await (await page.request.get(`${API_BASE}/api/sessions/${sB.session_id}`)).json()
    const lastA = (dAFull.chat_history ?? []).slice(-1)[0]
    const lastB = (dBFull.chat_history ?? []).slice(-1)[0]
    console.log(`[复现] A chat_history=${(dAFull.chat_history ?? []).length} 末条=${JSON.stringify(lastA)?.slice(0, 120)}`)
    console.log(`[复现] B chat_history=${(dBFull.chat_history ?? []).length} 末条=${JSON.stringify(lastB)?.slice(0, 120)}`)

    // ── 切回 A：断言思考 + 回答完整，且无 B 的 query 混入 ──
    // 断言范围收窄到消息区（main），排除侧边栏会话标题对"串字"判断的干扰
    await page.getByText(sA.display_name, { exact: false }).first().click()
    await page.waitForTimeout(1000)
    const mainA = page.locator('main').first()
    const bodyA = (await mainA.textContent().catch(() => null)) ?? (await page.locator('body').textContent()) ?? ''
    const okReasonA = bodyA.includes('分析思路')
    const okAnswerA = bodyA.includes(STUB_ANSWER)
    const noCrossA = !bodyA.includes(QUERY_B)
    console.log(`[复现] A: thinking=${okReasonA} answer=${okAnswerA} noCross=${noCrossA}`)
    // 探测缺失形态：打印消息区中"这是"开头片段与完整 stub 的 diff 前缀
    const idxA = bodyA.indexOf('这是')
    console.log(`[复现] A 消息区片段: "${idxA >= 0 ? bodyA.slice(idxA, idxA + 80) : '(无回答开头)'}"`)

    // ── 切回 B：同样断言 ──
    await page.getByText(sB.display_name, { exact: false }).first().click()
    await page.waitForTimeout(1000)
    const mainB = page.locator('main').first()
    const bodyB = (await mainB.textContent().catch(() => null)) ?? (await page.locator('body').textContent()) ?? ''
    const okReasonB = bodyB.includes('分析思路')
    const okAnswerB = bodyB.includes(STUB_ANSWER)
    const noCrossB = !bodyB.includes(QUERY_A)
    console.log(`[复现] B: thinking=${okReasonB} answer=${okAnswerB} noCross=${noCrossB}`)
    const idxB = bodyB.indexOf('这是')
    console.log(`[复现] B 消息区片段: "${idxB >= 0 ? bodyB.slice(idxB, idxB + 80) : '(无回答开头)'}"`)

    // 断言：两边都完整才算通过；任一缺失/串字即复现成功
    expect(okReasonA && okAnswerA && noCrossA, '会话 A 刷新后文本应完整且无串字').toBe(true)
    expect(okReasonB && okAnswerB && noCrossB, '会话 B 刷新后文本应完整且无串字').toBe(true)
    console.log('[复现] ✓ 两会话刷新后文本均完整，未复现错乱')
  })
})
