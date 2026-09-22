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
  const [ready, setReady] = useState(!mocksEnabled);

  useEffect(() => {
    if (!mocksEnabled) return;
    let cancelled = false;

    void (async () => {
      const { startMockWorker } = await import('@/lib/mocks/browser');
      await startMockWorker();
      if (!cancelled) setReady(true);
    })();

    return () => {
      cancelled = true;
    };
  }, [mocksEnabled]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p role="status" className="text-sm text-slate-600">
          Đang chuẩn bị dữ liệu demo…
        </p>
      </div>
    );
  }

  return <>{children}</>;
}
