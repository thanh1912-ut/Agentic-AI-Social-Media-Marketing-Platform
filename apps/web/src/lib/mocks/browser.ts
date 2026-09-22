'use client';

/**
 * Khởi động MSW trong trình duyệt.
 *
 * Chỉ được gọi khi `NEXT_PUBLIC_USE_MOCKS=1`. Service worker nằm ở
 * `public/mockServiceWorker.js` (sinh bằng `npx msw init public`).
 */

import { setupWorker } from 'msw/browser';

import { handlers } from './handlers';

let started = false;

export async function startMockWorker(): Promise<void> {
  if (started) return;
  const worker = setupWorker(...handlers);
  await worker.start({
    // Không làm ồn console với các request không có handler (tài nguyên tĩnh…).
    onUnhandledRequest: 'bypass',
    quiet: true,
    serviceWorker: { url: '/mockServiceWorker.js' },
  });
  started = true;
}
