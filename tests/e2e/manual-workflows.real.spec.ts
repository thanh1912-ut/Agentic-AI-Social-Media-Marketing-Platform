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

test('real mode: campaign → manual post → media → approval → export → metrics', async ({ page, request }) => {
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
  const mediaAltText = `Ảnh món ăn của ${runId}`;
  await page.getByLabel('Mô tả ảnh (alt text)').fill(mediaAltText);
  await page.getByLabel('Tải ảnh JPEG, PNG hoặc WebP').setInputFiles({
    name: `pilot-menu-${runId}.png`,
    mimeType: 'image/png',
    buffer: Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGNcp2XMwMDAxAAGAA0pAQ+YLm8TAAAAAElFTkSuQmCC',
      'base64',
    ),
  });
  await expect(page.getByText(`Mô tả: ${mediaAltText}`).first()).toBeVisible();
  await page.getByRole('button', { name: 'Lưu thành phiên bản mới' }).click();
  await expect(page.getByText(/Phiên bản 2 · cập nhật/)).toBeVisible();
  await page.getByRole('button', { name: 'Gửi duyệt bản 2' }).click();
  await expect(page.getByRole('button', { name: 'Duyệt bản 2' })).toBeVisible();
  await page.getByRole('button', { name: 'Duyệt bản 2' }).click();
  await expect(page.getByText('Đã duyệt', { exact: true })).toBeVisible();

  const postId = new URL(page.url()).pathname.split('/posts/')[1];
  const postResponse = await page.request.get(
    `${apiOrigin}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/posts/${encodeURIComponent(postId)}`,
  );
  expect(postResponse.ok()).toBeTruthy();
  const savedPost = await postResponse.json() as {
    version: number;
    current: { version: number; media: Array<{ filename?: string; sha256?: string; source: string }> };
  };
  expect(savedPost.version).toBe(2);
  const savedImage = savedPost.current.media.find((item) => item.source === 'uploaded');
  expect(savedImage?.filename).toBe(`pilot-menu-${runId}.png`);
  expect(savedImage?.sha256).toMatch(/^[a-f0-9]{64}$/);
  const approvalResponse = await page.request.get(
    `${apiOrigin}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/posts/${encodeURIComponent(postId)}/approvals`,
  );
  expect(approvalResponse.ok()).toBeTruthy();
  const approvals = await approvalResponse.json() as Array<{
    version: number;
    decision: string;
    content_sha256: string;
  }>;
  expect(approvals).toContainEqual(expect.objectContaining({ version: 2, decision: 'approved' }));
  expect(approvals.find((item) => item.version === 2)?.content_sha256).toMatch(/^[a-f0-9]{64}$/);

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

  await page.goto(`/w/${encodeURIComponent(workspaceId)}/analytics`);
  await expect(page.getByRole('heading', { name: 'Hiệu quả nội dung' })).toBeVisible();
  const sourceId = `pilot-page-${runId}`;
  await page.getByLabel('Mã nguồn / Facebook Page ID').fill(sourceId);
  await page.getByLabel('Lượt tiếp cận').fill('250');
  await page.getByLabel('Tương tác').fill('25');
  await page.getByRole('button', { name: 'Thêm bài vào snapshot' }).click();
  await expect(page.getByText(/Tiếp cận: 250 · tương tác: 25/)).toBeVisible();
  await page.getByRole('button', { name: 'Lưu 1 bài' }).click();
  await expect(page.getByRole('status')).toContainText('Đã lưu 1 dòng số liệu');
  await expect(page.getByRole('heading', { name: 'Báo cáo snapshot' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Đề xuất thử nghiệm' })).toBeVisible();
  await expect(page.getByText(/Chưa đủ bằng chứng/)).toBeVisible();

  const dashboardUrl = new URL(`${apiOrigin}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/analytics/dashboard`);
  dashboardUrl.searchParams.set('source_id', sourceId);
  const dashboardResponse = await page.request.get(dashboardUrl.toString());
  expect(dashboardResponse.ok()).toBeTruthy();
  const dashboard = await dashboardResponse.json() as {
    report: { observations: Array<{ metric: string; value: number | null; sample_size: number; coverage: number }> };
  };
  expect(dashboard.report.observations).toContainEqual(expect.objectContaining({
    metric: 'reach', value: 250, sample_size: 1, coverage: 1,
  }));
});
