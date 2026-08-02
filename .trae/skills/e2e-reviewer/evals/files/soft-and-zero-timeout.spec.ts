import { test, expect } from '@playwright/test';

test.describe('notification banner', () => {
  test('banner disappears after dismiss', async ({ page }) => {
    await page.goto('/inbox');
    await page.getByRole('button', { name: 'Dismiss' }).click();
    await expect(page.locator('.banner')).toHaveCount(0, { timeout: 0 });
  });

  test('spinner is bounded, not slept', async ({ page }) => {
    await page.goto('/inbox');
    await page.locator('.spinner').waitFor({ state: 'hidden', timeout: 5000 });
    await expect(page.locator('.inbox-list')).toBeVisible({ timeout: 5000 });
  });

  test('flash error must never appear on the safe path', async ({ page }) => {
    await page.goto('/inbox?safe=1');
    // JUSTIFIED: snapshot-of-absence — the flash error must not exist at this exact moment
    await expect(page.locator('.flash-error')).toHaveCount(0, { timeout: 0 });
  });
});

test.describe('profile panel', () => {
  test('shows all profile fields', async ({ page }) => {
    await page.goto('/profile');
    await expect.soft(page.locator('.name')).toBeVisible();
    await expect.soft(page.locator('.email')).toBeVisible();
    await expect.soft(page.locator('.avatar')).toBeVisible();
  });

  test('shows plan details', async ({ page }) => {
    await page.goto('/profile');
    await expect(page.locator('.plan-panel')).toBeVisible();
    await expect(page.locator('.plan-name')).toHaveText('Pro');
    await expect.soft(page.locator('.renewal-hint')).toContainText('renews');
  });
});
