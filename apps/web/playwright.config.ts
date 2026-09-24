import { defineConfig, devices } from '@playwright/test';

/**
 * Cấu hình E2E.
 *
 * Chạy với dữ liệu demo (`NEXT_PUBLIC_USE_MOCKS=1`) nên không cần backend. Khi
 * backend sẵn sàng, đổi `NEXT_PUBLIC_USE_MOCKS=0` và trỏ `NEXT_PUBLIC_API_BASE_URL`
 * vào môi trường test — bộ test giữ nguyên.
 */
const PORT = Number(process.env.E2E_PORT ?? 3100);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: '../../tests/e2e',
  testIgnore: ['**/*.real.spec.ts'],
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  timeout: 60_000,
  expect: { timeout: 10_000 },

  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'vi-VN',
    timezoneId: 'Asia/Ho_Chi_Minh',
  },

  projects: [
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 7'] } },
  ],

  webServer: {
    command: `npm run build && node scripts/prepare-standalone.mjs && node .next/standalone/apps/web/server.js`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
    env: {
      HOSTNAME: '127.0.0.1',
      PORT: String(PORT),
      NEXT_PUBLIC_USE_MOCKS: '1',
      NEXT_PUBLIC_API_BASE_URL: 'http://127.0.0.1:8000',
      NEXT_PUBLIC_ENVIRONMENT_LABEL: 'Bản demo',
    },
  },
});
