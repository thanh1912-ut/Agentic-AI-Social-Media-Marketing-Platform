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

test.describe('lát cắt 2 — campaign và nội dung', () => {
  test('mở campaign và xem lịch nội dung', async ({ page }) => {
    await login(page);
    await page.getByRole('link', { name: 'Chiến dịch' }).click();
    await page.getByRole('link', { name: 'Mở chiến dịch' }).first().click();

    await expect(page.getByRole('heading', { name: 'Chiến dịch tháng 3 — Khách văn phòng' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Lịch nội dung' })).toBeVisible();
    await expect(page.getByText('Dữ liệu demo').first()).toBeVisible();
  });

  test('sửa bài tạo version mới rồi gửi duyệt đúng version', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/campaigns/cmp_khai_truong/posts/post_3');

    const caption = page.getByLabel('Caption');
    await expect(caption).toHaveValue(/Combo trưa 55.000đ/);
    await caption.fill('Combo trưa 55.000đ — bản đã chỉnh sửa để gửi duyệt lại.');
    await page.getByRole('button', { name: 'Lưu thành phiên bản mới' }).click();

    await expect(page.getByText('Bản 5 · Người dùng sửa')).toBeVisible();
    await expect(page.getByText(/Phải gửi duyệt lại đúng phiên bản 5/)).toBeVisible();
    await page.getByRole('button', { name: 'Gửi duyệt bản 5' }).click();
    await expect(page.getByRole('button', { name: 'Duyệt bản 5' })).toBeVisible();
  });

  test('tạo export đi qua job, không hiển thị là đã đăng', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/campaigns/cmp_khai_truong');
    await page.getByRole('button', { name: 'Tạo tệp xuất' }).click();
    await page.waitForURL(/\/jobs\/job_export_/);
    await expect(page.getByText(/Đang dựng tệp XLSX/)).toBeVisible();
    await expect(page.getByText(/đã đăng/i)).not.toBeVisible();
  });
});
