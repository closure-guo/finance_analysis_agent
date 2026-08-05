import { test, expect } from '@playwright/test'

/**
 * ReAct 路径后台化：会话切换不中断管线（harden-react-path-resilience delta task 8.1/8.2）
 *
 * 验证目标：
 * 1. 分析过程中切换会话 -> 管线在后台继续执行 -> 快照 progress 持续增长
 * 2. 管线最终完成（status=completed）
 * 3. 切回原会话 -> 报告正确展示
 *
 * 与 resume-pipeline-across-sessions.spec.ts 的区别：
 *   - 旧测试验证「切走后快照停在断开点」（progressAfter >= progressBefore）
 *   - 新测试验证「切走后管线后台继续推进」（progressAfter > progressBefore -> 最终 completed）
 *
 * 确定性方案（TESTING=1 + STUB_SCENARIO=pipeline，后端 8002 / 前端 5175）：
 *   - STUB_NODE_DELAY=1.5 时全程 ~30s，切走后后台管线继续推进
 *   - 全程通过前端 UI 真实操作
 */

test.setTimeout(180_000)

const API_BASE = 'http://localhost:8002'
const FRONTEND_BASE = 'http://localhost:5175'

async function clickSession(page: import('@playwright/test').Page, name: string) {
  await page.getByText(name, { exact: true }).first().click()
}

async function readSnapshotProgress(
  page: import('@playwright/test').Page,
  sessionId: string,
): Promise<number> {
  const resp = await page.request.get(`${API_BASE}/api/sessions/${sessionId}`)
  expect(resp.ok()).toBeTruthy()
  const body = await resp.json()
  if (!body.pipeline_snapshot) return -1
  return JSON.parse(body.pipeline_snapshot).progress as number
}

async function getSessionStatus(
  page: import('@playwright/test').Page,
  sessionId: string,
): Promise<string> {
  const resp = await page.request.get(`${API_BASE}/api/sessions/${sessionId}`)
  expect(resp.ok()).toBeTruthy()
  const body = await resp.json()
  return body.status as string
}

test.describe('ReAct 路径后台化（harden-react-path-resilience）', () => {
  const TARGET_SESSION = '贵州茅台(600519)'

  test.beforeEach(async ({ page }) => {
    // 造占位会话作为切走目标
    const seedResp = await page.request.post(`${API_BASE}/api/test/seed`, {
      data: {
        display_name: 'E2E占位会话-resilience',
        session_type: 'chat',
        chat_history: [{ role: 'user', content: '占位会话' }],
      },
    })
    expect(seedResp.ok()).toBeTruthy()

    await page.goto(FRONTEND_BASE)
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-resilience')
      localStorage.removeItem('financeAgent.pipelineDurations')
    })
    await page.reload()

    // 切到深度模式并发起管线分析
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()
  })

  test('8.1 切换会话后管线后台继续执行并最终完成', async ({ page }) => {
    const timeline = page.getByTestId('pipeline-timeline')

    // 等管线进入运行态
    await expect(timeline).toBeVisible({ timeout: 60_000 })

    // 定位当前会话
    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
      display_name: string
    }>
    const target = sessions.find(
      (s) => s.display_name === TARGET_SESSION || s.display_name === '深度分析600519',
    )
    expect(target).toBeTruthy()

    // 等管线确认运行态：快照 progress > 0
    await expect(async () => {
      const p = await readSnapshotProgress(page, target!.session_id)
      expect(p).toBeGreaterThan(0)
    }).toPass({ timeout: 60_000, intervals: [500, 1_000, 2_000] })

    const progressBefore = await readSnapshotProgress(page, target!.session_id)

    // 切走到占位会话（触发 abortStreaming）
    await clickSession(page, 'E2E占位会话-resilience')
    await expect(timeline).not.toBeVisible()

    // 核心断言：切走后管线后台继续推进，progress 持续增长
    // 等待至少 3 秒后检查 progress 是否增长
    await page.waitForTimeout(3_000)
    const progressAfter = await readSnapshotProgress(page, target!.session_id)
    expect(progressAfter).toBeGreaterThan(progressBefore)

    // 等管线最终完成（后台 Task 独立于 SSE 生命周期）
    await expect(async () => {
      const status = await getSessionStatus(page, target!.session_id)
      expect(status).toBe('completed')
    }).toPass({ timeout: 120_000, intervals: [2_000, 5_000] })
  })

  test('8.2 切换会话后等待完成，切回验证报告展示', async ({ page }) => {
    const timeline = page.getByTestId('pipeline-timeline')

    // 等管线进入运行态
    await expect(timeline).toBeVisible({ timeout: 60_000 })

    // 定位当前会话
    const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions = (await sessionsResp.json()).sessions as Array<{
      session_id: string
      display_name: string
    }>
    const target = sessions.find(
      (s) => s.display_name === TARGET_SESSION || s.display_name === '深度分析600519',
    )
    expect(target).toBeTruthy()

    // 等管线确认运行态
    await expect(async () => {
      const p = await readSnapshotProgress(page, target!.session_id)
      expect(p).toBeGreaterThan(0)
    }).toPass({ timeout: 60_000, intervals: [500, 1_000, 2_000] })

    // 切走到占位会话
    await clickSession(page, 'E2E占位会话-resilience')
    await expect(timeline).not.toBeVisible()

    // 等后台管线完成
    await expect(async () => {
      const status = await getSessionStatus(page, target!.session_id)
      expect(status).toBe('completed')
    }).toPass({ timeout: 120_000, intervals: [2_000, 5_000] })

    // 切回原会话：用 session_id 查 API 取实时 display_name
    const sessionsResp2 = await page.request.get(`${API_BASE}/api/sessions`)
    const sessions2 = (await sessionsResp2.json()).sessions as Array<{
      session_id: string
      display_name: string
    }>
    const targetNow = sessions2.find((s) => s.session_id === target!.session_id)
    expect(targetNow).toBeTruthy()
    await clickSession(page, targetNow!.display_name)

    // 报告恢复可见
    await expect(page.getByText('深度分析报告').first()).toBeVisible({ timeout: 30_000 })
  })
})

// 8.3 LLM 失败场景（后端 8003 / 前端 5176，STUB_SCENARIO=llm_failure）
const API_BASE_FAIL = 'http://localhost:8003'
const FRONTEND_BASE_FAIL = 'http://localhost:5176'

test.describe('LLM 失败场景（harden-react-path-resilience 8.3）', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(FRONTEND_BASE_FAIL)
    await page.evaluate(() => {
      localStorage.setItem('fa_api_key', 'stub-key-for-testing')
      localStorage.setItem('fa_user_id', 'user-test-fail')
      localStorage.removeItem('financeAgent.pipelineDurations')
    })
    await page.reload()

    // 切到深度模式并发送消息
    await page.getByRole('button', { name: /模式/ }).click()
    await page.getByRole('button', { name: /深度研究.*5 层 Agent 流水线/ }).click()
    await page.getByPlaceholder(/输入/).fill('深度分析600519')
    await page.getByTestId('send-button').click()
  })

  test('8.3 LLM 失败时前端展示错误信息', async ({ page }) => {
    // LLM 失败后，Agent 主循环 yield ERROR 事件 -> api.py 发送 error SSE
    // 前端应展示错误消息（而非无限等待）
    await expect(page.getByText(/错误|失败|出错/i).first()).toBeVisible({ timeout: 30_000 })
  })
})
