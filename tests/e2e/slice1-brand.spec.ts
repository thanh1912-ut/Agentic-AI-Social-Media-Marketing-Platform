import { expect, test } from '@playwright/test';

/**
 * E2E lát cắt 1: đăng nhập → chọn doanh nghiệp → xem hồ sơ thương hiệu → tài liệu
 * → tiến độ tác vụ.
 *
 * Chạy trên dữ liệu demo (MSW) nên không cần backend.
 */

const OWNER = { email: 'chu.quan@phobac.vn', password: 'demo1234' };

async function login(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(OWNER.email);
  await page.getByLabel('Mật khẩu').fill(OWNER.password);
  await page.getByRole('button', { name: 'Đăng nhập' }).click();
  await page.waitForURL(/\/w\//, { timeout: 20_000 });
}

test.describe('lát cắt 1 — hồ sơ thương hiệu', () => {
  test('đăng nhập và vào được khu vực làm việc', async ({ page }) => {
    await login(page);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  });

  test('sai mật khẩu thì báo lỗi tiếng Việt, không vào được', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(OWNER.email);
    await page.getByLabel('Mật khẩu').fill('sai-mat-khau');
    await page.getByRole('button', { name: 'Đăng nhập' }).click();

    const alert = page.getByRole('alert');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText('không đúng');
    await expect(page).toHaveURL(/\/login/);
  });

  test('mọi màn hình đều có nhãn dữ liệu demo', async ({ page }) => {
    await login(page);
    // Dữ liệu demo KHÔNG được giả thành dữ liệu thật.
    await expect(page.getByText('Dữ liệu demo').first()).toBeVisible();
  });

  test('tài liệu lỗi phải nói rõ lý do và việc cần làm', async ({ page }) => {
    await login(page);
    await page.getByRole('link', { name: 'Tài liệu' }).click();
    await page.waitForURL(/\/documents/);

    // Tệp scan thiếu lớp văn bản — phải hiện lý do, không chỉ "lỗi".
    await expect(page.getByText('không có lớp văn bản để đọc')).toBeVisible();
    await expect(page.getByText('xuất lại từ Word')).toBeVisible();
  });

  test('hồ sơ thương hiệu cho xem nguồn trích xuất', async ({ page }) => {
    await login(page);
    await page.getByRole('link', { name: 'Hồ sơ thương hiệu' }).click();
    await page.waitForURL(/\/brand/);

    // Bằng chứng cho thông tin AI trích xuất phải truy cập được.
    const sourceToggle = page.getByRole('button', { name: /Xem nguồn/i }).first();
    await expect(sourceToggle).toBeVisible();
    await sourceToggle.click();
    await expect(page.locator('blockquote').first()).toBeVisible();
  });

  test('trường mâu thuẫn cho người dùng chọn, không tự quyết', async ({ page }) => {
    await login(page);
    await page.goto(page.url().replace(/\/$/, '') + '/brand');

    await expect(page.getByText(/mâu thuẫn/i).first()).toBeVisible();
    // Phải có lựa chọn cho người dùng, không im lặng lấy một giá trị.
    await expect(page.getByRole('radio').first()).toBeVisible();
  });

  test('tiến độ tác vụ không bịa phần trăm', async ({ page }) => {
    await login(page);
    await page.goto(page.url().replace(/\/$/, '') + '/documents');

    await page.getByRole('link', { name: /Đọc lại tài liệu/ }).first().click();
    await page.waitForURL(/\/jobs\//);

    // Hoặc có phần trăm thật (có aria-valuenow), hoặc thanh không xác định.
    const progress = page.getByRole('progressbar').first();
    await expect(progress).toBeVisible();

    const label = (await progress.getAttribute('aria-label')) ?? '';
    const valueNow = await progress.getAttribute('aria-valuenow');
    if (valueNow === null) {
      expect(label).toContain('chưa xác định được tổng khối lượng');
    }
  });
});

test.describe('trạng thái rỗng', () => {
  test('doanh nghiệp chưa có dữ liệu thì hiện trạng thái rỗng, không trắng trang', async ({
    page,
  }) => {
    await login(page);
    // Chuyển sang doanh nghiệp mới tạo (chưa có tài liệu nào).
    await page.goto('/w/ws_tap_hoa_an/documents');
    await expect(page.getByText(/Chưa có tài liệu nào/)).toBeVisible();
  });
});
