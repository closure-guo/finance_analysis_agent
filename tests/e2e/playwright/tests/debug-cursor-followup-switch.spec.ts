import { test, expect } from '@playwright/test'

/**
 * Bug 复现（调试中）：快速模式第二轮输出中途切走再切回，
 * 输出完毕后末尾加载游标不消失，再切换会话才消失。
 *
 * 通道迁移说明（2026-09-01）：quick 模式自 add-assistant-ui-thread（#93）
 * 起走 AG-UI 通道（assistant-ui Thread）。该通道的会话切换语义为
 * 「切走重挂载 Thread 清空本 mount 新 run 消息，切回走 rebuildSession 快照」
 * （调研 §3.3 路径 a）——切回时不续传进行中的 run，游标（agui-stream-status）
 * 由本 mount 的 agent 运行态驱动，天然不会常驻。本 spec 作为回归守卫保留：
 *   - 切回后历史快照正常渲染（stream-output）
 *   - 游标不常驻（agui-stream-status 保持隐藏）
 *   - 后端会话状态不腐化（终态 completed）
 *
 * 已实测的通道语义（2026-09-01）：quick run 在切走时被中止，第二轮不落库
 * （会话仅保留第一轮 user/assistant）。与深度模式（journal 续传）不同，
 * 这是 AG-UI 通道的既有设计取舍，本 spec 不断言第二轮落库。
 *
 * 链路：会话 A 第一轮 → 新建分析 → 会话 B 第一轮 → 切回 A →
 *       A 第二轮发送 → 流式中途点 B → 立即点回 A →
 *       游标不常驻 + 快照渲染 + 后端终态 completed
 */

const API_BASE = 'http://localhost:8000'

test('第二轮中途切换会话后游标也应消失', async ({ page }) => {
  // 三轮 quick run + 两次会话切换 + abort 落停轮询，全量套件并发负载下放宽单测总时长
  test.setTimeout(90_000)
  await page.goto('/')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-test-123')
  })
  await page.reload()

  // 会话 A 第一轮
  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /快速模式/ }).click()
  await page.getByPlaceholder(/输入问题/).fill('第一轮问题A')
  await page.getByTestId('send-button').click()
  await expect(page.getByTestId('agui-assistant-message')).toContainText('增量累积', { timeout: 20_000 })
  await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 20_000 })

  // 新建分析 -> 会话 B 第一轮
  await page.getByRole('button', { name: /新建分析/ }).click()
  await page.getByPlaceholder(/输入问题/).fill('第一轮问题B')
  await page.getByTestId('send-button').click()
  await expect(page.getByTestId('agui-assistant-message')).toContainText('增量累积', { timeout: 20_000 })
  await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 20_000 })

  // 切回会话 A（completed，rebuildSession 快照渲染历史）
  await page.getByText('第一轮问题A').first().click()
  await expect(page.getByTestId('stream-output').first()).toBeVisible({ timeout: 30_000 })

  // 会话 A 第二轮
  await page.getByPlaceholder(/输入问题/).fill('第二轮问题A')
  await page.getByTestId('send-button').click()
  await expect(page.getByTestId('agui-stream-status')).toBeVisible({ timeout: 10_000 })

  // 流式中途切到 B（触发 selectSession 守卫：abort A 的 quick run）
  await page.getByText('第一轮问题B').first().click()

  // 等 A 的中止在后端落停再切回：abort 传播期间 A 仍为 running，此时切回会走
  // resume 续传而非 rebuildSession 快照，快照断言会产生环境性抖动（CI 实测）
  const sessionsList = await page.request.get(`${API_BASE}/api/sessions`)
  const { sessions: sessionsNow } = (await sessionsList.json()) as {
    sessions: Array<{ session_id: string; display_name?: string }>
  }
  const sessionAId = sessionsNow.find(s => (s.display_name ?? '').includes('第一轮问题A'))?.session_id
  if (sessionAId) {
    for (let i = 0; i < 15; i++) {
      const resp = await page.request.get(`${API_BASE}/api/sessions/${sessionAId}`)
      const d = (await resp.json()) as { status: string }
      if (d.status !== 'running' && d.status !== 'clarifying') break
      await page.waitForTimeout(1_000)
    }
  }

  // 切回 A（重挂载 Thread → rebuildSession 快照）
  await page.getByText('第一轮问题A').first().click()

  // 切回后快照渲染正常
  await expect(page.getByTestId('stream-output').first()).toBeVisible({ timeout: 30_000 })

  // 游标不常驻：重挂载的 Thread 无进行中 run，指示器应保持隐藏
  // （修复前旧通道：resumeStream 路径下游标常驻）
  await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 20_000 })

  // 后端会话状态不腐化：会话 A 保持终态 completed（quick run 切走即中止，
  // 第二轮不落库——AG-UI 通道既有语义，见文件头说明）
  const sessionsResp = await page.request.get(`${API_BASE}/api/sessions`)
  const { sessions } = (await sessionsResp.json()) as {
    sessions: Array<{ session_id: string; display_name?: string }>
  }
  const sessionA = sessions.find(s => (s.display_name ?? '').includes('第一轮问题A'))
  expect(sessionA, '会话 A 应在会话列表中').toBeTruthy()
  if (!sessionA) return
  const detailResp = await page.request.get(`${API_BASE}/api/sessions/${sessionA.session_id}`)
  const detail = (await detailResp.json()) as {
    status: string
    chat_history: Array<{ role: string; content: string }>
  }
  expect(detail.status).toBe('completed')
})
