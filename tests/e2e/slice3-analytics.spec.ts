import { expect, test } from '@playwright/test';

const OWNER = { email: 'chu.quan@phobac.vn', password: 'demo1234' };

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(OWNER.email);
  await page.getByLabel('Mật khẩu').fill(OWNER.password);
  await page.getByRole('button', { name: 'Đăng nhập' }).click();
  await page.waitForURL((url) => url.pathname === '/' || url.pathname.startsWith('/w/'), {
    timeout: 20_000,
  });
  if (new URL(page.url()).pathname === '/') {
    await page.getByRole('button', { name: 'Tiếp tục tới tài liệu' }).click();
  }
  await page.waitForURL(/\/w\//, { timeout: 20_000 });
}

test('mở dashboard số liệu và nhập snapshot demo có gắn nguồn', async ({ page }) => {
  await login(page);
  await page.getByRole('link', { name: 'Hiệu quả' }).click();
  await page.waitForURL(/\/analytics$/);
  await expect(page.getByRole('heading', { name: 'Hiệu quả nội dung' })).toBeVisible();
  await expect(page.locator('select option').nth(1)).toBeAttached();

  await page.getByLabel('Mã nguồn / Facebook Page ID').fill('demo-page-pho-bac');
  await page.getByLabel('Tương tác').fill('25');
  await page.getByLabel('Lượt tiếp cận').fill('250');
  await page.getByRole('button', { name: 'Thêm bài vào snapshot' }).click();
  await page.getByRole('button', { name: 'Lưu 1 bài' }).click();

  await expect(page.getByRole('status')).toContainText('Đã lưu 1 dòng số liệu');
  await expect(page.getByRole('heading', { name: 'Báo cáo snapshot' })).toBeVisible();
  await expect(page.getByText('Dữ liệu minh họa — không phải kết quả thật.')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Đề xuất thử nghiệm' })).toBeVisible();
  await expect(page.getByText(/Chưa đủ bằng chứng/)).toBeVisible();
});
