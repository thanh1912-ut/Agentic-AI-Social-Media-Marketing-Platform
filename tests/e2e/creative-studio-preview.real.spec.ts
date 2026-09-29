import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';

test('chụp màn hình đăng nhập của preview real mode, không nhập tài khoản', async ({ page }) => {
  test.skip(!process.env.CREATIVE_STUDIO_REAL_SCREENSHOTS, 'Chỉ chụp trang đăng nhập thật khi CREATIVE_STUDIO_REAL_SCREENSHOTS được đặt.');
  const output = resolve(process.env.CREATIVE_STUDIO_REAL_SCREENSHOTS ?? '.');
  await mkdir(output, { recursive: true });
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: /Chào mừng trở lại/ })).toBeVisible();
  await expect(page.getByText('Lối tắt đăng nhập demo')).toHaveCount(0);

  for (const viewport of [
    { name: 'desktop', width: 1440, height: 960 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.screenshot({ path: join(output, `login-${viewport.name}.png`), fullPage: true });
  }
});
