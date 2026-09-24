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

  test('sửa brief bằng optimistic version và hiển thị bản mới', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/campaigns/cmp_khai_truong');
    const versionLabel = page.locator('header').getByText(/phiên bản \d+/);
    const initialVersionText = await versionLabel.textContent();
    const initialVersion = Number(initialVersionText?.match(/phiên bản (\d+)/)?.[1]);
    expect(Number.isInteger(initialVersion)).toBeTruthy();

    await page.getByRole('button', { name: 'Chỉnh sửa brief' }).click();
    await page.getByLabel('Thông điệp chính').fill('Bữa trưa gọn ngon, đủ vị cho ngày bận rộn.');
    await page.getByRole('button', { name: /Lưu brief/ }).click();

    await expect(page.getByText('Bữa trưa gọn ngon, đủ vị cho ngày bận rộn.')).toBeVisible();
    await expect(versionLabel).toHaveText(new RegExp(`phiên bản ${initialVersion + 1}`));
    await expect(page.getByRole('button', { name: 'Chỉnh sửa brief' })).toBeVisible();
  });

  test('sửa strategy và slot rồi sinh bài đúng chủ đề slot', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/campaigns/cmp_khai_truong');
    await expect(page.getByText(/Nhấn vào bữa trưa nhanh gọn/)).toBeVisible();

    await page.getByRole('button', { name: 'Chỉnh sửa brief' }).click();
    await page.getByLabel('Chiến lược nội dung').fill('Ưu tiên bữa trưa văn phòng, nêu rõ giá và thời gian phục vụ.');
    await page.locator('#slot-topic-slot-trua-1').fill('Combo phở nóng cho giờ nghỉ trưa');
    await page.getByRole('button', { name: /Lưu brief/ }).click();

    await expect(page.getByText('Ưu tiên bữa trưa văn phòng, nêu rõ giá và thời gian phục vụ.')).toBeVisible();
    await expect(page.getByText('Combo phở nóng cho giờ nghỉ trưa')).toBeVisible();
    await page.getByRole('button', { name: 'Sinh bài theo slot' }).first().click();
    await page.waitForURL(/\/jobs\/job_content_generate_/);
    await expect(page.getByRole('heading', { name: 'Đang tạo bản nháp: Combo phở nóng cho giờ nghỉ trưa' })).toBeVisible();
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

  test('upload ảnh, preview và gỡ ảnh bằng các phiên bản riêng', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/campaigns/cmp_khai_truong/posts/post_2');
    const versionLabel = page.locator('header').getByText(/Phiên bản \d+/);
    const initialVersion = Number((await versionLabel.textContent())?.match(/Phiên bản (\d+)/)?.[1]);
    expect(Number.isInteger(initialVersion)).toBeTruthy();

    const altText = 'Tô phở nóng với rau thơm trên bàn gỗ';
    await page.getByLabel('Mô tả ảnh (alt text)').fill(altText);
    await page.getByLabel('Tải ảnh JPEG, PNG hoặc WebP').setInputFiles({
      name: 'pho-nong.png',
      mimeType: 'image/png',
      buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/wv8AAAAASUVORK5CYII=', 'base64'),
    });
    await expect(page.getByText(`Mô tả: ${altText}`).first()).toBeVisible();
    await expect(page.getByText(/Thay đổi ảnh chưa lưu/)).toBeVisible();
    await page.getByRole('button', { name: 'Lưu thành phiên bản mới' }).click();
    await expect(versionLabel).toHaveText(new RegExp(`Phiên bản ${initialVersion + 1}`));
    await expect(page.getByText(`Mô tả: ${altText}`).first()).toBeVisible();

    await page.getByRole('button', { name: 'Gỡ khỏi bản nháp' }).click();
    await expect(page.getByText('Phiên bản này chưa có ảnh đính kèm.')).toBeVisible();
    await page.getByRole('button', { name: 'Lưu thành phiên bản mới' }).click();
    await expect(versionLabel).toHaveText(new RegExp(`Phiên bản ${initialVersion + 2}`));
  });

  test('AI revise tạo version demo mới rồi quay lại trạng thái draft', async ({ page }) => {
    await login(page);
    await page.goto('/w/ws_pho_bac/campaigns/cmp_khai_truong/posts/post_2');

    await page.getByLabel('Bạn muốn sửa thế nào?').fill('Viết ngắn gọn hơn, giữ nguyên thông tin và hashtag.');
    await page.getByLabel('Phạm vi sửa').selectOption('caption');
    await page.getByRole('button', { name: 'Tạo phiên bản AI sửa' }).click();

    await expect(page.getByText(/AI demo đã tạo phiên bản mới/)).toBeVisible();
    await expect(page.getByText(/Bản 3 · AI sửa/)).toBeVisible();
    await expect(page.getByRole('textbox', { name: 'Caption' })).toHaveValue(/Bản AI demo/);
    await expect(page.getByText('Dữ liệu demo').first()).toBeVisible();
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
