import { expect, test } from '@playwright/test'

/**
 * add-current-stance-view Task 4:当前观点区 E2E 门禁。
 * 红线:不 mock 业务接口——数据经 TESTING=1 的 /api/test/seed 的 track_record
 * .predictions 通道写入独立测试库(与生产同一 insert_prediction 路径)。
 *
 * 套件序:字母序排在本套件末位(本 spec 种子之后无依赖空库用例)。
 * 本地重跑前删 data/test-e2e-track-record.db*(config 头注释同款纪律)。
 *
 * 对 brief 的一处实现修正(实证依据:逐字落盘后套件首跑,该断言 Expected 2
 * Received 3):brief 的全量行数断言 toHaveCount(2) 与其自身前提「断言只认
 * 本 spec 造的 symbol」矛盾——字母序前位 prediction-duplicates 留下
 * 600519.SH 一条 open,list_current_predictions 按股去重后本 spec 运行时
 * stance 区必含其行(共 3 行)。不可改口 toHaveCount(3)(耦合前位种子,前位
 * spec 一变即脆断),故按 brief 自述前提收窄:行数断言过 hasText 过滤只数
 * 本 spec 造的 渝农商行/同花顺 两行。每股收敛语义另有更强证明:601058 台账
 * 2 条 open vs stance 恰 1 行(row601058 count 1 + 最新日期断言)。
 *
 * 空态场景不在本套件覆盖:串行共享持久库且无清库端点,无法可靠构造
 * 「无任何 open」前提;空态由 vitest 单测层覆盖(trackRecordPage.test.tsx)。
 *
 * selector 来源:TrackRecordPage.tsx 真实 testid——current-stance /
 * current-stance-row-* / prediction-log / prediction-tab-*。
 */
test.describe('战绩页:当前观点区(add-current-stance-view)', () => {
  test('每股仅显示最新一条 open;台账不受影响;行点击进详情', async ({ page, request }) => {
    const seedResp = await request.post('/api/test/seed', {
      data: {
        track_record: {
          predictions: [
            { symbol: '601058.SH', symbol_name: '渝农商行', direction: 'neutral', created_at: '2026-10-05T10:00:00' },
            { symbol: '601058.SH', symbol_name: '渝农商行', direction: 'neutral', created_at: '2026-10-06T10:00:00' },
            { symbol: '300033.SZ', symbol_name: '同花顺', direction: 'long', created_at: '2026-10-06T11:00:00' },
          ],
        },
      },
    })
    expect(seedResp.ok()).toBeTruthy()

    await page.goto('/track-record')
    const stance = page.getByTestId('current-stance')
    await expect(stance).toBeVisible()
    // 口径说明常驻(立场视图与台账的语义边界)
    await expect(stance).toContainText('每股仅显示最新一条进行中观点')
    // 每股一行:601058 两条 open 收敛为最新一条(10-06),300033 一行;
    // 行数断言只认本 spec 造的两个 symbol(前位 duplicates 种子的 600519
    // 行是合法存在,见头注释「对 brief 的一处实现修正」)
    const row601058 = stance.getByTestId(/^current-stance-row-/).filter({ hasText: '渝农商行' })
    await expect(
      stance.getByTestId(/^current-stance-row-/).filter({ hasText: /渝农商行|同花顺/ })
    ).toHaveCount(2)
    await expect(row601058).toHaveCount(1)
    await expect(row601058).toContainText('2026-10-06')
    await expect(row601058).toContainText('T+20')

    // 台账不受立场视图影响:缺省「当前持有」tab 下 601058 仍两条 open
    const log = page.getByTestId('prediction-log')
    await expect(log.getByRole('row', { name: /渝农商行/ })).toHaveCount(2)

    // 行点击进入观点详情页(与观点日志行同一详情路由)
    await row601058.click()
    await expect(page).toHaveURL(/\/track-record\/predictions\//)
  })
})
