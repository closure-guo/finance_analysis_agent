// Playwright CLI 脚本：逐步操作前端，调试切换会话后内容消失问题
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // 收集 console 日志
  const consoleLogs = [];
  page.on('console', msg => {
    consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
  });

  // 辅助函数：获取聊天内容区域文本
  async function getChatContent() {
    return await page.evaluate(() => {
      // 主内容区域有 ml-64 或 ml-12 class（侧边栏切换）
      const main = document.querySelector('.ml-64, .ml-12');
      if (main) return main.innerText;
      // fallback：获取 body 文本，排除侧边栏
      const sidebar = document.querySelector('[class*="fixed"], [class*="sidebar"]');
      const bodyText = document.body.innerText;
      return bodyText;
    });
  }

  // 步骤1：导航到首页
  console.log('\n=== 步骤1：导航到首页 ===');
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });

  // 设置 API Key 到 localStorage
  await page.evaluate(() => {
    localStorage.setItem('fa_api_key', 'sk-2e9c5078489c4a9abb8d275470a8b4b2');
  });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  console.log('页面已加载，API Key 已设置');

  // 步骤2：输入股票名称并发送
  console.log('\n=== 步骤2：输入股票名称并发送 ===');
  const textarea = page.locator('textarea[placeholder*="输入股票"]');
  await textarea.fill('分析贵州茅台');
  await page.waitForTimeout(500);

  // 发送按钮有 data-testid="send-button" 或 fa-arrow-up 图标
  const sendBtn = page.locator('[data-testid="send-button"]');
  if (await sendBtn.count() > 0) {
    await sendBtn.click();
  } else {
    await page.locator('button:has(i.fa-arrow-up)').first().click();
  }
  console.log('已点击发送按钮');

  // 步骤3：等待 agent 开始输出
  console.log('\n=== 步骤3：等待 agent 输出（15秒）===');
  await page.waitForTimeout(15000);

  await page.screenshot({ path: 'tests/e2e/screenshot_step3_after_send.png', fullPage: true });

  const mainContent = await getChatContent();
  console.log('聊天内容（前600字符）:', mainContent.substring(0, 600));
  console.log('聊天内容长度:', mainContent.length);

  // 打印相关 console 日志
  const relevantLogs = consoleLogs.filter(l =>
    l.includes('resumeStream') || l.includes('selectSession') || l.includes('saveCurrentStreamState') ||
    l.includes('error') || l.includes('Error')
  );
  console.log('\n相关 console 日志:');
  relevantLogs.forEach(l => console.log('  ', l));

  // 步骤4：点击"新建分析"按钮
  console.log('\n=== 步骤4：点击新建分析 ===');
  consoleLogs.length = 0; // 清空日志
  await page.locator('button:has-text("新建分析")').click();
  await page.waitForTimeout(2000);
  console.log('已点击新建分析');

  await page.screenshot({ path: 'tests/e2e/screenshot_step4_new_session.png', fullPage: true });
  const newText = await getChatContent();
  console.log('新建分析后聊天内容（前200字符）:', newText.substring(0, 200));

  // 步骤5：切回之前的会话
  console.log('\n=== 步骤5：切换回之前的会话 ===');
  // 会话列表中的项有 cursor-pointer class，点击包含"分析贵州茅台"的项
  const sessionItem = page.locator('div.cursor-pointer:has-text("分析贵州茅台")').first();
  if (await sessionItem.count() > 0) {
    await sessionItem.click();
    console.log('已点击切换回"分析贵州茅台"会话');
  } else {
    console.log('未找到"分析贵州茅台"会话项');
    const allItems = await page.locator('div.cursor-pointer').allTextContents();
    console.log('所有可点击项:', allItems.map(t => t.trim().substring(0, 30)));
  }

  await page.waitForTimeout(3000);
  await page.screenshot({ path: 'tests/e2e/screenshot_step5_switch_back.png', fullPage: true });

  // 检查切换后的聊天内容
  const switchBackText = await getChatContent();
  console.log('\n切换后聊天内容（前600字符）:', switchBackText.substring(0, 600));
  console.log('切换后聊天内容长度:', switchBackText.length);

  // 检查切换后的 console 日志
  const switchLogs = consoleLogs.filter(l =>
    l.includes('resumeStream') || l.includes('selectSession') || l.includes('saveCurrentStreamState') ||
    l.includes('error') || l.includes('Error')
  );
  console.log('\n切换后相关 console 日志:');
  switchLogs.forEach(l => console.log('  ', l));

  // 步骤6：等待并检查是否有新输出
  console.log('\n=== 步骤6：等待切换后的输出（10秒）===');
  await page.waitForTimeout(10000);
  await page.screenshot({ path: 'tests/e2e/screenshot_step6_after_wait.png', fullPage: true });

  const finalText = await getChatContent();
  console.log('最终聊天内容（前600字符）:', finalText.substring(0, 600));
  console.log('最终聊天内容长度:', finalText.length);

  // 最终 console 日志
  const finalLogs = consoleLogs.filter(l =>
    l.includes('resumeStream') || l.includes('selectSession') || l.includes('saveCurrentStreamState') ||
    l.includes('error') || l.includes('Error')
  );
  console.log('\n最终相关 console 日志:');
  finalLogs.forEach(l => console.log('  ', l));

  // 诊断结果
  console.log('\n=== 诊断结果 ===');
  console.log(`切换前聊天内容长度: ${mainContent.length}`);
  console.log(`切换后聊天内容长度: ${switchBackText.length}`);
  console.log(`最终聊天内容长度: ${finalText.length}`);

  if (finalText.length < 20 && mainContent.length > 20) {
    console.log('❌ 内容丢失！切换后聊天内容消失');
  } else if (finalText.length >= mainContent.length * 0.5) {
    console.log('✅ 切换后内容恢复正常');
  } else {
    console.log('⚠️ 内容部分丢失，需要检查');
  }

  await browser.close();
})();
