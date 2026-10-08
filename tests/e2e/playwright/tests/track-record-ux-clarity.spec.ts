import { expect, test } from '@playwright/test'

/**
 * update-track-record-display-clarity Task 8:展示治理 E2E 门禁。
 * 红线:不 mock 业务接口——造数走 TESTING=1 的 /api/test/seed(predictions + 行内 marks)。
 * 套件序:字母序排本套件末位(ux > stance);断言只认本 spec 造的 symbol(601318/000858/601288)。
 * 覆盖:窗口列混合口径 / open 行浮动收益(盯市 title) / 同日重复折叠展开(total 不变) /
 * 切片空态折叠 / 详情页方向+判定规则中文映射。
 *
 * 对 brief 的两处实现修正(实证依据:TrackRecordPage.tsx 折叠逻辑 + model.py
 * list_predictions 排序,逐条核过):
 * 1.brief 种子只写 2 条 duplicate_of_day 行,但其断言要求「同日重复 ×3」——
 *   dup-group 仅合并 consecutive duplicate_of_day 行(同 symbol 同日,open 行
 *   不入组),2 条必渲染 ×2。补第 3 条 dup(13:00),与断言及注释「3 dup 明细」
 *   的本意对齐(沿用 stance-view「对 brief 的一处实现修正」先例)。
 * 2.展开后五粮液行数 brief 写 toHaveCount(4)(注释「1 open + 3 dup 明细」)——
 *   漏算常驻汇总行:展开时 dup-group 汇总行仍在(Fragment 结构,汇总 tr 恒渲染),
 *   实为 1 汇总 + 3 明细 + 1 open = 5。改 toHaveCount(5),计数注释如实。
 *
 * 切片空态前提(brief 尾注担忧,已实证不触发):切片空态要求 overview.settled=0
 * (settled=win+loss,model.py compute_stats),字母序前位 spec 种子只有 open/
 * duplicate_of_day/resolved_neutral 行(index-compare/portfolio 仅曲线、pred-tabs
 * 无种子、duplicates 600519 open+dup、stance-view 3 open),无任何 resolved_win/
 * loss——settled 恒 0,空态前提在全套件成立,切片断言无需移入有前提的 test。
 *
 * scan.sh 清零改造(原文两处一次性/疑似恒真断言,按 e2e-reviewer P0 要求改 web-first):
 * - 盯市 title 断言由 toBeAttached 取首个匹配 → toHaveCount(2):区间收益/基准超额
 *   两个收益格同携「盯市 日期（未结算浮动）」title(TrackRecordPage.tsx markTitle
 *   双 td 注入),计数断言同时消除位置取首个匹配的选择器写法(P1 #10a);
 * - 分页 total 不变断言由一次性取 innerText 后比对 → 捕获「共 N 条」span
 *   后 toHaveText 自动重试断言(P0 #4c-4e)。
 *
 * dup-group testid 用正则匹配:key 含首行服务端 prediction_id(种子时服务端生成,
 * 不可预知),防同股同日多段 consecutive dup 区撞 key 的串扰(生产 688072
 * 2026-10-02 实证);本套件种子仅一段连续 dup,正则唯一命中。
 */
test.describe('战绩页:展示治理(add-track-record-display-clarity)', () => {
  let seeded = false

  test.beforeEach(async ({ request }) => {
    if (seeded) return
    const resp = await request.post('/api/test/seed', {
      data: {
        track_record: {
          predictions: [
            {
              symbol: '601318.SH', symbol_name: '中国平安', direction: 'short',
              created_at: '2026-10-01T10:00:00',
              marks: [{ mark_date: '2026-10-08', cum_return: -0.012, cum_excess: -0.008 }],
            },
            {
              symbol: '601318.SH', symbol_name: '中国平安', direction: 'neutral',
              created_at: '2026-10-02T10:00:00', horizon_days: 252,
            },
            {
              symbol: '000858.SH', symbol_name: '五粮液', direction: 'neutral',
              created_at: '2026-10-05T10:00:00',
            },
            {
              symbol: '000858.SH', symbol_name: '五粮液', direction: 'neutral',
              created_at: '2026-10-05T11:00:00', status: 'duplicate_of_day', resolution_rule: 'duplicate_of_day',
            },
            {
              symbol: '000858.SH', symbol_name: '五粮液', direction: 'neutral',
              created_at: '2026-10-05T12:00:00', status: 'duplicate_of_day', resolution_rule: 'duplicate_of_day',
            },
            {
              symbol: '000858.SH', symbol_name: '五粮液', direction: 'neutral',
              created_at: '2026-10-05T13:00:00', status: 'duplicate_of_day', resolution_rule: 'duplicate_of_day',
            },
            {
              symbol: '601288.SH', symbol_name: '农业银行', direction: 'short',
              created_at: '2026-10-04T10:00:00', status: 'resolved_neutral', resolution_rule: 'superseded',
            },
          ],
        },
      },
    })
    expect(resp.ok()).toBeTruthy()
    seeded = true
  })

  test('窗口列混合口径 + open 行浮动收益 + 无盯市显示 —', async ({ page }) => {
    await page.goto('/track-record')
    const log = page.getByTestId('prediction-log')
    // 601318 short open(有盯市):T+20 + 浮动收益 + 盯市日期 title
    const peace = log.getByRole('row').filter({ hasText: '中国平安' }).filter({ hasText: '看空' })
    await expect(peace).toHaveCount(1)
    await expect(peace).toContainText('T+20')
    await expect(peace).toContainText('-1.20%')
    await expect(peace).toContainText('-0.80%')
    // 两个收益格(区间收益/基准超额)同携盯市 title——以计数断言锁定,不用位置选择器
    await expect(peace.getByTitle('盯市 2026-10-08（未结算浮动）')).toHaveCount(2)
    // 601318 neutral open(无盯市,T+252):收益格 —
    // (行级宽松断言:行内其他占位格也可能含 —,稀释已知限制;严格列级定位见 vitest 单测)
    const peaceNeutral = log.getByRole('row').filter({ hasText: '中国平安' }).filter({ hasText: '中性' })
    await expect(peaceNeutral).toHaveCount(1)
    await expect(peaceNeutral).toContainText('T+252')
    await expect(peaceNeutral).toContainText('—')
    // 口径披露行双计数:本套件种子中旧口径 open 行仅 601318 neutral h=252 一条
    // (前位 spec 种子 horizon 均缺省 20)→ legacy_open=1
    await expect(page.getByTestId('track-record-legacy-open')).toContainText('另有 1 条旧口径进行中')
    // 副标题不再含「20 日」
    await expect(page.getByTestId('prediction-log-header')).not.toContainText('20 日')
  })

  test('同日重复折叠:默认汇总 ×3,展开后明细可见,total 不变', async ({ page }) => {
    await page.goto('/track-record')
    await page.getByTestId('prediction-tab-all').click()
    const log = page.getByTestId('prediction-log')
    // key 含首行服务端 prediction_id(不可预知)→ 正则;种子仅一段连续 dup,唯一命中
    const group = page.getByTestId(/^dup-group-000858\.SH-2026-10-05-/)
    await expect(group).toContainText('同日重复 ×3')
    // total 不变:「共 N 条」span 全文捕获,展开后 toHaveText 自动重试比对
    const pagBefore = await page.getByTestId('track-record-pagination').getByText(/共 \d+ 条/).innerText()
    await group.click()
    await expect(log.getByRole('row', { name: /五粮液/ })).toHaveCount(5) // 1 汇总 + 3 dup 明细 + 1 open
    await expect(page.getByTestId('track-record-pagination').getByText(/共 \d+ 条/)).toHaveText(pagBefore)
    await group.click()
    await expect(log.getByRole('row', { name: /五粮液/ })).toHaveCount(2) // 收起:1 open + 1 汇总
  })

  test('已判定 tab:带内中性标签;详情页方向/判定规则中文', async ({ page }) => {
    await page.goto('/track-record')
    await page.getByTestId('prediction-tab-resolved').click()
    const abc = page.getByTestId('prediction-log').getByRole('row').filter({ hasText: '农业银行' })
    await expect(abc).toContainText('带内中性')
    await abc.click()
    await expect(page).toHaveURL(/\/track-record\/predictions\//)
    await expect(page.getByText('看空', { exact: true })).toBeVisible()
    await expect(page.getByText('被新观点替代·提前结算')).toBeVisible()
  })

  test('切片空态折叠:settled=0 不渲染分桶表格', async ({ page }) => {
    await page.goto('/track-record')
    await expect(page.getByTestId('track-record-segments-empty')).toContainText('切片指标将在首批观点结算后可用')
    await expect(page.getByTestId('track-record-segments')).toHaveCount(0)
  })
})
