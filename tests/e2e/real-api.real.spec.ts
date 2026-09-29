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
  await chooseWorkspace(page, workspaceId);
}

async function chooseWorkspace(page: Page, id: string): Promise<boolean> {
  await page.goto('/');
  const chooserHeading = page.getByRole('heading', { name: 'Chọn doanh nghiệp' });
  const explicitSelection = await chooserHeading
    .waitFor({ state: 'visible', timeout: 1_500 })
    .then(() => true)
    .catch(() => false);
  if (explicitSelection) {
    await page.locator(`input[name="workspace"][value="${id}"]`).check();
    await page.getByRole('button', { name: 'Mở không gian làm việc' }).click();
  } else {
    await page.waitForURL((url) => url.pathname.startsWith(`/w/${id}/`));
  }
  await page.waitForURL((url) => url.pathname.startsWith(`/w/${id}/`));
  await page.goto(`/w/${id}/documents`);
  await page.waitForURL((url) => url.pathname === `/w/${id}/documents`);
  return explicitSelection;
}


test.describe('real API acceptance — auth, documents, jobs and Brand Profile', () => {
  test('self registration creates only an account; logout and login return to Page activation', async ({ page }) => {
    test.skip(
      process.env.E2E_REAL_AUTH_TESTS !== '1',
      'Set E2E_REAL_AUTH_TESTS=1 only against a disposable real API database.',
    );
    const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const email = `signup-${suffix}@example.com`;
    const password = `e2e-${suffix}-password`;

    await page.goto('/register');
    await page.getByLabel('Họ tên').fill('E2E Account Owner');
    await page.getByLabel('Email', { exact: true }).fill(email);
    await page.getByLabel('Mật khẩu', { exact: true }).fill(password);
    await page.getByLabel('Nhập lại mật khẩu').fill(password);
    await page.getByRole('button', { name: 'Đăng ký' }).click();
    await expect(page).toHaveURL('/');
    await expect(page.getByRole('heading', { name: 'Chọn doanh nghiệp để bắt đầu' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Thêm Fanpage doanh nghiệp' })).toBeVisible();
    await expect(page.getByLabel('Page ID')).toBeVisible();
    await expect(page.getByLabel('Page Access Token')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible();

    await page.reload();
    await expect(page.getByRole('heading', { name: 'Chọn doanh nghiệp để bắt đầu' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible();
    await page.getByRole('button', { name: 'Đăng xuất' }).click();
    await expect(page).toHaveURL(/\/login$/);

    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Mật khẩu').fill(password);
    await page.getByRole('button', { name: 'Đăng nhập' }).click();
    await expect(page.getByRole('button', { name: 'Đăng xuất' })).toBeVisible();
    await expect(page).toHaveURL('/');
    await expect(page.getByRole('heading', { name: 'Chọn doanh nghiệp để bắt đầu' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Thêm Fanpage doanh nghiệp' })).toBeVisible();
  });

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
    await page.getByLabel('Giới thiệu thương hiệu cho AI').fill('Bản sửa phải giữ lại để sao chép');
    await page.getByRole('button', { name: 'Lưu và áp dụng' }).click();
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
