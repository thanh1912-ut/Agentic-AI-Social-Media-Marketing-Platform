import { expect, test } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { join, resolve } from 'node:path';

const OWNER = { email: 'chu.quan@phobac.vn', password: 'demo1234' };

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(OWNER.email);
  await page.getByLabel('Mật khẩu').fill(OWNER.password);
  await page.getByRole('button', { name: 'Đăng nhập' }).click();
  await page.waitForURL((url) => url.pathname === '/' || url.pathname.startsWith('/w/'));
  if (new URL(page.url()).pathname === '/') {
    await page.getByRole('button', { name: 'Tiếp tục tới tài liệu' }).click();
  }
  await page.waitForURL(/\/w\//);
}

test.describe('giao diện thích ứng và điều hướng', () => {
  test('chụp ảnh tổng quan desktop và mobile cho báo cáo UI', async ({ page }) => {
    test.skip(!process.env.UI_REFRESH_CAPTURE_DIR, 'Chỉ tạo ảnh khi UI_REFRESH_CAPTURE_DIR được đặt.');
    await login(page);
    await page.goto('/w/ws_pho_bac');
    await expect(page.getByRole('heading', { name: /Tổng quan/ })).toBeVisible();

    const output = resolve(process.env.UI_REFRESH_CAPTURE_DIR ?? '.');
    await mkdir(output, { recursive: true });
    await page.setViewportSize({ width: 1440, height: 960 });
    await page.screenshot({ path: join(output, 'desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: join(output, 'mobile.png'), fullPage: true });
  });

  test('các màn hình làm việc không tràn ngang ở kích thước chuẩn', async ({ page }) => {
    await login(page);
    for (const width of [390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const route of ['/documents', '/fanpages', '/analytics']) {
        await page.goto(`/w/ws_pho_bac${route}`);
        await page.waitForLoadState('domcontentloaded');
        const dimensions = await page.evaluate(() => ({ viewport: window.innerWidth, page: document.documentElement.scrollWidth }));
        expect(dimensions.page, `${route} ở ${width}px`).toBeLessThanOrEqual(dimensions.viewport + 1);
      }
    }
  });

  test('menu di động mở, đóng bằng Escape và trả focus về nút mở', async ({ page }) => {
    await login(page);
    await page.setViewportSize({ width: 390, height: 844 });
    const openButton = page.getByRole('button', { name: 'Mở menu' });
    await openButton.click();
    const dialog = page.getByRole('dialog', { name: 'Điều hướng' });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole('link', { name: 'Tài liệu', exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).not.toBeVisible();
    await expect(openButton).toBeFocused();
  });

  test('analytics và đề xuất có một mục đang hoạt động trong sidebar', async ({ page }) => {
    await login(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/w/ws_pho_bac/analytics');
    const currentLinks = page.locator('.app-sidebar a[aria-current="page"]');
    await expect(currentLinks).toHaveCount(1);
    await expect(currentLinks).toHaveText('Hiệu quả & đề xuất');
  });
});
