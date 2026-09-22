'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { ApiError } from '@/lib/api';

/**
 * Chính sách thử lại.
 *
 * Cố ý KHÔNG thử lại các lỗi 4xx (trừ 408/429): lỗi quyền, lỗi dữ liệu hay xung
 * đột phiên bản thì thử lại cũng không khỏi, chỉ làm người dùng chờ vô ích.
 * Đặc biệt `version_conflict` không bao giờ được thử lại — sẽ ghi đè dữ liệu.
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 2) return false;
  if (error instanceof ApiError) {
    if (error.isVersionConflict) return false;
    if (error.status !== null && error.status >= 400 && error.status < 500) {
      return error.status === 408 || error.status === 429;
    }
    return error.retryable;
  }
  return false;
}

export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: shouldRetry,
            refetchOnWindowFocus: false,
            staleTime: 15_000,
          },
          mutations: {
            // Ghi dữ liệu thì không tự thử lại: có thể tạo trùng.
            retry: false,
          },
        },
      }),
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
