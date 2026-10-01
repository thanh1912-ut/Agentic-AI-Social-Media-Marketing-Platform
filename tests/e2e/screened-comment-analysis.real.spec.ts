import { expect, test } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';

// Real API/PG/Redis/Celery/native Gemini serialization, synthetic Meta + Gemini
// transport owned by the test. No live Facebook or Google request.
test('screened comments: review → durable analysis → citations → reload', async ({ page }) => {
  const credentialFile = process.env.E2E_SCREENED_COMMENT_CREDENTIAL_FILE;
  test.skip(!credentialFile, 'Requires a disposable Page and isolated synthetic provider worker.');
  const c = JSON.parse(readFileSync(credentialFile!, 'utf8')) as {
    email: string; password: string; workspace_id: string; source_id: string;
  };
  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill(c.email);
  await page.getByLabel('Mật khẩu', { exact: true }).fill(c.password);
  await page.getByRole('button', { name: /Đăng nhập$/ }).click();
  await expect(page.getByRole('button', { name: 'Đăng xuất', exact: true })).toBeVisible();
  await page.goto(`/w/${c.workspace_id}/research?tab=sources`);
  await page.getByRole('button', { name: 'Bài viết & bình luận', exact: true }).click();
  const accepted = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(`/sources/${c.source_id}/comments/crawl`));
  await page.getByRole('button', { name: /Thu thập bình luận và replies/ }).click();
  const crawl = await accepted;
  expect(crawl.status()).toBe(202);
  const { job_id: crawl_job_id } = await crawl.json() as { job_id: string };
  const api = process.env.E2E_REAL_API_BASE_URL!;
  await expect.poll(async () => (await (await page.request.get(`${api}/api/v1/jobs/${crawl_job_id}`)).json()).status,
    { timeout: 40_000 }).toBe('succeeded');
  await page.getByRole('button', { name: 'Xem bình luận và tương tác', exact: true }).click();
  await expect(page.getByText('Synthetic reply', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Rà soát để phân tích bằng Gemini', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Chọn đoạn 1', exact: true }).check();
  await page.getByRole('textbox', { name: /Bản kiểm tra đoạn 1/ }).fill('Reviewed synthetic question');
  await page.getByRole('textbox', { name: /Tham chiếu đánh giá xử lý và gửi dữ liệu/ }).fill('Synthetic fixture only; no personal data; transfer test');
  const received = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(`/sources/${c.source_id}/comment-analyses`));
  await page.getByRole('button', { name: /Phân tích bản đã kiểm tra$/ }).click();
  const response = await received;
  expect(response.status()).toBe(202);
  const { job_id } = await response.json() as { job_id: string };
  await expect.poll(async () => (await (await page.request.get(`${api}/api/v1/jobs/${job_id}`)).json()).status,
    { timeout: 40_000 }).toBe('succeeded');
  await expect(page.getByText('Người đọc muốn biết cách dùng sản phẩm.', { exact: true })).toBeVisible({ timeout: 20_000 });
  await page.getByText('Đoạn đã dùng', { exact: true }).click();
  await expect(page.getByText(/Reviewed synthetic question · Bản Owner đã sửa/)).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: 'Bài viết & bình luận', exact: true }).click();
  await page.getByRole('button', { name: 'Xem bình luận và tương tác', exact: true }).click();
  await page.getByRole('button', { name: 'Rà soát để phân tích bằng Gemini', exact: true }).click();
  await expect(page.getByText('Người đọc muốn biết cách dùng sản phẩm.', { exact: true })).toBeVisible();
  const job = await (await page.request.get(`${api}/api/v1/jobs/${job_id}`)).json();
  let report_job_id: string | undefined, report_id: string | undefined, campaign_id: string | undefined;
  if (process.env.E2E_COMMENT_REPORT === '1') {
    report_job_id = job.result?.report_job_id;
    expect(report_job_id).toBeTruthy();
    await expect.poll(async () => (await (await page.request.get(`${api}/api/v1/jobs/${report_job_id}`)).json()).status,
      { timeout: 40_000 }).toBe('succeeded');
    const reportJob = await (await page.request.get(`${api}/api/v1/jobs/${report_job_id}`)).json();
    report_id = reportJob.result?.report_id;
    expect(report_id).toBeTruthy();
    await expect(page.getByRole('link', { name: 'Xem báo cáo và chọn hướng viết' })).toBeVisible({ timeout: 20_000 });
    await page.getByRole('link', { name: 'Xem báo cáo và chọn hướng viết' }).click();
    await expect(page.getByRole('heading', { name: 'Hướng viết từ câu hỏi đã chọn', exact: true })).toBeVisible();
    await expect(page.getByText('1 lô bình luận đã kiểm tra', { exact: false }).first()).toBeVisible();
    const selected = page.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(`/reports/${report_id}/draft`));
    await page.getByRole('button', { name: 'Tạo chiến dịch nháp', exact: true }).click();
    const created = await selected;
    expect(created.status()).toBe(201);
    campaign_id = (await created.json()).campaign_id;
    await page.getByRole('link', { name: 'Mở chiến dịch để xem lại và yêu cầu AI sinh bài' }).click();
    await expect(page.getByRole('heading', { name: 'Hướng dẫn bắt đầu', exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Nguồn của hướng viết đã chọn' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Xem báo cáo đã chọn' })).toHaveAttribute('href', `/w/${c.workspace_id}/research?tab=reports#research-report-${report_id}`);
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Hướng dẫn bắt đầu', exact: true })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Nguồn của hướng viết đã chọn' })).toContainText('1 lô bình luận đã kiểm tra');
  }
  if (process.env.E2E_SCREENED_COMMENT_SCREENSHOT) await page.screenshot({ path: process.env.E2E_SCREENED_COMMENT_SCREENSHOT, fullPage: true });
  if (process.env.E2E_SCREENED_COMMENT_RESULT_FILE) writeFileSync(process.env.E2E_SCREENED_COMMENT_RESULT_FILE, JSON.stringify({
    fixture_only: true, workspace_id: c.workspace_id, source_id: c.source_id, crawl_job_id, job_id,
    batch_id: job.result?.batch_id, report_job_id, report_id, campaign_id, native_gemini_mock_transport: true, live_provider_calls: 0,
    reload_verified: true, selected_comments: 1, unselected_comments_sent: false,
  }, null, 2));
});
