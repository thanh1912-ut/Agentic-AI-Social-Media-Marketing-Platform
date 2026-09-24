'use client';

import { Suspense, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useMutation } from '@tanstack/react-query';

import { ApiError, api } from '@/lib/api';
import { Button, Card, ErrorPanel } from '@/components/ui';

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  const reset = useMutation({
    mutationFn: (newPassword: string) => api.auth.resetPassword({ token, new_password: newPassword }),
  });
  const apiError = reset.error instanceof ApiError ? reset.error : null;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      setValidationError('Liên kết thiếu mã đặt lại mật khẩu. Hãy yêu cầu liên kết mới.');
      return;
    }
    if (password.length < 8) {
      setValidationError('Mật khẩu cần có ít nhất 8 ký tự.');
      return;
    }
    if (password !== confirmation) {
      setValidationError('Hai mật khẩu chưa khớp nhau.');
      return;
    }
    setValidationError(null);
    reset.mutate(password);
  }

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col justify-center px-4 py-10">
      <h1 className="text-lg font-semibold text-slate-900">Đặt mật khẩu mới</h1>
      <p className="mt-1 text-sm text-slate-600">
        Chọn mật khẩu mới cho tài khoản của bạn. Liên kết chỉ dùng được một lần.
      </p>
      <div className="mt-5">
        <Card>
          {reset.isSuccess ? (
            <div role="status" className="space-y-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
              <h2 className="text-sm font-semibold text-emerald-900">Đã cập nhật mật khẩu</h2>
              <p className="text-sm text-emerald-900">Các phiên đăng nhập cũ đã kết thúc. Đăng nhập lại bằng mật khẩu mới.</p>
              <Link href="/login" className="inline-flex font-medium text-slate-900 underline">Đến trang đăng nhập</Link>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4" noValidate>
              <div>
                <label htmlFor="new-password" className="block text-sm font-medium text-slate-700">Mật khẩu mới</label>
                <input
                  id="new-password"
                  name="new_password"
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
              <div>
                <label htmlFor="confirm-password" className="block text-sm font-medium text-slate-700">Nhập lại mật khẩu</label>
                <input
                  id="confirm-password"
                  name="confirm_password"
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  required
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
              {validationError ? <p role="alert" className="text-sm text-rose-700">{validationError}</p> : null}
              {apiError ? (
                <ErrorPanel
                  title={apiError.code === 'invalid_reset_token' ? 'Liên kết không còn hợp lệ' : 'Không cập nhật được mật khẩu'}
                  message={apiError.message}
                  code={apiError.code}
                  requestId={apiError.requestId}
                  retryable={apiError.retryable}
                  onRetry={() => reset.mutate(password)}
                />
              ) : null}
              <Button type="submit" loading={reset.isPending}>
                {reset.isPending ? 'Đang cập nhật…' : 'Cập nhật mật khẩu'}
              </Button>
            </form>
          )}
        </Card>
      </div>
      {!reset.isSuccess ? (
        <p className="mt-5 text-sm text-slate-600">
          <Link href="/forgot-password" className="font-medium text-slate-900 underline">Yêu cầu liên kết mới</Link>
        </p>
      ) : null}
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-md px-4 py-10 text-sm text-slate-600">Đang tải biểu mẫu đặt lại mật khẩu…</div>}>
      <ResetPasswordForm />
    </Suspense>
  );
}
