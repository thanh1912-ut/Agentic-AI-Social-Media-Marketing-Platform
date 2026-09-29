'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiError, api, useMocks } from '@/lib/api';
import type { ApiRegisterRequest } from '@/lib/api/types';
import { queryKeys } from '@/lib/query-keys';
import { Button, ErrorPanel } from '@/components/ui';
import { AuthShell } from '@/components/auth-shell';

export default function RegisterPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const mocksEnabled = useMocks();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [accountCreated, setAccountCreated] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);

  const register = useMutation({
    mutationFn: (body: ApiRegisterRequest) => api.auth.register(body),
    onSuccess: async (created) => {
      setAccountCreated(true);
      try {
        const session = await api.auth.me();
        queryClient.clear();
        queryClient.setQueryData(queryKeys.me, session);
        const workspaceId = session.active_workspace_id ?? created.active_workspace_id;
        if (!workspaceId) {
          router.replace('/');
          return;
        }
        router.replace(`/w/${workspaceId}/brand`);
      } catch {
        setSessionError('Tài khoản đã tạo nhưng chưa xác nhận được phiên đăng nhập. Hãy đăng nhập bằng email và mật khẩu vừa tạo.');
      }
    },
  });

  const apiError = register.error instanceof ApiError ? register.error : null;

  function startRegistration() {
    if (register.isPending) return;
    if (!fullName.trim() || !email.trim() || !companyName.trim() || password.length < 8 || password.length > 200) {
      setValidationError('Hãy điền đủ thông tin và dùng mật khẩu từ 8 đến 200 ký tự.');
      return;
    }
    const emailInput = document.getElementById('register-email');
    if (emailInput instanceof HTMLInputElement && !emailInput.checkValidity()) {
      setValidationError('Hãy nhập địa chỉ email hợp lệ.');
      return;
    }
    if (password !== confirmation) {
      setValidationError('Hai mật khẩu chưa khớp nhau.');
      return;
    }
    setValidationError(null);
    const body: ApiRegisterRequest = {
      email: email.trim(),
      password,
      full_name: fullName.trim(),
      company_name: companyName.trim(),
    };
    register.mutate(body);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    startRegistration();
  }

  return (
    <AuthShell title="Tạo tài khoản" description="Bắt đầu với không gian riêng cho thương hiệu. Nếu đã được mời vào một nhóm, hãy dùng liên kết trong lời mời.">
          {mocksEnabled ? (
            <div role="status" className="space-y-3">
              <p className="text-sm text-slate-700">Đăng ký cần kết nối máy chủ thật. Bản demo chỉ dùng các tài khoản mẫu.</p>
              <Link href="/login" className="text-sm font-medium text-slate-900 underline">Quay lại đăng nhập demo</Link>
            </div>
          ) : accountCreated ? (
            <div role="status" className="space-y-3">
              <h2 className="text-sm font-semibold text-emerald-900">Đã tạo tài khoản</h2>
              <p className="text-sm text-slate-700">Email: <span className="font-medium">{email.trim()}</span></p>
              {sessionError ? <p className="text-sm text-amber-800">{sessionError}</p> : null}
              <Link href="/login" className="text-sm font-medium text-slate-900 underline">Đến trang đăng nhập</Link>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4" noValidate>
              <div>
                <label htmlFor="register-name" className="block text-sm font-medium text-slate-700">Họ tên</label>
                <input
                  id="register-name"
                  name="full_name"
                  autoComplete="name"
                  required
                  maxLength={200}
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
              <div>
                <label htmlFor="register-email" className="block text-sm font-medium text-slate-700">Email</label>
                <input
                  id="register-email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  maxLength={320}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
              <div>
                <label htmlFor="register-company" className="block text-sm font-medium text-slate-700">Tên thương hiệu / workspace</label>
                <input
                  id="register-company"
                  name="company_name"
                  autoComplete="organization"
                  required
                  maxLength={200}
                  value={companyName}
                  onChange={(event) => setCompanyName(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
              <div>
                <label htmlFor="register-password" className="block text-sm font-medium text-slate-700">Mật khẩu</label>
                <input
                  id="register-password"
                  name="password"
                  type={passwordVisible ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  maxLength={200}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  aria-describedby="register-password-hint"
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
                <div className="mt-1 flex items-center justify-between gap-2">
                  <p id="register-password-hint" className="text-xs text-slate-500">Từ 8 đến 200 ký tự.</p>
                  <button type="button" className="text-xs font-medium text-slate-700 underline" onClick={() => setPasswordVisible((value) => !value)}>
                    {passwordVisible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                  </button>
                </div>
              </div>
              <div>
                <label htmlFor="register-confirm-password" className="block text-sm font-medium text-slate-700">Nhập lại mật khẩu</label>
                <input
                  id="register-confirm-password"
                  name="confirm_password"
                  type={passwordVisible ? 'text' : 'password'}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  maxLength={200}
                  value={confirmation}
                  onChange={(event) => setConfirmation(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>

              {validationError ? <p role="alert" className="text-sm text-rose-700">{validationError}</p> : null}
              {apiError ? (
                <ErrorPanel
                  title={apiError.code === 'already_exists' ? 'Email đã có tài khoản' : 'Không tạo được tài khoản'}
                  message={apiError.isNetworkError
                    ? 'Không rõ máy chủ đã tạo tài khoản chưa. Hãy thử đăng nhập bằng email và mật khẩu này trước khi gửi đăng ký lại.'
                    : apiError.message}
                  code={apiError.code}
                  requestId={apiError.requestId}
                  retryable={apiError.retryable && !apiError.isNetworkError}
                  onRetry={apiError.isNetworkError ? undefined : startRegistration}
                />
              ) : null}
              {apiError?.code === 'already_exists' || apiError?.isNetworkError ? (
                <p className="text-sm text-slate-600">
                  <Link href="/login" className="font-medium text-slate-900 underline">Đăng nhập</Link>
                  {apiError.code === 'already_exists' ? (
                    <> hoặc <Link href="/forgot-password" className="font-medium text-slate-900 underline">đặt lại mật khẩu</Link>.</>
                  ) : null}
                </p>
              ) : null}
              <Button type="submit" loading={register.isPending}>
                {register.isPending ? 'Đang tạo tài khoản…' : 'Đăng ký'}
              </Button>
              <p className="pt-2 text-center text-sm text-slate-600">
                Đã có tài khoản? <Link href="/login" className="font-medium text-slate-900 underline">Đăng nhập</Link>
              </p>
            </form>
          )}
    </AuthShell>
  );
}
