import { expect, test, type Page } from '@playwright/test';

const apiOrigin = new URL(
  process.env.E2E_REAL_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? '',
).origin;

async function login(page: Page, email: string, password: string): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Mật khẩu').fill(password);
  await page.getByRole('button', { name: 'Đăng nhập' }).click();
  await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible();
}

test('real mode: campaign → manual post → approval → export and download', async ({ page, request }) => {
  const runId = `${Date.now()}-${Math.floor(Math.random() * 1_000_000)}`;
  const email = `pilot-${runId}@example.com`;
  const password = `Pilot-${runId}-safe-pass`;
  const registration = await request.post(`${apiOrigin}/api/v1/auth/register`, {
    data: {
      email,
      password,
      full_name: 'Pilot Owner',
      company_name: `Pilot Workspace ${runId}`,
    },
  });
  const registrationBody = await registration.text();
  expect(registration.status(), registrationBody).toBe(201);
  const session = JSON.parse(registrationBody) as { active_workspace_id: string };
  expect(session.active_workspace_id).toBeTruthy();
  const workspaceId = session.active_workspace_id;
  const campaignName = `Pilot campaign ${runId}`;

  await login(page, email, password);
  await page.goto(`/w/${encodeURIComponent(workspaceId)}/campaigns`);
  await page.getByLabel('Tên chiến dịch').fill(campaignName);
  await page.getByLabel('Thông điệp chính').fill('Ưu đãi cuối tuần cho khách hàng địa phương.');
  await page.getByLabel('Khán giả mục tiêu').fill('Khách hàng địa phương');
  await page.getByRole('button', { name: 'Tạo campaign' }).click();
  await expect(page.getByRole('heading', { name: campaignName })).toBeVisible();

  await page.getByRole('textbox', { name: 'Nội dung' }).fill('Thưởng thức món mới cùng gia đình vào cuối tuần này.');
  await page.getByLabel('Hashtag').fill('#pilot #weekend');
  await page.locator('form').filter({ has: page.getByRole('textbox', { name: 'Nội dung' }) })
    .getByRole('button', { name: 'Tạo bản nháp' }).click();
  await expect(page.getByRole('heading', { name: 'Biên tập bài viết' })).toBeVisible();
  await page.getByRole('button', { name: 'Gửi duyệt bản 1' }).click();
  await expect(page.getByRole('button', { name: 'Duyệt bản 1' })).toBeVisible();
  await page.getByRole('button', { name: 'Duyệt bản 1' }).click();
  await expect(page.getByText('Đã duyệt', { exact: true })).toBeVisible();

  const campaignUrl = new URL(page.url()).pathname.split('/posts/')[0];
  await page.goto(campaignUrl);
  await expect(page.getByRole('heading', { name: campaignName })).toBeVisible();
  await page.getByRole('button', { name: 'Tạo tệp xuất' }).click();
  await page.waitForURL(/\/jobs\//);
  await expect(page.getByText('Đã hoàn tất', { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/đã đăng/i)).toHaveCount(0);
  await expect(page.getByText('Mã tệp xuất')).toBeVisible();

  const downloadReady = page.waitForEvent('download');
  await page.getByRole('button', { name: /^Tải tệp/ }).click();
  const download = await downloadReady;
  expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
  expect(await download.failure()).toBeNull();
});
