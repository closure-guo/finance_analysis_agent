import { test, expect } from '@playwright/test'

/**
 * bug 修复复现：展开态侧边栏内容溢出 256px 被裁剪
 *
 * 症状（用户报告）：侧边栏展开态下，「新建分析」按钮与「搜索股票」输入框
 * 宽度超过侧边栏 256px，右缘被 aside 的 overflow-hidden 裁掉。
 *
 * 根因：会话行 display_name 为 truncate（white-space: nowrap），长会话名的
 * min-content ≈ 全文宽度；展开态 rail 根（flex flex-col h-full）是行向 flex
 * 容器（sidebar.tsx 显隐包裹层 display:flex）的 flex item，min-width:auto 使
 * 其拒绝收缩到内容 min-content（~403px）以下，整个 rail 被撑宽溢出，rail 内
 * 所有 w-full 子元素（按钮/输入框）跟随拉伸后被裁剪。
 *
 * 造数：经 /api/test/seed 写入长 display_name 会话（真实存储写入，非拦截
 * 业务接口——符合「E2E 禁止 mock 被测系统」红线；隔离套件用独立测试库，
 * 测试自清理种子会话）。seed 走相对路径，经 vite 代理到达当前 config 的
 * TESTING=1 后端（默认 config 8000 / isolated config 8001 均可用）。
 *
 * 断言口径：内容盒宽度不得超过 256px 布局约束下各层的内宽（按钮/输入框
 * ≤ 232+1 容差、会话名 ≤ 216+1 容差），以 expect.poll 对 boundingBox 做
 * web-first 重试断言；不做一次性取值断言。
 */
const LONG_NAME = '深度分析贵州茅台当前估值水平与长期持有的价值锚点深度研究复盘'

test('长会话名不撑破展开态侧边栏：按钮/搜索框/会话名均在 256px 内', async ({ page, request }) => {
  // 幂等预清理：测试库跨运行持久化，上次运行若被中断（finally 未执行）或删除
  // 失手，会遗留同名种子会话，把下方 toHaveCount(1) 顶成 2——先按名删除遗留
  const listResp = await request.get('/api/sessions')
  expect(listResp.status(), '会话列表需要 TESTING=1 后端（默认 config 或 isolated config 启动）').toBe(200)
  const { sessions } = (await listResp.json()) as { sessions: { session_id: string; display_name: string }[] }
  for (const s of sessions.filter(s => s.display_name === LONG_NAME)) {
    await request.delete(`/api/sessions/${s.session_id}`)
  }

  const seedResp = await request.post('/api/test/seed', {
    data: {
      display_name: LONG_NAME,
      session_type: 'chat',
      status: 'completed',
      chat_history: [{ role: 'user', content: '估值水平分析' }],
    },
  })
  expect(seedResp.status(), 'seed 需要 TESTING=1 后端（默认 config 或 isolated config 启动）').toBe(200)
  const { session_id } = await seedResp.json()

  try {
    // 新 context 无 localStorage，侧边栏默认展开
    await page.goto('/')
    const rail = page.getByTestId('sidebar-rail')
    await expect(rail).toHaveAttribute('data-state', 'expanded')
    // 种子会话渲染进列表（列表按创建时间倒序，新会话在列表顶部）
    await expect(page.getByTestId('session-list')).toContainText(LONG_NAME)

    // 「新建分析」按钮：容器 p-3 → w-full 上限 256-24 = 232
    await expect
      .poll(async () => (await page.getByTestId('sidebar-new').boundingBox())?.width ?? Number.POSITIVE_INFINITY, {
        message: '「新建分析」按钮被长会话名撑出侧边栏（min-width:auto 拒绝收缩）',
      })
      .toBeLessThanOrEqual(233)

    // 「搜索股票」输入框：容器 px-3 → w-full 上限 232
    await expect
      .poll(async () => (await page.getByPlaceholder('搜索股票...').boundingBox())?.width ?? Number.POSITIVE_INFINITY, {
        message: '「搜索股票」输入框被长会话名撑出侧边栏',
      })
      .toBeLessThanOrEqual(233)

    // 长会话名 div（truncate）：列表 px-2 + 行 px-3 → 上限 256-16-24 = 216；
    // 宽度被约束后 ellipsis 才在可视区内生效
    const nameDiv = page.getByTestId('session-list').locator('.truncate').filter({ hasText: LONG_NAME })
    await expect(nameDiv).toHaveCount(1)
    await expect
      .poll(async () => (await nameDiv.boundingBox())?.width ?? Number.POSITIVE_INFINITY, {
        message: '长会话名 div 未被约束在列表内宽内（truncate 无效化）',
      })
      .toBeLessThanOrEqual(217)
  } finally {
    // 清理种子会话，不污染测试库中其他 spec 的会话列表；best-effort——
    // 删除失手不掩盖原断言失败，遗留由下次运行的预清理自愈
    await request.delete(`/api/sessions/${session_id}`).catch(() => {})
  }
})
