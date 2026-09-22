'use client';

import { createContext, useContext, useMemo, type ReactNode } from 'react';

import type { SessionResponse, Workspace } from '@agentic/contracts';

import { ApiError } from '@/lib/api';
import { useMe } from '@/lib/hooks';
import { Button, ErrorPanel, LoadingBlock } from '@/components/ui';

interface SessionValue {
  session: SessionResponse;
  user: SessionResponse['user'];
  workspaces: Workspace[];
}

const SessionContext = createContext<SessionValue | null>(null);

/** Truy cập phiên hiện tại. Chỉ dùng được bên trong `SessionGate`. */
export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error('useSession phải được dùng bên trong <SessionGate>.');
  }
  return value;
}

/**
 * Cổng phiên.
 *
 * Ba trạng thái phải phân biệt rõ:
 * - đang tải  → chờ, chưa kết luận gì
 * - 401       → chưa đăng nhập (hoặc phiên hết hạn) → mời đăng nhập
 * - lỗi khác  → lỗi hệ thống, cho thử lại
 *
 * Lưu ý: đây chỉ là lớp trải nghiệm. Backend vẫn kiểm quyền cho từng request.
 */
export function SessionGate({ children }: { children: ReactNode }) {
  const me = useMe();

  const value = useMemo<SessionValue | null>(() => {
    if (!me.data) return null;
    return {
      session: me.data,
      user: me.data.user,
      workspaces: me.data.workspaces,
    };
  }, [me.data]);

  if (me.isLoading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-10">
        <LoadingBlock label="Đang kiểm tra phiên đăng nhập…" />
      </div>
    );
  }

  if (me.isError) {
    const error = me.error instanceof ApiError ? me.error : null;

    if (error?.isUnauthenticated) {
      return (
        <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center px-4">
          <div className="rounded-xl border border-slate-200 bg-white px-6 py-8 shadow-sm">
            <h1 className="text-lg font-semibold text-slate-900">
              {error.isSessionExpired ? 'Phiên làm việc đã hết hạn' : 'Bạn chưa đăng nhập'}
            </h1>
            <p className="mt-2 text-sm text-slate-600">
              {error.isSessionExpired
                ? 'Vì an toàn, hệ thống đã kết thúc phiên sau một thời gian không hoạt động. Đăng nhập lại để tiếp tục — dữ liệu bạn đã lưu vẫn còn nguyên.'
                : 'Đăng nhập để vào khu vực làm việc của doanh nghiệp.'}
            </p>
            <div className="mt-5">
              <Button onClick={() => window.location.assign('/login')}>Đăng nhập</Button>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="mx-auto max-w-2xl px-4 py-10">
        <ErrorPanel
          title="Không kiểm tra được phiên đăng nhập"
          message={error?.message ?? 'Đã xảy ra lỗi không xác định.'}
          code={error?.code}
          requestId={error?.requestId}
          retryable={error?.retryable ?? true}
          onRetry={() => void me.refetch()}
        />
      </div>
    );
  }

  if (!value) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-10">
        <LoadingBlock label="Đang tải thông tin doanh nghiệp…" />
      </div>
    );
  }

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
