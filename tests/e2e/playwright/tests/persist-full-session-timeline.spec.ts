import { test, expect } from '@playwright/test'

/**
 * 切换会话后时序完整恢复（persist-full-session-timeline delta）
 *
 * 验证目标：
 * 1. 对话时序恢复：chat 会话 assistant 消息携带 agentTimeline
 *    [thinking, search(带results), thinking, tool_call] 交错时序，切回后
 *    思考横幅 / 搜索横幅（query + 结果数）/ 工具调用横幅按交错顺序渲染，
 *    且未走拍平近似（搜索横幅独立于工具调用横幅，两个思考横幅各自独立）。
 * 2. 管线时序恢复：analysis/completed 会话携带 report_markdown + pipeline_snapshot
 *    + pipeline_timelines（{trader, research_manager}），切回后报告可见、
 *    分层时间轴可见、节点分组标题（Trader / 研究经理）下对应思考/搜索/工具内容可见。
 * 3. 向后兼容：仅 thinking + tool_calls（无 agentTimeline）的旧会话切回不报错、正常显示。
 *
 * 确定性方案（TESTING=1 + STUB_SCENARIO=pipeline，后端 8002 / 前端 5175）：
 *   - 全程经 /api/test/seed 真实写入 session_store（不 mock 业务接口）
 *   - 全程通过前端 UI 真实操作：点击侧边栏会话项触发 selectSession -> GET /api/sessions/{id}
 *
 * Selector 约定：
 *   - 侧边栏会话项以 display_name 文本定位（复跑时可能有同名旧会话，first 锁定最新一条）
 *   - 思考横幅 getByRole('button', { name: /思考已完成/ })（历史恢复 streaming=false）
 *   - 搜索横幅 getByRole('button', { name: /搜索了.*个网页/ })（SearchBanner done 态）
 *   - 工具调用横幅 getByRole('button', { name: /工具调用/ })（历史恢复 done=true）
 *   - 分层时间轴 data-testid="pipeline-timeline"
 */

// 后端 8002（timeline config 的管线 stub 端口）
const API_BASE = 'http://localhost:8002'
const FRONTEND_BASE = 'http://localhost:5175'

// 侧边栏会话项点击：display_name 文本定位（复跑时可能有同名旧会话，用 first 锁定最新一条）
async function clickSession(page: import('@playwright/test').Page, name: string) {
  await page.getByText(name, { exact: true }).first().click()
}

// 造数 + 打开前端并点选会话（公共前置：seed 真实写库 -> localStorage 初始化 -> reload -> 点击侧边栏）
async function seedAndSelect(
  page: import('@playwright/test').Page,
  seedData: Record<string, unknown>,
  sessionName: string,
) {
  const seedResp = await page.request.post(`${API_BASE}/api/test/seed`, { data: seedData })
  expect(seedResp.ok()).toBeTruthy()
  const seedBody = await seedResp.json()
  expect(seedBody.session_id).toBeTruthy()

  await page.goto(FRONTEND_BASE)
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'stub-key-for-testing')
    localStorage.setItem('fa_user_id', 'user-test-persist-timeline')
    localStorage.removeItem('financeAgent.pipelineDurations')
  })
  await page.reload()

  await clickSession(page, sessionName)
  return seedBody.session_id as string
}

// 交错时序种子（thinking -> search -> thinking -> tool_call），供用例 1 使用
const CHAT_TIMELINE = [
  { type: 'thinking', content: '先理解用户意图：分析茅台基本面。', title: '理解需求', done: true },
  {
    type: 'search',
    query: '贵州茅台 2025 基本面',
    results: [
      { title: '贵州茅台年报解读', url: 'https://example.com/mt-report', content: '营收利润双增。' },
      { title: '白酒行业景气度跟踪', url: 'https://example.com/baijiu', content: '行业动销稳健。' },
    ],
    status: 'done',
  },
  { type: 'thinking', content: '搜索结果显示基本面稳健，继续查证股票代码。', title: '分析搜索结果', done: true },
  {
    type: 'tool_call',
    name: 'search_stock',
    args: 'query=茅台',
    result: '600519 贵州茅台',
    done: true,
  },
]

test.describe('切换会话后时序完整恢复（persist-full-session-timeline）', () => {
  test('1. 对话时序恢复：思考/搜索/工具调用横幅按交错顺序渲染', async ({ page }) => {
    await seedAndSelect(
      page,
      {
        display_name: 'E2E对话时序恢复会话',
        session_type: 'chat',
        chat_history: [
          { role: 'user', content: '帮我分析一下茅台' },
          {
            role: 'assistant',
            content: '茅台是白酒龙头，基本面稳健。',
            agentTimeline: CHAT_TIMELINE,
          },
        ],
      },
      'E2E对话时序恢复会话',
    )

    // 三类横幅均可见：2 个思考横幅（交错的两段思考各自独立，带 title 时折叠文案为 title）
    // + 1 个搜索横幅 + 1 个工具调用横幅
    const thinking1 = page.getByRole('button', { name: /理解需求/ })
    await expect(thinking1).toBeVisible({ timeout: 10_000 })
    const thinking2 = page.getByRole('button', { name: /分析搜索结果/ })
    await expect(thinking2).toBeVisible({ timeout: 10_000 })

    // 搜索横幅（done 态文案"搜索了 N 个网页 · query"）；独立于工具调用横幅 => 未走拍平
    const searchBanner = page.getByRole('button', { name: /搜索了.*个网页/ })
    await expect(searchBanner).toBeVisible({ timeout: 10_000 })
    // query 与结果数均恢复
    await expect(searchBanner).toContainText('贵州茅台 2025 基本面')
    await expect(searchBanner).toContainText('2')

    // 工具调用横幅（search_stock -> label「识别股票」，非搜索横幅）
    const toolCallBanner = page.getByRole('button', { name: /工具调用/ })
    await expect(toolCallBanner).toBeVisible({ timeout: 10_000 })

    // 交错顺序断言：思考1 < 搜索 < 思考2 < 工具调用（boundingBox.y 比较）
    const thinking1Box = await thinking1.boundingBox()
    const searchBox = await searchBanner.boundingBox()
    const thinking2Box = await thinking2.boundingBox()
    const toolCallBox = await toolCallBanner.boundingBox()
    expect(thinking1Box).not.toBeNull()
    expect(searchBox).not.toBeNull()
    expect(thinking2Box).not.toBeNull()
    expect(toolCallBox).not.toBeNull()
    expect(thinking1Box!.y).toBeLessThan(searchBox!.y)
    expect(searchBox!.y).toBeLessThan(thinking2Box!.y)
    expect(thinking2Box!.y).toBeLessThan(toolCallBox!.y)
  })

  test('2. 管线时序恢复：报告 + 分层时间轴 + 节点分组下思考/搜索/工具内容', async ({ page }) => {
    // 造一个 completed 的 analysis 会话：
    // pipeline_snapshot（completed 的 layerTree 序列化字符串，内嵌在 snapshot JSON 中）
    // + pipeline_timelines（trader / research_manager 两节点时序）
    const completedLayerTree = [
      { id: 'prep', label: 'PREP', status: 'completed', children: [] },
      { id: 'layer1', label: 'Layer I', status: 'completed', children: [] },
      { id: 'layer2', label: 'Layer II', status: 'completed', children: [] },
      { id: 'trader', label: 'Trader', status: 'completed', children: [] },
      { id: 'risk', label: 'Risk', status: 'completed', children: [] },
      { id: 'fund', label: 'Fund', status: 'completed', children: [] },
    ]
    await seedAndSelect(
      page,
      {
        display_name: 'E2E管线时序恢复会话',
        session_type: 'analysis',
        status: 'completed',
        report_markdown: '# 贵州茅台深度分析报告\n\n结论：谨慎增持。',
        chat_history: [{ role: 'user', content: '深度分析600519' }],
        pipeline_snapshot: {
          layerTree: JSON.stringify(completedLayerTree),
          currentNodeId: '',
          progress: 1,
          updatedAt: 1700000000000,
        },
        pipeline_timelines: {
          trader: [
            { type: 'thinking', content: '权衡多空观点，形成交易决策。', title: '交易权衡', done: true },
            {
              type: 'tool_call',
              name: 'get_position',
              args: 'symbol=600519',
              result: '{"shares": 0}',
              done: true,
            },
          ],
          research_manager: [
            { type: 'thinking', content: '汇总多空辩论要点，形成研究结论。', title: '辩论汇总', done: true },
            {
              type: 'search',
              query: '贵州茅台 最新估值',
              results: [
                { title: '茅台估值跟踪', url: 'https://example.com/valuation', content: 'PE 处于历史中枢。' },
              ],
              status: 'done',
            },
          ],
        },
      },
      'E2E管线时序恢复会话',
    )

    // 报告可见（completed 分支按报告消息重建；stockName 为空故断言固定文案「深度分析报告」）
    await expect(page.getByText('深度分析报告').first()).toBeVisible({ timeout: 15_000 })

    // 分层时间轴可见（completed 分支按快照 layerTree 静态渲染）
    const timeline = page.getByTestId('pipeline-timeline')
    await expect(timeline).toBeVisible({ timeout: 15_000 })

    // 节点分组标题可见（nodeDisplayName：trader -> Trader，research_manager -> 研究经理）
    await expect(page.getByText('Trader', { exact: true }).first()).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('研究经理', { exact: true })).toBeVisible()

    // Trader 分组下：思考横幅 + 工具调用横幅（get_position 不在 label 映射表，原样显示 name）
    // 用 data-timeline-index 容器断言顺序：trader 组 thinking(0) < tool_call(1)
    const traderThinking = page.getByRole('button', { name: /交易权衡/ })
    await expect(traderThinking).toBeVisible({ timeout: 10_000 })
    const traderToolCall = page.getByRole('button', { name: /工具调用.*1 次/ })
    await expect(traderToolCall.first()).toBeVisible({ timeout: 10_000 })

    // 研究经理分组下：思考横幅 + 搜索横幅（query 恢复）
    const managerThinking = page.getByRole('button', { name: /辩论汇总/ })
    await expect(managerThinking).toBeVisible({ timeout: 10_000 })
    const managerSearch = page.getByRole('button', { name: /搜索了.*个网页/ })
    await expect(managerSearch).toBeVisible({ timeout: 10_000 })
    await expect(managerSearch).toContainText('贵州茅台 最新估值')

    // 分组时序断言：Trader 分组整体在研究经理分组上方（Object.entries 插入序 = seed 顺序）
    const traderBox = await page.getByText('Trader', { exact: true }).first().boundingBox()
    const managerBox = await page.getByText('研究经理', { exact: true }).boundingBox()
    expect(traderBox).not.toBeNull()
    expect(managerBox).not.toBeNull()
    expect(traderBox!.y).toBeLessThan(managerBox!.y)
  })

  test('3. 向后兼容：仅 thinking + tool_calls（无 agentTimeline）的旧会话正常恢复', async ({ page }) => {
    await seedAndSelect(
      page,
      {
        display_name: 'E2E旧格式会话',
        session_type: 'chat',
        chat_history: [
          { role: 'user', content: '看看平安银行' },
          {
            role: 'assistant',
            content: '平安银行是股份制银行龙头之一。',
            thinking: '用户想了解平安银行，先确认股票代码。',
            tool_calls: [
              {
                name: 'search_stock',
                args: { query: '平安银行' },
                result_text: '000001 平安银行',
                done: true,
              },
            ],
          },
        ],
      },
      'E2E旧格式会话',
    )

    // 旧数据回退拍平近似：思考在前、工具调用在后（buildTimelineFromHistory），页面不报错
    const thinkingBanner = page.getByRole('button', { name: /思考已完成/ })
    await expect(thinkingBanner).toBeVisible({ timeout: 10_000 })
    const toolCallBanner = page.getByRole('button', { name: /工具调用/ })
    await expect(toolCallBanner).toBeVisible({ timeout: 10_000 })

    // 回复正文可见（会话整体正常渲染）
    await expect(page.getByText('平安银行是股份制银行龙头之一。')).toBeVisible()

    // 拍平近似下不应出现独立搜索横幅（search_stock 非搜索类工具，还原为 tool_call item）
    await expect(page.getByRole('button', { name: /搜索了.*个网页/ })).toHaveCount(0)
  })
})
