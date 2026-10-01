import { expect, test } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';

// Real API/PostgreSQL/Redis/Celery; preseeded post and synthetic Meta adapter.
// This does not prove live Page access or a complete 90-day backfill.
test('owned Page fixture: manual comments → Redis worker → replies → reload', async ({ page }) => {
  const credentialFile = process.env.E2E_OWNED_COMMENT_CREDENTIAL_FILE;
  test.skip(!credentialFile, 'Requires an isolated owned Page and synthetic Meta collector.');
  const credentials = JSON.parse(readFileSync(credentialFile!, 'utf8')) as {
    email: string; password: string; workspace_id: string; source_id: string;
  };
  let crawlRequests = 0;
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith(`/sources/${credentials.source_id}/comments/crawl`)) crawlRequests++;
  });
  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill(credentials.email);
  await page.getByLabel('Mật khẩu', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Đăng xuất', exact: true })).toBeVisible();
  await page.goto(`/w/${credentials.workspace_id}/research?tab=sources`);
  await expect(page.getByText('Synthetic owned Page - browser fixture', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Bài viết & bình luận', exact: true }).click();
  await expect(page.getByText('Synthetic company post', { exact: true })).toBeVisible();
  const button = page.getByRole('button', { name: /Thu thập bình luận và replies/ });
  await expect(button).toBeEnabled();
  expect(crawlRequests).toBe(0);
  const accepted = page.waitForResponse((r) => r.request().method() === 'POST'
    && r.url().endsWith(`/sources/${credentials.source_id}/comments/crawl`));
  await button.click();
  const response = await accepted;
  expect(response.status()).toBe(202);
  const { job_id } = await response.json() as { job_id: string };
  expect(crawlRequests).toBe(1);
  await expect.poll(async () => {
    const job = await page.request.get(`${process.env.E2E_REAL_API_BASE_URL}/api/v1/jobs/${job_id}`);
    expect(job.status()).toBe(200);
    return (await job.json()).status;
  }, { timeout: 40_000 }).toBe('succeeded');
  await page.getByRole('button', { name: 'Xem bình luận và tương tác', exact: true }).click();
  await expect(page.getByText('Synthetic reply', { exact: true })).toBeVisible();
  await expect(page.getByText('Like: 0', { exact: true })).toBeVisible();
  await expect(page.getByText('Like: 4', { exact: true })).toBeVisible();
  await expect(page.getByText('Reactions: Chưa có dữ liệu', { exact: true })).toHaveCount(3);
  await expect(page.getByRole('link', { name: 'Phản hồi cho bình luận đã lưu' })).toBeVisible();
  await expect(page.getByText(/0901 234 567/)).toHaveCount(0);
  await page.reload();
  await page.getByRole('button', { name: 'Bài viết & bình luận', exact: true }).click();
  await page.getByRole('button', { name: 'Xem bình luận và tương tác', exact: true }).click();
  await expect(page.getByText('Synthetic reply', { exact: true })).toBeVisible();
  await expect(page.getByText(/Đã nhận 3 bình luận và replies; 2 bình luận gốc.*nguồn công bố 2 ở luồng bình luận gốc/)).toBeVisible();
  await expect(page.getByText(/bình luận ẩn\/xóa có thể không được Meta trả về/)).toBeVisible();
  expect(crawlRequests).toBe(1);
  if (process.env.E2E_OWNED_COMMENT_SCREENSHOT) {
    await page.screenshot({ path: process.env.E2E_OWNED_COMMENT_SCREENSHOT, fullPage: true });
  }
  if (process.env.E2E_OWNED_COMMENT_RESULT_FILE) {
    writeFileSync(process.env.E2E_OWNED_COMMENT_RESULT_FILE, JSON.stringify({ fixture_only: true,
      preseeded_post: true, job_id, workspace_id: credentials.workspace_id, source_id: credentials.source_id,
      comments_and_replies: 3, root_comments: 2, provider_calls: 0, reload_verified: true,
      real_api: true, no_automatic_crawl_on_open: true }, null, 2));
  }
});
