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
  await expect(page.getByText('Dữ liệu minh họa — không phải kết quả thật.', { exact: false }).first()).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Đề xuất thử nghiệm' })).toBeVisible();
  await expect(page.getByText(/Chưa đủ bằng chứng/)).toBeVisible();
});

test('ghi feedback và áp dụng recommendation thành brief revision cần owner duyệt', async ({ page }) => {
  await login(page);
  await page.getByRole('link', { name: 'Hiệu quả' }).click();
  await page.waitForURL(/\/analytics$/);
  await page.getByLabel('Mã nguồn / Facebook Page ID').fill('demo-source-eligible');
  await expect(page.getByText('Có đề xuất')).toBeVisible();
  await page.getByRole('button', { name: 'Lưu đề xuất có bằng chứng' }).click();
  await expect(page.getByText('Trạng thái xử lý:')).toContainText('new');
  await page.getByRole('button', { name: 'Hữu ích', exact: true }).click();
  await expect(page.getByText('Trạng thái xử lý:')).toContainText('acknowledged');
  await page.getByRole('button', { name: 'Tạo brief revision để xem lại' }).click();
  await expect(page.getByText('Campaign chỉ đổi sau khi chấp nhận.')).toBeVisible();
  await expect(page.getByText(/Bản nháp brief · phiên bản gốc/)).toBeVisible();
  await page.getByRole('button', { name: 'Chấp nhận revision' }).click();
  await expect(page.getByText('Trạng thái bản nháp:')).toContainText('accepted');
  await expect(page.getByText('Dữ liệu minh họa — không phải kết quả thật.', { exact: false }).first()).toBeVisible();

  await expect(page.getByRole('heading', { name: 'Theo dõi kết quả recommendation' })).toBeVisible();
  await page.getByLabel('Bắt đầu baseline').fill('2026-09-01T00:00');
  await page.getByLabel('Kết thúc baseline').fill('2026-09-07T23:59');
  await page.getByLabel('Bắt đầu follow-up').fill('2026-09-08T00:00');
  await page.getByLabel('Kết thúc follow-up').fill('2026-09-15T23:59');
  await page.getByRole('button', { name: 'Ghi nhận kết quả' }).click();
  await expect(page.getByRole('heading', { name: 'Outcomes đã lưu' })).toBeVisible();
  await expect(page.getByText(/So sánh mô tả không chứng minh recommendation gây ra thay đổi/)).toBeVisible();
});
