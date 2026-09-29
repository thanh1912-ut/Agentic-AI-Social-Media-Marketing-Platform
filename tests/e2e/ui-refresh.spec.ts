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
    await page.getByRole('button', { name: 'Mở không gian làm việc' }).click();
  }
  await page.waitForURL(/\/w\//);
  await page.goto('/w/ws_pho_bac/documents');
  await page.waitForURL(/\/documents$/);
}

test.describe('giao diện thích ứng và điều hướng', () => {
  test('chụp các màn hình chính desktop và mobile cho báo cáo UI', async ({ page }) => {
    test.skip(!process.env.CREATIVE_STUDIO_SCREENSHOT_DIR, 'Chỉ tạo ảnh khi CREATIVE_STUDIO_SCREENSHOT_DIR được đặt.');
    const output = resolve(process.env.CREATIVE_STUDIO_SCREENSHOT_DIR ?? '.');
    await mkdir(output, { recursive: true });

    // Ảnh đăng nhập để trống; ảnh nghiệp vụ dùng fixture MSW và được ghi nhãn demo.
    await page.goto('/login');
    await expect(page.getByRole('heading', { name: /Chào mừng trở lại/ })).toBeVisible();
    for (const viewport of [{ name: 'desktop', width: 1440, height: 960 }, { name: 'mobile', width: 390, height: 844 }]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.screenshot({ path: join(output, `login-${viewport.name}.png`), fullPage: true });
    }

    await login(page);
    const routes = [
      { name: 'overview', path: '/w/ws_pho_bac', heading: /Tổng quan/ },
      { name: 'documents', path: '/w/ws_pho_bac/documents', heading: /Tài liệu/ },
      { name: 'campaigns', path: '/w/ws_pho_bac/campaigns', heading: /Chiến dịch/ },
      { name: 'editor', path: '/w/ws_pho_bac/campaigns/cmp_khai_truong/posts/post_1', heading: /Biên tập bài viết/ },
      { name: 'publishing', path: '/w/ws_pho_bac/publishing', heading: /Xuất bản/ },
      { name: 'market', path: '/w/ws_pho_bac/fanpages', heading: /Fanpage/ },
    ];

    for (const route of routes) {
      await page.setViewportSize({ width: 1440, height: 960 });
      await page.goto(route.path);
      await expect(page.getByRole('heading', { name: route.heading }).first()).toBeVisible();
      await page.screenshot({ path: join(output, `${route.name}-desktop.png`), fullPage: true });
      await page.setViewportSize({ width: 390, height: 844 });
      await page.screenshot({ path: join(output, `${route.name}-mobile.png`), fullPage: true });
    }
  });

  test('các màn hình làm việc không tràn ngang ở kích thước chuẩn', async ({ page }) => {
    await login(page);
    for (const width of [390, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const route of ['/brand', '/documents', '/campaigns', '/campaigns/cmp_khai_truong/posts/post_1', '/publishing', '/fanpages', '/analytics', '/settings']) {
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

  test('tab nội dung được giữ trong URL và khôi phục sau reload', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/fanpages');
    await page.waitForURL(/\/research/);
    await page.getByRole('tab', { name: 'Phân tích & hướng viết' }).click();
    await expect(page).toHaveURL(/tab=reports/);
    await page.reload();
    await expect(page.getByRole('tab', { name: 'Phân tích & hướng viết' })).toHaveAttribute('aria-selected', 'true');

    await page.goto('/w/ws_pho_bac/publishing?tab=history');
    await expect(page.getByRole('tab', { name: 'Lịch sử' })).toHaveAttribute('aria-selected', 'true');
    await page.getByRole('tab', { name: 'Bài đã duyệt' }).focus();
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('tab', { name: 'Lịch đăng' })).toBeFocused();
  });

  test('giao diện không tràn ở mức zoom 200% và tôn trọng reduced motion', async ({ page }) => {
    await login(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/w/ws_pho_bac/campaigns/cmp_khai_truong/posts/post_1');
    await page.evaluate(() => { document.documentElement.style.zoom = '2'; });
    const dimensions = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, page: document.documentElement.scrollWidth }));
    expect(dimensions.page).toBeLessThanOrEqual(dimensions.viewport + 1);

    await page.emulateMedia({ reducedMotion: 'reduce' });
    const duration = await page.locator('.sidebar-link').first().evaluate((element) => getComputedStyle(element).transitionDuration);
    expect(Math.max(...duration.split(',').map((value) => parseFloat(value)))).toBeLessThanOrEqual(0.001);
    await expect(page.getByRole('textbox', { name: 'Caption' })).toBeVisible();
  });
});
