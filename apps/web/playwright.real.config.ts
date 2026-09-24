import { defineConfig, devices } from '@playwright/test';

const suppliedApiOrigin =
  process.env.E2E_REAL_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;

if (!suppliedApiOrigin) {
  throw new Error(
    'Real E2E cần E2E_REAL_API_BASE_URL (API origin, không gồm /api/v1).',
  );
}

const parsedApiOrigin = new URL(suppliedApiOrigin);
if (parsedApiOrigin.pathname !== '/' || parsedApiOrigin.search || parsedApiOrigin.hash) {
  throw new Error('E2E_REAL_API_BASE_URL chỉ được là API origin, không có path/query/hash.');
}

const apiOrigin = parsedApiOrigin.origin;
const port = Number(process.env.E2E_REAL_PORT ?? 3101);
const baseURL = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: '../../tests/e2e',
  testMatch: ['**/*.real.spec.ts'],
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  workers: 1,
  reporter: 'list',
  timeout: 120_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'vi-VN',
    timezoneId: 'Asia/Ho_Chi_Minh',
  },
  projects: [{ name: 'real-api-chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run build && node scripts/prepare-standalone.mjs && node .next/standalone/apps/web/server.js`,
    url: baseURL,
    reuseExistingServer: false,
    timeout: 180_000,
    env: {
      HOSTNAME: '127.0.0.1',
      PORT: String(port),
      NEXT_PUBLIC_USE_MOCKS: '0',
      NEXT_PUBLIC_API_BASE_URL: apiOrigin,
      NEXT_PUBLIC_ENVIRONMENT_LABEL: 'Kết nối API thật',
    },
  },
});
