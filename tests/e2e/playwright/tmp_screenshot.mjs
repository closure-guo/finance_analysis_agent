import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });

const textarea = page.locator('textarea').first();
await textarea.waitFor({ state: 'visible', timeout: 15000 });
await textarea.fill('分析茅台');

const sendButton = page.getByRole('button', { name: /send|发送|提交|arrow|arrowup/i }).first();
await sendButton.click({ timeout: 10000 }).catch(async () => {
  await textarea.press('Enter');
});

await page.waitForTimeout(15000);

await page.screenshot({ path: 'screenshots/maotai-analysis.png', fullPage: false });

console.log('URL:', page.url());
console.log('Title:', await page.title());

await browser.close();
