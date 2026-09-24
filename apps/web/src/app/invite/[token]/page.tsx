'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError, api } from '@/lib/api';
import type { ApiAcceptInvitationRequest } from '@/lib/api/types';
import { queryKeys } from '@/lib/query-keys';
import { Button, Card, ErrorPanel, LoadingBlock } from '@/components/ui';

export default function AcceptInvitationPage() {
  const params = useParams<{ token?: string }>();
  const token = params?.token ?? '';
  const router = useRouter();
  const queryClient = useQueryClient();
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);

  const preview = useQuery({
    queryKey: ['invitation-preview', token],
    queryFn: () => api.auth.previewInvitation(token),
    enabled: token.length > 0,
    retry: false,
  });
  const accept = useMutation({
    mutationFn: (body: ApiAcceptInvitationRequest) => api.auth.acceptInvitation(token, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.me });
      await queryClient.refetchQueries({ queryKey: queryKeys.me });
      router.replace('/');
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const invitation = preview.data;
    if (!invitation) return;
    if (password && password.length < 8) {
      setValidationError('Mật khẩu cần có ít nhất 8 ký tự.');
      return;
    }
    if (password !== confirmation) {
      setValidationError('Hai mật khẩu chưa khớp nhau.');
      return;
    }
    setValidationError(null);
    const body: ApiAcceptInvitationRequest = {
      email: invitation.email,
      ...(fullName.trim() ? { full_name: fullName.trim() } : {}),
      ...(password ? { password } : {}),
    };
    accept.mutate(body);
  }

  const apiError = accept.error instanceof ApiError ? accept.error : null;
  const previewError = preview.error instanceof ApiError ? preview.error : null;
  const roleLabel = preview.data?.role === 'editor' ? 'Biên tập viên' : 'Chỉ xem';

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-lg flex-col justify-center px-4 py-10">
      <h1 className="text-lg font-semibold text-slate-900">Tham gia doanh nghiệp</h1>
      <p className="mt-1 text-sm text-slate-600">Xem thông tin lời mời rồi xác nhận để vào workspace.</p>
      <div className="mt-5">
        <Card>
          {preview.isPending ? (
            <LoadingBlock label="Đang kiểm tra lời mời…" />
          ) : previewError ? (
            <ErrorPanel
              title="Lời mời không còn dùng được"
              message={previewError.message}
              code={previewError.code}
              requestId={previewError.requestId}
              retryable={previewError.retryable}
              onRetry={() => void preview.refetch()}
            />
          ) : preview.data ? (
            <form onSubmit={submit} className="space-y-4" noValidate>
              <dl className="space-y-2 rounded-lg bg-slate-50 p-3 text-sm">
                <div>
                  <dt className="text-xs text-slate-500">Doanh nghiệp</dt>
                  <dd className="font-medium text-slate-900">{preview.data.workspace_name}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Email được mời</dt>
                  <dd className="font-medium text-slate-900">{preview.data.email}</dd>
                </div>
                <div>
                  <dt className="text-xs text-slate-500">Vai trò</dt>
                  <dd className="font-medium text-slate-900">{roleLabel}</dd>
                </div>
              </dl>
              <p className="text-sm text-slate-600">
                Nếu email này chưa có tài khoản, hãy nhập họ tên và tạo mật khẩu. Tài khoản hiện có có thể để trống hai trường này.
              </p>
              <div>
                <label htmlFor="invite-full-name" className="block text-sm font-medium text-slate-700">Họ tên</label>
                <input
                  id="invite-full-name"
                  name="full_name"
                  autoComplete="name"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
              <div>
                <label htmlFor="invite-password" className="block text-sm font-medium text-slate-700">Tạo mật khẩu nếu đây là tài khoản mới</label>
                <input
                  id="invite-password"
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  minLength={8}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                />
              </div>
              {password ? (
                <div>
                  <label htmlFor="invite-confirm-password" className="block text-sm font-medium text-slate-700">Nhập lại mật khẩu</label>
                  <input
                    id="invite-confirm-password"
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
              ) : null}
              {validationError ? <p role="alert" className="text-sm text-rose-700">{validationError}</p> : null}
              {apiError ? (
                <ErrorPanel
                  title="Không chấp nhận được lời mời"
                  message={apiError.message}
                  code={apiError.code}
                  requestId={apiError.requestId}
                  retryable={apiError.retryable}
                  onRetry={() => accept.mutate({
                    email: preview.data.email,
                    ...(fullName.trim() ? { full_name: fullName.trim() } : {}),
                    ...(password ? { password } : {}),
                  })}
                />
              ) : null}
              <Button type="submit" loading={accept.isPending}>
                {accept.isPending ? 'Đang tham gia…' : 'Chấp nhận lời mời'}
              </Button>
            </form>
          ) : (
            <p role="alert" className="text-sm text-rose-700">Liên kết lời mời không có mã xác thực.</p>
          )}
        </Card>
      </div>
      <p className="mt-5 text-sm text-slate-600">
        <Link href="/login" className="font-medium text-slate-900 underline">Đến trang đăng nhập</Link>
      </p>
    </div>
  );
}
