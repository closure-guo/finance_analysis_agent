import { test, expect } from '@playwright/test'

/**
 * AG-UI quick 通道「带工具调用 run」E2E（fix/agui-quick-toolcall-lifecycle 回归）。
 *
 * 背景（线上两症状）：translator 的 TOOL_CALL 段此前缺 TOOL_CALL_END，
 * 客户端 HttpAgent 校验 RUN_FINISHED 时抛 AGUIError（tool calls still active）
 * → 整个 run 判错、思考/工具/回答内容实时丢弃（刷新后走 MessageItem 快照才恢复）；
 * 同时 QuickThread.send 的 parentId=null 使追问挂成兄弟分支，多步交互序列错乱。
 *
 * 链路（真实链路，不 mock 业务接口——E2E 红线）：
 *   发送 → POST /api/agui/quick（TESTING=1 + STUB_SCENARIO=tool_call 后端 8001）
 *   → harness Agent（思考1 → web_search stub 工具 → 思考2 → 回答）
 *   → 真实 translator 翻译 AG-UI 事件流（TOOL_CALL_END 修复在此被端到端覆盖）
 *   → assistant-ui Thread 渲染。
 *
 * stub 确定性输出（tool_call 场景）：
 *   思考1 = "用户想知道茅台最新消息，我需要先搜索一下实时信息。"
 *   工具  = web_search（stub 固定结果）
 *   思考2 = "搜索结果显示茅台近期有提价动作，我整理一下关键信息给用户。"
 *   回答  = "这是一段测试用的固定回复。…增量累积。"
 */

/** 配置测试 Key → 切快速模式 → 发送一条消息（走 AG-UI 通道） */
async function openAndSendQuickMessage(page: import('@playwright/test').Page, message: string) {
  await page.goto('/')
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-agui-toolcall-e2e')
  })
  await page.reload()

  await page.getByRole('button', { name: /模式/ }).click()
  await page.getByRole('button', { name: /快速模式/ }).click()

  await page.getByPlaceholder(/输入问题/).fill(message)
  await page.getByTestId('send-button').click()
}

test.describe('AG-UI quick 通道带工具调用 run', () => {
  // 全量门禁 8 并发 worker 下 vite/后端争用，page.reload 等 load 可超默认 30s
  // （环境性失败族，归因同 tests/validation/2026-08-29-* §E2E）——给足余量。
  test.setTimeout(90_000)

  test('工具调用 run 实时完整呈现（思考/工具横幅 + 回答累积 + RUN_FINISHED 不判错）', async ({
    page,
  }) => {
    const message = 'AGUI工具调用测试'
    await openAndSendQuickMessage(page, message)

    const thread = page.getByTestId('agui-thread')
    await expect(thread).toBeAttached({ timeout: 10_000 })
    await expect(page.getByTestId('agui-user-message')).toContainText(message, { timeout: 10_000 })

    const assistantMessage = page.getByTestId('agui-assistant-message')

    // 思考1（REASONING_MESSAGE_* → Reasoning part）
    await expect(assistantMessage).toContainText('需要先搜索', { timeout: 20_000 })

    // 工具调用横幅（TOOL_CALL_* → tool-call part）；修复前 run 在此判错、内容丢弃
    await expect(assistantMessage).toContainText('调用工具 · web_search', { timeout: 20_000 })

    // 思考2（工具结果后的再思考，时间序列第二段 reasoning）
    await expect(assistantMessage).toContainText('提价动作', { timeout: 20_000 })

    // 回答完整累积（stub 末 chunk）
    await expect(assistantMessage).toContainText('增量累积', { timeout: 20_000 })

    // RUN_FINISHED 终止态：指示器消失（修复前 AGUIError 使 run 异常终止）
    await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 15_000 })
  })

  test('追问按轮分列：第二轮不串入第一轮消息，请求携带历史上下文', async ({ page }) => {
    await openAndSendQuickMessage(page, 'AGUI多轮第一问')

    const assistantMessage = page.getByTestId('agui-assistant-message')
    await expect(assistantMessage).toContainText('增量累积', { timeout: 20_000 })
    await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 15_000 })

    // 追问（同 mount，sessionId 已由 RUN_STARTED.thread_id 回传绑定）
    await page.getByPlaceholder(/输入问题/).fill('AGUI多轮第二问')
    await page.getByTestId('send-button').click()

    // 第二轮回答出现在视图上（修复前 parentId=null 使第一轮脱离视图）
    await expect(page.getByTestId('agui-user-message').filter({ hasText: '第二问' })).toBeVisible({
      timeout: 10_000,
    })

    // 两轮各自独立：恰好 2 条 assistant 消息，两条 user 气泡均在视图中
    const assistantMsgs = page.getByTestId('agui-assistant-message')
    await expect(assistantMsgs).toHaveCount(2, { timeout: 20_000 })
    await expect(assistantMsgs.nth(0)).toContainText('增量累积')
    await expect(assistantMsgs.nth(1)).toBeAttached()
    await expect(page.getByTestId('agui-user-message').filter({ hasText: '第一问' })).toBeVisible()

    // 后端落库核验（经 API 只读校验）：第二轮请求必须携带第一问历史——
    // 会话 chat_history 应同时包含两问与两答
    const sessionsResp = await page.request.get('http://localhost:8001/api/sessions')
    expect(sessionsResp.ok()).toBeTruthy()
    const { sessions } = (await sessionsResp.json()) as {
      sessions: Array<{ session_id: string; display_name?: string }>
    }
    const target = sessions.find(s => (s.display_name ?? '').includes('AGUI多轮第一问'))
    expect(target, '多轮会话应出现在会话列表').toBeTruthy()
    if (!target) return
    const detailResp = await page.request.get(`http://localhost:8001/api/sessions/${target.session_id}`)
    expect(detailResp.ok()).toBeTruthy()
    const detail = (await detailResp.json()) as {
      status: string
      chat_history: Array<{ role: string; content: string }>
    }
    const userEntries = detail.chat_history.filter(m => m.role === 'user')
    const userTexts = userEntries.map(m => m.content).join('\n')
    expect(userTexts).toContain('AGUI多轮第一问')
    expect(userTexts).toContain('AGUI多轮第二问')
  })

  test('刷新恢复：快照渲染带工具调用的完整时序（MessageItem 路径）', async ({ page }) => {
    await openAndSendQuickMessage(page, 'AGUI工具调用刷新恢复')

    const assistantMessage = page.getByTestId('agui-assistant-message')
    await expect(assistantMessage).toContainText('增量累积', { timeout: 20_000 })
    await expect(page.getByTestId('agui-stream-status')).toBeHidden({ timeout: 15_000 })

    // 刷新 → fa_current_session_id 自动恢复 → rebuildSession 快照渲染历史
    await page.reload()
    const historyEntry = page.getByTestId('stream-output').filter({ hasText: '固定回复' })
    await expect(historyEntry).toBeVisible({ timeout: 20_000 })

    // 历史快照恰好一次，思考段与回答文本完整恢复
    await expect(historyEntry).toHaveCount(1)
    await expect(historyEntry).toContainText('需要先搜索')

    // 注：历史快照不含「调用工具 · web_search」横幅——quick 通道落库无结构化
    // agentTimeline，恢复走 buildTimelineFromHistory fallback，其按 design 决策 7
    // 跳过搜索类工具（搜索横幅需结构化 results，AG-UI 通道仅有 result_text）。
    // 该恢复保真度缺口独立于本次修复，待产品决策（结构化搜索结果落库或
    // fallback 渲染工具横幅）后补断言。

    // Thread 重挂载后为空壳
    await expect(page.getByTestId('agui-user-message')).toHaveCount(0)
    await expect(page.getByTestId('agui-assistant-message')).toHaveCount(0)
  })
})
