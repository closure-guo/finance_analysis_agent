import { test, expect } from '@playwright/test'

/**
 * E2E: 两会话并发流式输出 + 同标签切换，断言文本完整性
 *
 * 复现 bug：两会话同时运行 + 切换时，流式文字概率性缺失/串字。
 * 后端 TESTING=1 走 StubLLMClient（固定文本，零 token 消耗），
 * 前端真实 Vite dev server，SSE 全链路真实——满足 E2E 禁 mock 红线。
 *
 * 核心技术债改造（2026-09-04）：原 spec 含 5 处 waitForTimeout（引导/切换
 * 固定等待），CI 上时序漂移导致不稳定、被移出门禁。现全部改为 web-first 断言：
 *   - 页面/新建会话就绪：等主输入框可见（真实交互面，非计时）
 *   - 新建会话后发送：以「输入值落定 → 发送键可点击」为闸门，值被视图
 *     remount 清空则重填再发（sendMessage，上限 5 次，无固定 sleep）
 *   - 会话间快速切换：等主线程（thread-main）渲染出目标会话的用户消息，
 *     才允许点下一个——既保留「切换生效后再点下一个」的竞态约束，又
 *     不再依赖固定 sleep（Playwright 自动重试至超时）。
 *
 * 核心断言（精准，因 stub 文本固定已知）：
 *   会话 A / 会话 B 的最终回答必须完整等于 STUB_ANSWER，
 *   无缺字（缺失）、无交叉混入对方内容（串字）。
 *
 * 关键时序：
 *   1. 会话 A 发起分析，SSE 流开始（stub 每 50ms 吐一个 chunk）
 *   2. 立即点"新建分析"切到会话 B 并发起分析
 *      → 此刻 A 的 reader 被 abort（异步），B 的 reader 启动
 *      → 若 single-reader 不变量失效，A 的残留 reader 会写全局 assistantMsgIdRef
 *   3. 在两个会话间快速来回切换（模拟用户切标签）
 *   4. 等两任务完成，切回各自会话断言最终文本完整性
 */

// 支持隔离配置（playwright.isolated.config.ts 用 8001/5174，避免占用 docker 的 8000/5173）
const API_BASE = process.env.E2E_API_BASE ?? 'http://localhost:8000'
const FRONTEND = process.env.E2E_FRONTEND ?? 'http://localhost:5173'
const LLM_KEY = process.env.LLM_API_KEY || 'stub-key-for-testing'

// 主输入框（quick/deep 占位符不同，但都以「输入」开头；空态与对话态不同时挂载）
const COMPOSER = /输入/

// 会话库含历史遗留数据（同名会话可能存在多条），每个测试用独立唯一 tag
// 使 display_name 全局唯一，避免 find 命中历史/上一轮会话导致断言错位。
// 注意：必须在每个 test 内生成（模块级常量在 --repeat-each 下会被复用）
function makeQueries() {
  const tag = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  return { queryA: `测试问题A-${tag}`, queryB: `测试问题B-${tag}` }
}

// StubLLMClient 固定回答（src/finance_agent/harness/stub_llm_client.py:_STUB_ANSWER_CHUNKS）
// 拼接后为完整字符串；若流式丢字/串字，页面最终文本不会等于它
const STUB_ANSWER = '这是一段测试用的固定回复。用于验证流式渲染的增量累积。'

/**
 * 主线程已切到目标会话（web-first）。
 *
 * 切回 live 会话时无加载遮罩，可观察的「切换生效」信号=主线程渲染出该
 * 会话的用户消息（History 由 ThreadMessages/streamStore 渲染，new run 由
 * QuickThread 渲染，两者都在 thread-main 容器内）。侧边栏同名文本用
 * session-list 作用域隔离，不与 thread-main 混淆。
 */
async function expectThreadShows(page: import('@playwright/test').Page, query: string) {
  await expect(
    page.getByTestId('thread-main').getByText(query, { exact: false }).first(),
  ).toBeVisible({ timeout: 10_000 })
}

/** 主输入框就绪（空态/对话态统一入口：页面引导、新建会话后都等它） */
async function expectComposerReady(page: import('@playwright/test').Page) {
  await expect(page.getByPlaceholder(COMPOSER)).toBeVisible()
}

/**
 * 向当前会话发送一条消息（web-first 重试版）。
 *
 * 新建会话存在真实瞬态：abort 完成/视图 remount 会清空输入值，输入框身份
 * 可能被替换（fill 的值随之丢失 → 发送键保持 disabled）。不用固定 sleep，
 * 以「输入值落定（toHaveValue）→ 发送键可点击」两个可观察状态为闸门重试；
 * 值被清空就重填，直到稳定发出（上限 5 次，超出即报错而非静默成功）。
 */
async function sendMessage(page: import('@playwright/test').Page, query: string) {
  for (let attempt = 1; attempt <= 5; attempt++) {
    const input = page.getByPlaceholder(COMPOSER)
    await expect(input).toBeVisible()
    await input.fill(query)
    try {
      await expect(input).toHaveValue(query, { timeout: 3_000 })
      await page.getByTestId('send-button').click({ timeout: 5_000 })
      return
    } catch (err) {
      console.log(`[E2E] 输入被清空/发送键不可用（第 ${attempt}/5 次重试）：${(err as Error).message?.slice(0, 120)}`)
    }
  }
  throw new Error(`发送失败：输入框无法稳定持有消息「${query}」`)
}

/**
 * 快速来回切换 N 次：模拟用户在同标签内切换会话。
 *
 * web-first 化：每次点击后先断言 thread-main 已渲染目标会话的用户消息
 * （=切换已生效）才点下一个。没有固定 sleep → CI 时序漂移免疫；同时守住
 * 原 300ms 的语义：点击队列里不允许叠加「未生效的切换」，否则测的是浏览器
 * 事件队列而不是 abort/resume 竞态。
 */
async function rapidSwitch(
  page: import('@playwright/test').Page,
  sessions: Array<{ display_name: string; query: string }>,
  times: number,
) {
  const list = page.getByTestId('session-list')
  for (let i = 0; i < times; i++) {
    const target = sessions[i % 2]
    const item = list.getByText(target.display_name, { exact: false }).first()
    await expect(item).toBeVisible()
    await item.click()
    await expectThreadShows(page, target.query)
  }
}

test.describe('并发流式输出完整性', () => {
  test.beforeEach(async ({ page }) => {
    page.on('console', msg => {
      if (msg.type() === 'error') console.log('[BROWSER ERROR]', msg.text())
    })
    page.on('pageerror', err => console.log('[PAGE ERROR]', err.message))

    await page.goto(FRONTEND)
    await page.evaluate((key) => {
      localStorage.setItem('fa_api_key', key)
      localStorage.setItem('fa_user_id', 'e2e-concurrent-stream')
    }, LLM_KEY)
    await page.reload()
    await expectComposerReady(page)
  })

  test('两会话并发流式输出 + 快速切换，文本完整无缺字无串字', async ({ page }) => {
    test.setTimeout(180_000)
    const { queryA: QUERY_A, queryB: QUERY_B } = makeQueries()

    // ── 会话 A：发起第一条消息 ──
    await sendMessage(page, QUERY_A)

    // 等会话 A 流式输出开始（stub 思考文本先出现）
    await expect(page.getByText(/分析思路|测试问题/i).first()).toBeVisible({ timeout: 30_000 })
    console.log('[E2E] 会话 A 流式输出已开始')

    // ── 立即新建会话 B（此刻 A 的 reader 被 abort，B 的 reader 启动）──
    await page.getByRole('button', { name: /新建分析/ }).click()
    await expectComposerReady(page)

    await sendMessage(page, QUERY_B)
    await expect(page.getByText(/分析思路|测试问题/i).first()).toBeVisible({ timeout: 30_000 })
    console.log('[E2E] 会话 B 流式输出已开始，两流并发中')

    // ── 读取会话列表获取两个 display_name ──
    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
      display_name: string
      status?: string
    }>
    // 会话库含历史遗留数据（列表按时间倒序），按 display_name 精确取本次创建的两个
    console.log(`[E2E][诊断] 会话总数: ${sessions.length}`)
    const sB = sessions.find(s => s.display_name === QUERY_B)
    const sA = sessions.find(s => s.display_name === QUERY_A)
    if (!sA || !sB) throw new Error(`未找到本次会话: A=${!!sA} B=${!!sB}`)
    console.log(`[E2E] 会话 A: ${sA.session_id} (${sA.display_name})`)
    console.log(`[E2E] 会话 B: ${sB.session_id} (${sB.display_name})`)

    // ── 快速来回切换（模拟用户切标签，触发 reader abort/恢复竞态）──
    console.log('[E2E] 开始快速切换...')
    await rapidSwitch(page, [
      { display_name: sA.display_name, query: QUERY_A },
      { display_name: sB.display_name, query: QUERY_B },
    ], 6)

    // ── 等两个任务都完成（status=completed/clarifying）──
    console.log('[E2E] 等待两任务完成...')
    await expect.poll(async () => {
      const [rA, rB] = await Promise.all([
        page.request.get(`${API_BASE}/api/sessions/${sA.session_id}`),
        page.request.get(`${API_BASE}/api/sessions/${sB.session_id}`),
      ])
      const [dA, dB] = await Promise.all([rA.json(), rB.json()])
      return { a: dA.status, b: dB.status }
    }, { timeout: 60_000, intervals: [1000] }).toMatchObject({
      a: expect.stringMatching(/completed|clarifying/),
      b: expect.stringMatching(/completed|clarifying/),
    })

    // ── 切回会话 A，断言最终文本完整 ──
    // 轮询而非固定等待：切回触发 chat_history 重建 + resumeStream，渲染耗时不确定
    await page.getByTestId('session-list').getByText(sA.display_name, { exact: false }).first().click()
    await expect.poll(
      async () => (await page.locator('body').textContent())?.includes(STUB_ANSWER) ?? false,
      { timeout: 15_000, intervals: [500], message: '会话 A 流式文本应完整（无缺字/串字）' },
    ).toBe(true)
    console.log('[E2E] 会话 A 文本完整')

    // ── 切回会话 B，断言最终文本完整 ──
    await page.getByTestId('session-list').getByText(sB.display_name, { exact: false }).first().click()
    await expect.poll(
      async () => (await page.locator('body').textContent())?.includes(STUB_ANSWER) ?? false,
      { timeout: 15_000, intervals: [500], message: '会话 B 流式文本应完整（无缺字/串字）' },
    ).toBe(true)
    console.log('[E2E] 会话 B 文本完整')

    console.log('[E2E] ✓ 两会话文本均完整，无缺失无串字')
  })

  test('两会话并发流式输出（不切走），各自文本完整', async ({ page }) => {
    test.setTimeout(120_000)
    const { queryA: QUERY_A, queryB: QUERY_B } = makeQueries()

    // 收集前端 SSE 诊断日志（?sse_debug 开启，sseDebug 用 console.warn 输出）
    const sseLogs: string[] = []
    page.on('console', msg => {
      const t = msg.text()
      if (t.includes('[SSE]')) sseLogs.push(t)
    })

    // 带 ?sse_debug 重新加载，开启前端诊断日志
    await page.goto(`${FRONTEND}/?sse_debug`)
    await expectComposerReady(page)

    // 会话 A 发起
    await sendMessage(page, QUERY_A)
    await expect(page.getByText(/分析思路|测试问题/i).first()).toBeVisible({ timeout: 30_000 })

    // 立即新建会话 B 发起（不切回 A）
    await page.getByRole('button', { name: /新建分析/ }).click()
    await expectComposerReady(page)
    await sendMessage(page, QUERY_B)
    await expect(page.getByText(/分析思路|测试问题/i).first()).toBeVisible({ timeout: 30_000 })

    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
      display_name: string
      status?: string
    }>
    // 会话库含历史遗留数据（列表按时间倒序），必须按 display_name 精确取本次创建的两个，
    // 不能用 sessions[0]/[1]——顺序不保证且会命中历史会话。
    const sB = sessions.find(s => s.display_name === QUERY_B)
    const sA = sessions.find(s => s.display_name === QUERY_A)
    if (!sA || !sB) throw new Error(`未找到本次会话: A=${!!sA} B=${!!sB}`)
    console.log(`[E2E][诊断] A=${sA.session_id}(${sA.status}) B=${sB.session_id}(${sB.status})`)
    expect(sA.session_id, '会话 A 与 B 应为不同 session').not.toBe(sB.session_id)
    // 等待 B 完成（当前视图）
    await expect.poll(async () => {
      const r = await page.request.get(`${API_BASE}/api/sessions/${sB.session_id}`)
      return (await r.json()).status
    }, { timeout: 60_000, intervals: [1000] }).toMatch(/completed|clarifying/)

    // 对比后端 chat_history（真相）与前端渲染：定位丢失发生在前端还是后端
    const detailResp = await page.request.get(`${API_BASE}/api/sessions/${sB.session_id}`)
    const detail = await detailResp.json()
    const assistantMsg = ((detail.chat_history ?? []) as Array<{ role: string; content: string }>)
      .find(h => h.role === 'assistant')
    expect(assistantMsg?.content, '前置校验：后端应已产出完整回答').toContain(STUB_ANSWER)

    const bodyB = await page.locator('body').textContent()
    const idx = bodyB?.indexOf('这是') ?? -1
    if (idx >= 0) console.log(`[E2E] 前端渲染片段: "${bodyB?.slice(idx, idx + 40)}"`)

    // 失败时打印 SSE 决策轨迹，便于定位 token 在哪个环节被丢
    if (!bodyB?.includes(STUB_ANSWER)) {
      console.log(`[E2E][SSE轨迹] 共 ${sseLogs.length} 条`)
      for (const log of sseLogs) console.log(`[E2E][SSE轨迹] ${log}`)
    }

    expect(bodyB, '当前视图（B）流式文本应完整').toContain(STUB_ANSWER)
    console.log('[E2E] ✓ 会话 B（当前视图）文本完整')
  })
})
