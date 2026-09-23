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
  await page.waitForURL((url) => url.pathname === '/' || url.pathname.startsWith('/w/'), {
    timeout: 20_000,
  });
  if (new URL(page.url()).pathname === '/') {
    await page.getByRole('button', { name: 'Tiếp tục tới tài liệu' }).click();
  }
  await page.waitForURL(/\/w\//, { timeout: 20_000 });
}

test.describe('lát cắt 1 — hồ sơ thương hiệu', () => {
  test('đăng nhập và vào được khu vực làm việc', async ({ page }) => {
    await login(page);
    await expect(page.getByRole('heading', { name: 'Tài liệu', exact: true })).toBeVisible();
  });

  test('sai mật khẩu thì báo lỗi tiếng Việt, không vào được', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(OWNER.email);
    await page.getByLabel('Mật khẩu').fill('sai-mat-khau');
    await page.getByRole('button', { name: 'Đăng nhập' }).click();

    // Dùng đúng id của khối lỗi: `getByRole('alert')` khớp cả
    // `#__next-route-announcer__` do Next.js tự chèn.
    const alert = page.locator('#login-error');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText('không đúng');
    await expect(page).toHaveURL(/\/login/);
  });

  test('mọi màn hình đều có nhãn dữ liệu demo', async ({ page }) => {
    await login(page);
    // Dữ liệu demo KHÔNG được giả thành dữ liệu thật.
    await expect(page.getByText('Bản demo').first()).toBeVisible();
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

  test('sửa và xác nhận gửi cùng revision qua mock HTTP contract', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/brand');
    await expect(page.getByRole('heading', { name: 'Hồ sơ thương hiệu' })).toBeVisible();

    const revisedName = 'Quán Phở Bắc Cô Hương — đã xác nhận';
    await page.getByLabel(/Sửa.*Tên doanh nghiệp/).fill(revisedName);
    await page.getByRole('button', { name: 'Xác nhận hồ sơ' }).click();

    await expect(page.getByText('Đã lưu và xác nhận hồ sơ thương hiệu.')).toBeVisible();
    await expect(page.getByText('Hồ sơ đã xác nhận')).toBeVisible();
    await expect(page.getByLabel(/Sửa.*Tên doanh nghiệp/)).toHaveValue(revisedName);
  });

  test('lời mời chưa có tài khoản không làm màn hình thành viên bị crash', async ({ page }) => {
    await login(page);
    await page.getByRole('link', { name: 'Cài đặt' }).click();
    await page.waitForURL(/\/settings/);

    await expect(page.getByText('Lời mời đang chờ')).toBeVisible();
    await expect(page.getByText('moi-moi@pho-bac.vn')).toBeVisible();
  });

  test('trường mâu thuẫn cho người dùng chọn, không tự quyết', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/brand');

    await expect(page.getByText(/mâu thuẫn/i).first()).toBeVisible();
    // Phải có lựa chọn cho người dùng, không im lặng lấy một giá trị.
    await expect(page.getByRole('radio').first()).toBeVisible();
  });

  test('409 version conflict yêu cầu tải bản mới, không tự gửi lại', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/brand');
    await expect(page.getByRole('heading', { name: 'Hồ sơ thương hiệu' })).toBeVisible();
    await page.evaluate(async () => {
      const endpoint = '/api/v1/workspaces/ws_pho_bac/brand-profile';
      const getResponse = await fetch(endpoint);
      const payload: unknown = await getResponse.json();
      if (typeof payload !== 'object' || payload === null || !('version' in payload)) {
        throw new Error('Mock Brand Profile did not return a revision.');
      }
      const version = payload.version;
      if (typeof version !== 'number') throw new Error('Mock revision is not numeric.');
      const updateResponse = await fetch(endpoint, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version, fields: [], confirm: false }),
      });
      if (!updateResponse.ok) throw new Error('Could not advance the mock revision.');
    });

    await page.getByLabel(/Sửa.*Tên doanh nghiệp/).fill('Tên đang sửa ở tab cũ');
    await page.getByRole('button', { name: 'Lưu thay đổi' }).click();
    await expect(page.getByText(/Nội dung này vừa được người khác cập nhật/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Tải bản mới nhất' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Thử lại' })).toHaveCount(0);
  });

  test('tiến độ tác vụ không bịa phần trăm', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/documents');
    await expect(page.getByText('Đã đọc xong nội dung').first()).toBeVisible();
    await expect(page.getByText('Đã tạo/cập nhật Brand Profile').first()).toBeVisible();
    await expect(page.getByText('Truy xuất từ khóa (lexical)').first()).toBeVisible();

    // "Đọc lại tài liệu" là BUTTON (gọi POST reprocess rồi mới chuyển trang),
    // không phải link.
    await page.getByRole('button', { name: /Đọc lại tài liệu/ }).first().click();
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
