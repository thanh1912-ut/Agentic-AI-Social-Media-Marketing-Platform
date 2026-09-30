import { expect, test } from '@playwright/test';
import { readFileSync, writeFileSync } from 'node:fs';

// Real application/PostgreSQL/Redis. Collector responses are synthetic and
// explicitly labeled; this test is not live Facebook acceptance.
test('public Page fixture: UI crawl → Redis worker → saved comment counts → reload', async ({ page }) => {
  const credentialFile = process.env.E2E_PUBLIC_COMMENT_CREDENTIAL_FILE;
  test.skip(!credentialFile, 'Provide credentials for an isolated synthetic Page workspace.');
  const credentials = JSON.parse(readFileSync(credentialFile!, 'utf8')) as {
    email: string; password: string; workspace_id: string; source_id: string;
  };
  await page.goto('/login');
  await page.getByLabel('Email', { exact: true }).fill(credentials.email);
  await page.getByLabel('Mật khẩu', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Đăng xuất', exact: true })).toBeVisible();
  await page.goto(`/w/${credentials.workspace_id}/research?tab=sources`);
  await expect(page.getByText('Synthetic public Page - browser fixture', { exact: true })).toBeVisible();
  const accepted = page.waitForResponse((response) => response.request().method() === 'POST'
    && response.url().endsWith(`/sources/${credentials.source_id}/crawl`));
  await page.getByRole('tabpanel', { name: 'Thu thập', exact: true }).getByRole('button', { name: 'Crawl ngay', exact: true }).click();
  const response = await accepted;
  expect(response.status()).toBe(202);
  const { job_id } = await response.json() as { job_id: string };
  await expect(page.getByText('Synthetic public Page content', { exact: true }).first()).toBeVisible({ timeout: 40_000 });
  await expect(page.getByText(/Job succeeded/)).toBeVisible({ timeout: 40_000 });
  await page.getByRole('button', { name: 'Xem bình luận và tương tác', exact: true }).first().click();
  await expect(page.getByText('Câu hỏi khác', { exact: true })).toBeVisible();
  await expect(page.getByText('Like: 2', { exact: true })).toBeVisible();
  await expect(page.getByText('Reactions: 9', { exact: true })).toHaveCount(2);
  await expect(page.getByText(/Đã nhận 2 bình luận.*nguồn công bố 200/)).toBeVisible();
  await expect(page.getByText(/Chưa xác minh đầy đủ lịch sử/)).toBeVisible();
  await expect(page.getByText(/user_name01/)).toHaveCount(2);
  await expect(page.getByText('0901 234 567', { exact: false })).toHaveCount(0);
  await expect(page.getByText('person@example.invalid', { exact: false })).toHaveCount(0);
  await page.reload();
  await page.getByRole('button', { name: 'Bài viết & lịch sử', exact: true }).click();
  await page.getByRole('button', { name: 'Xem bình luận và tương tác', exact: true }).first().click();
  await expect(page.getByText('Câu hỏi khác', { exact: true })).toBeVisible();
  await expect(page.getByText('Like: 2', { exact: true })).toBeVisible();
  if (process.env.E2E_PUBLIC_COMMENT_SCREENSHOT) {
    await page.screenshot({ path: process.env.E2E_PUBLIC_COMMENT_SCREENSHOT, fullPage: true });
  }
  if (process.env.E2E_PUBLIC_COMMENT_RESULT_FILE) {
    writeFileSync(process.env.E2E_PUBLIC_COMMENT_RESULT_FILE, JSON.stringify({
      fixture_only: true, job_id, workspace_id: credentials.workspace_id, source_id: credentials.source_id,
      comment_rows: 2, reload_verified: true, real_api: true, provider_calls: 0,
    }, null, 2));
  }
});
