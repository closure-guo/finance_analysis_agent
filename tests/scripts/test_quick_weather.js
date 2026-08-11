const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const logs = [];
  page.on('console', msg => logs.push(`[${msg.type()}] ${msg.text()}`));

  await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
  await page.evaluate((key) => localStorage.setItem('fa_api_key', key), process.env.LLM_API_KEY || 'stub-key-for-testing');
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // 切换到快速模式
  const modeBtn = page.locator('button:has-text("快速模式")');
  if (await modeBtn.count() > 0) {
    await modeBtn.click();
    await page.waitForTimeout(500);
    console.log('已切换到快速模式');
  } else {
    console.log('未找到快速模式按钮，尝试深度模式');
  }

  // 输入并发送
  const textarea = page.locator('textarea').first();
  await textarea.fill('沈阳天气');
  await page.waitForTimeout(500);

  const sendBtn = page.locator('[data-testid="send-button"]');
  if (await sendBtn.count() > 0) {
    await sendBtn.click();
    console.log('已点击发送按钮');
  } else {
    console.log('未找到发送按钮');
  }

  // 等待 30 秒看结果
  console.log('等待 30 秒...');
  await page.waitForTimeout(30000);
  await page.screenshot({ path: 'tests/e2e/screenshot_quick_weather.png', fullPage: true });

  const text = await page.evaluate(() => {
    const main = document.querySelector('.ml-64, .ml-12');
    return main ? main.innerText : document.body.innerText;
  });
  console.log('=== 页面文本 ===');
  console.log(text.substring(0, 800));

  console.log('\n=== 相关日志 ===');
  logs.filter(l =>
    l.includes('error') || l.includes('Error') || l.includes('search') ||
    l.includes('chat') || l.includes('resume') || l.includes('select')
  ).forEach(l => console.log(l));

  await browser.close();
})();
