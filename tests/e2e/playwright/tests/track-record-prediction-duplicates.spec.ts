import { expect, test } from '@playwright/test'

/**
 * add-prediction-pool-integrity Task 8:同日重复(duplicate_of_day)徽标 E2E 门禁。
 * 红线:不 mock 业务接口——数据经 TESTING=1 的 /api/test/seed 的 track_record
 * .predictions 造数通道写入独立测试库(open 行原样 insert;非 open 行经
 * update_prediction_status 置终态,与生产 dedup 判定同一条状态变更路径)。
 *
 * 造数前提:同股(600519.SH)同日(2026-10-09)两条观点——10:00 一条 open、
 * 11:00 一条 duplicate_of_day 终态。后者由判定侧「同日重复关闭」产生:不产
 * 结算读数(无 结算价/收益),不计入已结算分母(settled=win+loss),但计入
 * 观点总数。徽标文案真源 frontend/src/pages/trackRecord/predictionStatus.ts
 * (duplicate_of_day → 「同日重复」)。
 *
 * 造数前提(套件序,对 brief 文件名的一处修正):本 spec 的种子会让观点日志
 * 非空,而 track-record-pred-tabs.spec.ts 依赖空日志断言空态
 * (track-record-empty)且专属套件串行共享同一持久库、无清库端点。Playwright
 * 按文件名字母序执行套件——brief 原名 track-record-duplicates.spec.ts 会排在
 * pred-tabs 之前、污染其空态前提,故改名 track-record-prediction-*保证排在
 * pred-tabs 之后(本套件末位)。本地/CI 重跑前删 data/test-e2e-track-record.db*
 * (见 playwright.track-record.config.ts 头注释)。
 *
 * selector 来源(非盲写):TrackRecordPage.tsx 真实结构——本任务为其表格容器
 * 补的 data-testid="prediction-log" 测试钩子、既有 prediction-tab-* tab 钩子、
 * 行内状态徽标文本(predictionStatus.ts 单一真源)、样本积累横幅
 * track-record-insufficient(已判定 N 条 = settled 读数)。
 */
test.describe('战绩页:同日重复观点徽标', () => {
  test('duplicate 行渲染「同日重复」徽标且无结算读数,总览不计已结算', async ({
    page,
    request,
  }) => {
    const seedResp = await request.post('/api/test/seed', {
      data: {
        track_record: {
          predictions: [
            { symbol: '600519.SH', direction: 'neutral', created_at: '2026-10-09T10:00:00' },
            {
              symbol: '600519.SH',
              direction: 'neutral',
              created_at: '2026-10-09T11:00:00',
              status: 'duplicate_of_day',
              resolution_rule: 'duplicate_of_day',
            },
          ],
        },
      },
    })
    expect(seedResp.ok()).toBeTruthy()

    await page.goto('/track-record')
    await expect(page.getByTestId('prediction-log')).toBeVisible()
    // 总览统计口径:duplicate 行计入观点总数(total=2)、不进已结算分母
    // (settled=win+loss=0 → 样本积累横幅「已判定 0 条」;若 duplicate 被误
    // 计入已结算,该读数会变 1)
    await expect(page.getByTestId('track-record-insufficient')).toHaveText(/已判定 0 条/)

    const log = page.getByTestId('prediction-log')
    // 缺省「当前持有」tab 只含 open 行:duplicate 不漏进当前持有
    await expect(log.getByRole('row', { name: /进行中/ })).toHaveCount(1)
    await expect(log.getByRole('row', { name: /同日重复/ })).toHaveCount(0)

    // 「已判定」tab(status != 'open')收录 duplicate_of_day 终态,且只有它一行
    await page.getByTestId('prediction-tab-resolved').click()
    const dupRow = log.getByRole('row', { name: /同日重复/ })
    await expect(dupRow).toHaveCount(1)
    await expect(log.getByRole('row', { name: /进行中/ })).toHaveCount(0)
    // duplicate 行不产结算读数:无「命中/未中」状态读数、无「未结算」open 提示
    await expect(dupRow).not.toContainText('命中')
    await expect(dupRow).not.toContainText('未中')
    await expect(dupRow).not.toContainText('未结算')

    // 「全部」tab 两行并存:1 open + 1 duplicate
    await page.getByTestId('prediction-tab-all').click()
    await expect(log.getByRole('row', { name: /同日重复/ })).toHaveCount(1)
    await expect(log.getByRole('row', { name: /进行中/ })).toHaveCount(1)
  })
})
