import { expect, test, type Page } from '@playwright/test';

const apiOrigin = new URL(
  process.env.E2E_REAL_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? '',
).origin;
const email = process.env.E2E_REAL_EMAIL ?? '';
const password = process.env.E2E_REAL_PASSWORD ?? '';
const workspaceId = process.env.E2E_REAL_WORKSPACE_ID ?? '';

function requireRealAccount(): void {
  test.skip(
    email === '' || password === '' || workspaceId === '',
    'Set E2E_REAL_EMAIL, E2E_REAL_PASSWORD and E2E_REAL_WORKSPACE_ID for a provisioned API test account.',
  );
}

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Mật khẩu').fill(password);
  await page.getByRole('button', { name: 'Đăng nhập' }).click();
  await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible();
}

async function chooseWorkspace(page: Page, id: string): Promise<boolean> {
  await page.goto('/');
  const chooserHeading = page.getByRole('heading', { name: 'Chọn doanh nghiệp' });
  const explicitSelection = await chooserHeading.isVisible().catch(() => false);
  if (explicitSelection) {
    await page.locator(`input[name="workspace"][value="${id}"]`).check();
    await page.getByRole('button', { name: 'Tiếp tục tới tài liệu' }).click();
  }
  await page.waitForURL((url) => url.pathname === `/w/${id}/documents`);
  return explicitSelection;
}

function onePageTextPdf(text: string): Buffer {
  const pdfText = text.replaceAll('\\', '\\\\').replaceAll('(', '\\(').replaceAll(')', '\\)');
  const stream = `BT /F1 12 Tf 72 720 Td (${pdfText}) Tj ET`;
  const objects = [
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    `<< /Length ${Buffer.byteLength(stream, 'ascii')} >>\nstream\n${stream}\nendstream`,
  ];

  let document = '%PDF-1.4\n';
  const offsets: number[] = [0];
  for (const [index, object] of objects.entries()) {
    offsets.push(Buffer.byteLength(document, 'ascii'));
    document += `${index + 1} 0 obj\n${object}\nendobj\n`;
  }
  const xrefOffset = Buffer.byteLength(document, 'ascii');
  document += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (const offset of offsets.slice(1)) {
    document += `${offset.toString().padStart(10, '0')} 00000 n \n`;
  }
  document += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return Buffer.from(document, 'ascii');
}

test.describe('real API acceptance — auth, documents, jobs and Brand Profile', () => {
  test('removes a stale mock service worker before showing real-mode login', async ({ page }) => {
    await page.goto('/login');
    await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return;
      await navigator.serviceWorker.register('/mockServiceWorker.js');
      await navigator.serviceWorker.ready;
    });

    // The real-mode shell may immediately reload once more after it unregisters
    // the stale worker. Wait only for the navigation commit, then assert the UI
    // and service-worker state after the app's own cleanup/reload settles.
    await page.reload({ waitUntil: 'commit' });
    await expect(page.getByRole('heading', { name: 'Đăng nhập' })).toBeVisible();
    const staleWorkerState = await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return { registrations: 0, controlledByMock: false };
      const registrations = await navigator.serviceWorker.getRegistrations();
      const workerScripts = registrations.flatMap((registration) =>
        [registration.active, registration.waiting, registration.installing]
          .filter((worker): worker is ServiceWorker => worker !== null)
          .map((worker) => worker.scriptURL),
      );
      return {
        registrations: workerScripts.filter((url) => url.includes('/mockServiceWorker.js')).length,
        controlledByMock:
          navigator.serviceWorker.controller?.scriptURL.includes('/mockServiceWorker.js') ?? false,
      };
    });
    expect(staleWorkerState).toEqual({ registrations: 0, controlledByMock: false });
  });

  test('login → upload TXT/PDF → job → inspect AI sources → confirm → reload persisted profile', async ({
    page,
  }) => {
    requireRealAccount();
    const uploadRunId = Date.now();
    const txtFilename = `pilot-brand-notes-${uploadRunId}.txt`;
    const pdfFilename = `pilot-menu-text-${uploadRunId}.pdf`;
    const apiRequests: string[] = [];
    let uploadCsrfHeader: string | undefined;
    const brandMutations: Array<{ method: string; body: unknown }> = [];
    page.on('request', (request) => {
      const requestUrl = new URL(request.url());
      if (requestUrl.pathname.startsWith('/api/v1/')) apiRequests.push(request.url());
      if (
        requestUrl.pathname === `/api/v1/workspaces/${workspaceId}/documents` &&
        request.method() === 'POST'
      ) {
        uploadCsrfHeader = request.headers()['x-csrf-token'];
      }
      if (
        requestUrl.pathname === `/api/v1/workspaces/${workspaceId}/brand-profile` &&
        request.method() === 'PATCH'
      ) {
        let body: unknown = null;
        try {
          body = request.postData() ? JSON.parse(request.postData() ?? 'null') : null;
        } catch {
          body = null;
        }
        brandMutations.push({ method: request.method(), body });
      }
      if (
        requestUrl.pathname === `/api/v1/workspaces/${workspaceId}/brand-profile/confirm` &&
        request.method() === 'POST'
      ) {
        let body: unknown = null;
        try {
          body = request.postData() ? JSON.parse(request.postData() ?? 'null') : null;
        } catch {
          body = null;
        }
        brandMutations.push({ method: request.method(), body });
      }
    });

    await login(page);
    const explicitWorkspaceSelection = await chooseWorkspace(page, workspaceId);
    await page.goto(`/w/${encodeURIComponent(workspaceId)}/documents`);
    await expect(page.getByRole('heading', { name: 'Tài liệu' })).toBeVisible();

    await page.locator('#document-files').setInputFiles([
      {
        name: txtFilename,
        mimeType: 'text/plain',
        buffer: Buffer.from(`Pho Bac ${uploadRunId} serves northern Vietnamese noodle soup. Friendly neighborhood voice.`, 'utf8'),
      },
      {
        name: pdfFilename,
        mimeType: 'application/pdf',
        buffer: onePageTextPdf(`Pho Bac ${uploadRunId} menu. Beef noodle soup. Open daily.`),
      },
    ]);

    await expect(page).toHaveURL(/\/jobs\//, { timeout: 30_000 });
    const jobUrl = page.url();
    await expect(page.getByText('Đã hoàn tất', { exact: true })).toBeVisible({ timeout: 90_000 });
    await page.reload();
    await expect(page.getByText('Đã hoàn tất', { exact: true })).toBeVisible({ timeout: 30_000 });

    await page.goto(`/w/${encodeURIComponent(workspaceId)}/documents`);
    await expect(page.getByText(txtFilename)).toBeVisible();
    await expect(page.getByText(pdfFilename)).toBeVisible();
    await expect(page.getByText('Đã đọc xong nội dung').first()).toBeVisible();
    await expect(page.getByText('Đã tạo/cập nhật Brand Profile').first()).toBeVisible();
    await expect(page.getByText('Mode truy xuất').first()).toBeVisible();

    await page.goto(`/w/${encodeURIComponent(workspaceId)}/brand`);
    await expect(page.getByRole('heading', { name: 'Hồ sơ thương hiệu' })).toBeVisible();
    const sourceToggle = page.getByRole('button', { name: /^Xem nguồn/ }).first();
    await expect(sourceToggle).toBeVisible({ timeout: 30_000 });
    await sourceToggle.click();
    await expect(page.locator('blockquote').first()).toBeVisible();

    // Confirm the current revision with the dedicated HTTP operation, then edit
    // and save+confirm atomically against the revision currently shown by API.
    if (await page.getByRole('button', { name: 'Xác nhận hồ sơ' }).isEnabled()) {
      await page.getByRole('button', { name: 'Xác nhận hồ sơ' }).click();
      await expect(page.getByText('Hồ sơ đã xác nhận')).toBeVisible();
      await expect.poll(() => brandMutations.some(({ method }) => method === 'POST')).toBe(true);
    }

    const businessName = page.getByLabel(/Sửa.*Tên doanh nghiệp/);
    await businessName.fill(`Pho Bac Pilot ${Date.now()}`);
    const persistedName = await businessName.inputValue();
    await page.getByRole('button', { name: 'Xác nhận hồ sơ' }).click();
    await expect(page.getByText('Hồ sơ đã xác nhận')).toBeVisible();
    await expect.poll(() => brandMutations.some(({ method }) => method === 'PATCH')).toBe(true);
    const patchBody = brandMutations.find(({ method }) => method === 'PATCH')?.body;
    expect(typeof patchBody).toBe('object');
    expect(patchBody).not.toBeNull();
    if (typeof patchBody === 'object' && patchBody !== null) {
      expect('version' in patchBody && typeof patchBody.version === 'number').toBe(true);
      expect('confirm' in patchBody && patchBody.confirm === true).toBe(true);
    }

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Hồ sơ thương hiệu' })).toBeVisible();
    await expect(page.getByLabel(/Sửa.*Tên doanh nghiệp/)).toHaveValue(persistedName);
    await expect(page.getByText('Hồ sơ đã xác nhận')).toBeVisible();

    expect(page.url()).toContain('/brand');
    expect(jobUrl).toContain('/jobs/');

    const expectedPaths = [
      '/api/v1/auth/login',
      '/api/v1/me',
      `/api/v1/workspaces/${workspaceId}/documents/limits`,
      `/api/v1/workspaces/${workspaceId}/documents`,
      `/api/v1/workspaces/${workspaceId}/brand-profile`,
    ];
    for (const path of expectedPaths) {
      expect(apiRequests.some((url) => new URL(url).pathname === path)).toBe(true);
    }
    if (explicitWorkspaceSelection) {
      expect(
        apiRequests.some((url) => new URL(url).pathname === '/api/v1/me/active-workspace'),
      ).toBe(true);
    }
    expect(apiRequests.every((url) => url.startsWith(apiOrigin))).toBe(true);
    expect(apiRequests.some((url) => new URL(url).pathname.startsWith('/api/v1/jobs/'))).toBe(true);
    expect(uploadCsrfHeader).toBeTruthy();
    expect(await page.getByText('Dữ liệu demo').count()).toBe(0);
  });

  test('Brand Profile 409 tells user to reload and does not retry the stale edit', async ({ page }) => {
    requireRealAccount();
    await login(page);
    const profileUrl = `${apiOrigin}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/brand-profile`;
    let patchCount = 0;
    await page.route(profileUrl, async (route) => {
      if (route.request().method() !== 'PATCH') return route.continue();
      patchCount += 1;
      return route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'version_conflict',
            message: 'Hồ sơ vừa được cập nhật ở nơi khác.',
            request_id: 'req_real_profile_conflict',
            retryable: false,
            details: { current_version: 42, your_version: 41 },
          },
        }),
      });
    });
    await page.goto(`/w/${encodeURIComponent(workspaceId)}/brand`);
    await expect(page.getByRole('heading', { name: 'Hồ sơ thương hiệu' })).toBeVisible();
    await page.getByLabel(/Sửa.*Tên doanh nghiệp/).fill('Bản sửa phải giữ lại để sao chép');
    await page.getByRole('button', { name: 'Lưu thay đổi' }).click();
    await expect(page.getByRole('button', { name: 'Tải bản mới nhất' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Thử lại' })).toHaveCount(0);
    expect(patchCount).toBe(1);
  });

  test('logout revokes through API origin; an expired cookie does not reveal demo data', async ({
    page,
  }) => {
    requireRealAccount();
    const logoutRequests: string[] = [];
    page.on('request', (request) => {
      if (new URL(request.url()).pathname === '/api/v1/auth/logout') {
        logoutRequests.push(request.url());
      }
    });

    await login(page);
    await page.getByRole('button', { name: 'Đăng xuất' }).click();
    await expect(page).toHaveURL(/\/login$/);
    expect(logoutRequests).toHaveLength(1);
    expect(logoutRequests[0]).toBe(`${apiOrigin}/api/v1/auth/logout`);

    await login(page);
    await page.context().clearCookies();
    await page.goto(`/w/${encodeURIComponent(workspaceId)}/documents`);
    await expect(page.getByRole('heading', { name: 'Phiên làm việc đã hết hạn' })).toBeVisible();
    await expect(page.getByText('Dữ liệu demo')).toHaveCount(0);
  });

  test('server error stays an error in real mode; it does not become fixture data', async ({
    page,
  }) => {
    requireRealAccount();
    await login(page);
    await page.route(
      `${apiOrigin}/api/v1/workspaces/${encodeURIComponent(workspaceId)}/documents`,
      async (route) => {
        if (route.request().method() !== 'GET') return route.continue();
        return route.fulfill({
          status: 503,
          contentType: 'application/json',
          body: JSON.stringify({
            error: {
              code: 'service_unavailable',
              message: 'Dịch vụ tài liệu đang tạm dừng.',
              request_id: 'req_real_e2e',
              retryable: true,
            },
          }),
        });
      },
    );
    await page.goto(`/w/${encodeURIComponent(workspaceId)}/documents`);
    await expect(page.getByRole('heading', { name: 'Không tải được danh sách tài liệu' })).toBeVisible();
    await expect(page.getByText('Dịch vụ tài liệu đang tạm dừng.')).toBeVisible();
    await expect(page.getByText('Dữ liệu demo')).toHaveCount(0);
  });
});
