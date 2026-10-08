import { expect, test } from '@playwright/test'

/**
 * update-track-record-settle-price-display Task 4:结算价格同口径展示 E2E 门禁。
 *
 * 背景（用户可见问题）：列表页「入场价」=决策时点参考价（盘面口径）、「结算价」=
 * hfq 后复权口径——两列不同价格序列不可直接对比（601818 盘面 3.0 vs 后复权 6.5）。
 * 本用例断言修复后的用户可见行为：结算入场价（后复权）列 + 口径列头标注 +
 * 详情页三格（参考价/结算入场价/结算价）。
 *
 * 红线:不 mock 业务接口——数据经 TESTING=1 的 /api/test/seed 的 track_record
 * .predictions 造数通道写入独立测试库;已结算行的结算字段（settle_entry_price/
 * exit_price/raw_return）经 update_prediction_status 透传（与本 PR Task 1，
 * 与生产判定写入同一条状态变更路径）。
 *
 * 套件序:本文件按字母序排在 track-record-prediction-duplicates 之后
 * （set > pre），其种子已让观点日志非空，本 spec 不依赖空态前提。
 * 本地重跑前删 data/test-e2e-track-record.db*（套件共享持久库，
 * 见 playwright.track-record.config.ts 头注释）。
 *
 * selector 来源（非盲写）:TrackRecordPage.tsx 真实结构——COLUMNS 列头文本、
 * prediction-tab-all tab 钩子（默认「当前持有」tab 只显示 open 行，已结算行
 * 须切「全部」）、prediction-row-{id} 行钩子、prediction-decision 详情卡钩子。
 */
test.describe('战绩页:结算价格同口径展示', () => {
  test('已结算行三价同口径可比+列头口径标注+详情页三格', async ({ page, request }) => {
    const seedResp = await request.post('/api/test/seed', {
      data: {
        track_record: {
          predictions: [
            {
              symbol: '600015.SH',
              symbol_name: '华夏银行',
              direction: 'short',
              entry_price: 3.0,
              created_at: '2026-10-09T18:00:00',
            },
            {
              symbol: '601818.SH',
              symbol_name: '光大银行',
              direction: 'short',
              entry_price: 3.0,
              created_at: '2026-10-09T17:00:00',
              status: 'resolved_loss',
              resolution_rule: 'horizon',
              settle_entry_price: 6.39,
              exit_price: 6.5,
              raw_return: -0.0172,
            },
          ],
        },
      },
    })
    expect(seedResp.ok()).toBeTruthy()

    await page.goto('/track-record')
    await expect(page.getByTestId('prediction-log')).toBeVisible()

    // 列头口径标注:三列各标其口径（spec Scenario: 已结算行展示同口径可比价格）
    const log = page.getByTestId('prediction-log')
    await expect(log.getByText('参考价（盘面）')).toBeVisible()
    await expect(log.getByText('结算入场价（后复权）')).toBeVisible()
    await expect(log.getByText('结算价（后复权）')).toBeVisible()

    // 默认「当前持有」tab 只含 open 行 → 切「全部」tab 看已结算行
    await page.getByTestId('prediction-tab-all').click()

    // 已结算行:盘面参考价 3.00 与后复权 6.39/6.50 同行可辨（跨口径并列但不混淆——
    // 列头已标注口径），区间收益 -1.72% 与后复权两端自洽
    const resolvedRow = log.locator('tr', { hasText: '光大银行' }).first()
    await expect(resolvedRow).toBeVisible()
    await expect(resolvedRow).toContainText('3.00')
    await expect(resolvedRow).toContainText('6.39')
    await expect(resolvedRow).toContainText('6.50')

    // 进行中行:结算两列占位「—」，无结算读数
    const openRow = log.locator('tr', { hasText: '华夏银行' }).first()
    await expect(openRow).toContainText('未结算')
    await expect(openRow).not.toContainText('6.39')

    // 详情页:价格区三格（参考价/结算入场价/结算价）带口径标注
    await resolvedRow.click()
    const decision = page.getByTestId('prediction-decision')
    await expect(decision).toBeVisible()
    await expect(decision).toContainText('参考价（盘面）')
    await expect(decision).toContainText('结算入场价（后复权）')
    await expect(decision).toContainText('结算价（后复权）')
    await expect(decision).toContainText('3.00')
    await expect(decision).toContainText('6.39')
    await expect(decision).toContainText('6.50')
  })
})
