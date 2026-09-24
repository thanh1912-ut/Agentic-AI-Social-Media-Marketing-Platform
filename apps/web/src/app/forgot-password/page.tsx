'use client';

/**
 * Quên mật khẩu.
 *
 * Nguyên tắc bảo mật: câu xác nhận sau khi gửi KHÔNG được tiết lộ email có tồn
 * tại hay không. Dù backend trả kết quả nào (trừ lỗi mạng / lỗi hệ thống), người
 * dùng luôn đọc đúng một câu như nhau.
 */

import { useState, type FormEvent } from 'react';
import Link from 'next/link';

import { useMutation } from '@tanstack/react-query';

import { ApiError, api } from '@/lib/api';
import { Button, Card, ErrorPanel } from '@/components/ui';

/** Câu xác nhận trung tính — dùng chung cho mọi trường hợp gửi thành công. */
const NEUTRAL_CONFIRMATION =
  'Nếu email này có tài khoản và hệ thống đã cấu hình gửi thư, hướng dẫn đặt lại mật khẩu sẽ được gửi. Liên kết chỉ dùng được một lần và sẽ hết hạn sau ít phút.';

export default function TrangQuenMatKhau() {
  const [email, setEmail] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [formatError, setFormatError] = useState<string | null>(null);

  const forgot = useMutation({
    mutationFn: (value: string) => api.auth.forgotPassword(value),
    onSuccess: () => setSubmitted(true),
  });

  const apiError = forgot.error instanceof ApiError ? forgot.error : null;
  const isNetworkError = apiError?.isNetworkError ?? false;
  const isSessionExpired = apiError?.isSessionExpired ?? false;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = email.trim();
    if (value === '' || !value.includes('@')) {
      setFormatError('Hãy nhập đúng địa chỉ email bạn dùng để đăng nhập.');
      return;
    }
    setFormatError(null);
    setSubmitted(false);
    forgot.mutate(value);
  }

  const emailDescribedBy = [
    'forgot-email-hint',
    formatError ? 'forgot-email-error' : null,
    apiError ? 'forgot-error' : null,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col justify-center px-4 py-10">
      <h1 className="text-lg font-semibold text-slate-900">Quên mật khẩu</h1>
      <p className="mt-1 text-sm text-slate-600">
        Nhập email đã dùng để đăng nhập. Hệ thống sẽ gửi hướng dẫn nếu email tồn tại và email delivery đã được cấu hình.
      </p>

      <div className="mt-5">
        <Card>
          {submitted ? (
            <div role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
              <h2 className="text-sm font-semibold text-emerald-900">Đã tiếp nhận yêu cầu</h2>
              <p className="mt-1 text-sm text-emerald-900">{NEUTRAL_CONFIRMATION}</p>
              <p className="mt-2 text-xs text-emerald-800">
                Vì lý do bảo mật, hệ thống không cho biết email này có tài khoản hay không. Nếu chưa nhận được thư, hãy liên hệ quản trị viên.
              </p>
              <div className="mt-3">
                <Button variant="secondary" size="sm" onClick={() => setSubmitted(false)}>
                  Gửi lại với email khác
                </Button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div>
                <label htmlFor="forgot-email" className="block text-sm font-medium text-slate-700">
                  Email đăng nhập
                </label>
                <input
                  id="forgot-email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  aria-describedby={emailDescribedBy}
                  aria-invalid={formatError ? true : undefined}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
                <p id="forgot-email-hint" className="mt-1 text-xs text-slate-500">
                  Dùng đúng email mà chủ sở hữu doanh nghiệp đã mời bạn.
                </p>
                {formatError ? (
                  <p id="forgot-email-error" role="alert" className="mt-1 text-xs text-rose-700">
                    {formatError}
                  </p>
                ) : null}
              </div>

              {apiError ? (
                <div id="forgot-error" role="alert">
                  <ErrorPanel
                    title={
                      isNetworkError
                        ? 'Không kết nối được tới máy chủ'
                        : isSessionExpired
                          ? 'Phiên làm việc đã hết hạn'
                          : 'Không gửi được yêu cầu đặt lại mật khẩu'
                    }
                    message={apiError.message}
                    code={apiError.code}
                    requestId={apiError.requestId}
                    retryable={apiError.retryable}
                    onRetry={() => forgot.mutate(email.trim())}
                  />
                </div>
              ) : null}

              <Button type="submit" loading={forgot.isPending}>
                {forgot.isPending ? 'Đang gửi…' : 'Gửi hướng dẫn đặt lại mật khẩu'}
              </Button>
            </form>
          )}
        </Card>
      </div>

      <p className="mt-5 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-slate-900 underline">
          Quay lại trang đăng nhập
        </Link>
      </p>
    </div>
  );
}
