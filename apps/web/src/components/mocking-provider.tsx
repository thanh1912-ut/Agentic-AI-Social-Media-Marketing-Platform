'use client';

import { useEffect, useState, type ReactNode } from 'react';

import { useMocks } from '@/lib/api/config';

/**
 * Bật mock ở tầng mạng TRƯỚC khi ứng dụng gọi API lần đầu.
 *
 * Dùng MSW để chặn ở đúng lớp `fetch` — nghĩa là toàn bộ đường đi thật
 * (client → HTTP → parse envelope lỗi) vẫn được chạy, chỉ có server là giả.
 * Nhờ vậy khi cắm backend thật vào, không phải sửa gì ở tầng UI.
 *
 * Khi `useMocks()` là false, component này không tải gì cả và render thẳng con.
 */
export function MockingProvider({ children }: { children: ReactNode }) {
  const mocksEnabled = useMocks();
  const [ready, setReady] = useState(false);
  const [reloadRequired, setReloadRequired] = useState(false);
  const [setupFailed, setSetupFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const { startMockWorker, unregisterMockWorker } = await import('@/lib/mocks/browser');
        if (mocksEnabled) {
          await startMockWorker();
        } else {
          const staleController = await unregisterMockWorker();
          const reloadKey = 'agentic:real-mode:mock-worker-reload';
          if (staleController && window.sessionStorage.getItem(reloadKey) !== 'done') {
            window.sessionStorage.setItem(reloadKey, 'done');
            window.location.reload();
            return;
          }
          if (staleController) {
            setReloadRequired(true);
            return;
          }
          window.sessionStorage.removeItem(reloadKey);
        }
        if (!cancelled) setReady(true);
      } catch {
        if (!cancelled) setSetupFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mocksEnabled]);

  if (!ready || reloadRequired || setupFailed) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        {setupFailed ? (
          <div className="max-w-md space-y-3 px-4 text-center">
            <p role="alert" className="text-sm text-rose-900">
              Không chuẩn bị được kết nối API. Trang chưa gửi request; hãy tải lại để thử lại.
            </p>
            <button
              type="button"
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
              onClick={() => window.location.reload()}
            >
              Tải lại trang
            </button>
          </div>
        ) : reloadRequired ? (
          <div className="max-w-md space-y-3 px-4 text-center">
            <p role="alert" className="text-sm text-amber-900">
              Trình duyệt còn giữ service worker của chế độ demo. Hãy tải lại để gửi request tới API thật.
            </p>
            <button
              type="button"
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white"
              onClick={() => {
                window.sessionStorage.removeItem('agentic:real-mode:mock-worker-reload');
                window.location.reload();
              }}
            >
              Tải lại trang
            </button>
          </div>
        ) : (
          <p role="status" className="text-sm text-slate-600">
            {mocksEnabled ? 'Đang chuẩn bị dữ liệu demo…' : 'Đang chuẩn bị kết nối API…'}
          </p>
        )}
      </div>
    );
  }

  return <>{children}</>;
}
