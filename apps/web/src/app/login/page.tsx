'use client';

/**
 * Đăng nhập.
 *
 * Lưu ý kiến trúc: trang này nằm trong `app/layout.tsx` — nơi bọc mọi trang bằng
 * `SessionGate`. Nếu cổng phiên chặn người chưa đăng nhập ở tầng layout thì form
 * dưới đây sẽ không bao giờ được render. Xem mục "khoảng trống hợp đồng" trong
 * báo cáo của slice này (cần tách cổng phiên ra khỏi nhánh /login).
 */

import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { useMutation, useQueryClient } from '@tanstack/react-query';

import { ApiError, api } from '@/lib/api';
import { useMocks } from '@/lib/api/config';
import { queryKeys } from '@/lib/query-keys';
import { Button, Card, DemoBadge, DisabledReason } from '@/components/ui';

/**
 * Tài khoản mẫu cho chế độ mock.
 *
 * ĐÂY LÀ LỐI TẮT CỦA BẢN DEMO, KHÔNG PHẢI TÍNH NĂNG THẬT: chỉ hiển thị khi
 * `useMocks()` bật. Danh sách này khớp với `DEMO_ACCOUNTS` trong
 * `src/lib/mocks/seed.ts` — sửa một bên thì phải sửa cả hai.
 */
const DEMO_ACCOUNTS: Array<{
  role: string;
  email: string;
  password: string;
  note: string;
}> = [
  {
    role: 'Chủ sở hữu (owner)',
    email: 'chu.quan@phobac.vn',
    password: 'demo1234',
    note: 'Toàn quyền: xác nhận hồ sơ, tải tài liệu, duyệt và đăng bài.',
  },
  {
    role: 'Biên tập viên (editor)',
    email: 'bientap@phobac.vn',
    password: 'demo1234',
    note: 'Sửa hồ sơ và tải tài liệu; không xác nhận hồ sơ, không duyệt bài.',
  },
  {
    role: 'Người xem (viewer)',
    email: 'xem@phobac.vn',
    password: 'demo1234',
    note: 'Chỉ xem — dùng để thấy giao diện khi bị khoá quyền.',
  },
];

export default function TrangDangNhap() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const mocksEnabled = useMocks();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mounted, setMounted] = useState(false);

  // Chỉ hiện gợi ý demo sau khi đã mount để bản render ở server và ở client khớp nhau.
  useEffect(() => setMounted(true), []);

  const login = useMutation({
    mutationFn: (credentials: { email: string; password: string }) =>
      api.auth.login(credentials),
    onSuccess: async () => {
      // Cổng phiên đọc lại `/me` rồi mới đi tiếp, nếu không trang gốc sẽ thấy
      // trạng thái "chưa đăng nhập" còn sót trong bộ đệm.
      await queryClient.invalidateQueries({ queryKey: queryKeys.me });
      await queryClient.refetchQueries({ queryKey: queryKeys.me });
      router.push('/');
    },
  });

  const apiError = login.error instanceof ApiError ? login.error : null;
  const genericError = login.error && !apiError ? 'Đã xảy ra lỗi không xác định khi đăng nhập.' : null;
  const isNetworkError = apiError?.isNetworkError ?? false;

  const missingFields = email.trim() === '' || password === '';
  const disabledReason = missingFields ? 'Hãy nhập đủ email và mật khẩu để đăng nhập.' : undefined;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (missingFields || login.isPending) return;
    login.mutate({ email: email.trim(), password });
  }

  function fillDemoAccount(account: (typeof DEMO_ACCOUNTS)[number]) {
    setEmail(account.email);
    setPassword(account.password);
    login.reset();
  }

  const errorDescribedBy = apiError || genericError ? 'login-error' : undefined;

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-4 py-10">
      <h1 className="text-lg font-semibold text-slate-900">Đăng nhập</h1>
      <p className="mt-1 text-sm text-slate-600">
        Vào khu vực làm việc của doanh nghiệp để nhập tài liệu và quản lý nội dung.
      </p>

      <div className="mt-5">
        <Card>
          <form onSubmit={handleSubmit} className="space-y-4" noValidate>
            <div>
              <label htmlFor="login-email" className="block text-sm font-medium text-slate-700">
                Email
              </label>
              <input
                id="login-email"
                name="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                aria-describedby={`login-email-hint${errorDescribedBy ? ` ${errorDescribedBy}` : ''}`}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
              <p id="login-email-hint" className="mt-1 text-xs text-slate-500">
                Email bạn đã dùng khi được mời vào doanh nghiệp.
              </p>
            </div>

            <div>
              <label htmlFor="login-password" className="block text-sm font-medium text-slate-700">
                Mật khẩu
              </label>
              <input
                id="login-password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-describedby={errorDescribedBy}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
              />
            </div>

            {apiError || genericError ? (
              <div
                id="login-error"
                role="alert"
                className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3"
              >
                <p className="text-sm font-semibold text-rose-900">
                  {isNetworkError ? 'Không kết nối được tới máy chủ' : 'Không đăng nhập được'}
                </p>
                <p className="mt-1 text-sm text-rose-800">
                  {isNetworkError
                    ? 'Máy chủ không phản hồi. Hãy kiểm tra kết nối mạng, sau đó thử đăng nhập lại. Mật khẩu bạn vừa nhập vẫn còn trong ô, không cần gõ lại.'
                    : (apiError?.message ?? genericError)}
                </p>
                {apiError?.reference ? (
                  <p className="mt-1 text-xs text-rose-700/80">
                    Mã tra cứu: <code className="font-mono">{apiError.reference}</code>
                  </p>
                ) : null}
              </div>
            ) : null}

            <div>
              <Button
                type="submit"
                loading={login.isPending}
                disabled={missingFields}
                disabledReason={disabledReason}
              >
                {login.isPending ? 'Đang đăng nhập…' : 'Đăng nhập'}
              </Button>
              {missingFields ? <DisabledReason>{disabledReason}</DisabledReason> : null}
            </div>

            <p className="text-sm text-slate-600">
              <Link href="/forgot-password" className="font-medium text-slate-900 underline">
                Quên mật khẩu?
              </Link>
            </p>
          </form>
        </Card>
      </div>

      {mounted && mocksEnabled ? (
        <section
          aria-label="Lối tắt đăng nhập cho bản demo"
          className="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold text-amber-900">
              Lối tắt đăng nhập demo — không phải tính năng thật
            </h2>
            <DemoBadge label="Chỉ có ở bản demo" />
          </div>
          <p className="mt-1 text-sm text-amber-900">
            Mục này chỉ hiện khi bật chế độ dữ liệu mẫu (<code className="font-mono">NEXT_PUBLIC_USE_MOCKS=1</code>).
            Khi nối vào máy chủ thật, mục này tự ẩn và các tài khoản dưới đây không tồn tại.
          </p>
          <ul className="mt-2 space-y-2">
            {DEMO_ACCOUNTS.map((account) => (
              <li
                key={account.email}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-200 bg-white px-3 py-2"
              >
                <div className="text-sm text-slate-800">
                  <p className="font-medium">{account.role}</p>
                  <p className="text-xs text-slate-600">
                    <code className="font-mono">{account.email}</code> · mật khẩu{' '}
                    <code className="font-mono">{account.password}</code>
                  </p>
                  <p className="text-xs text-slate-500">{account.note}</p>
                </div>
                <Button variant="secondary" size="sm" onClick={() => fillDemoAccount(account)}>
                  Điền tài khoản này
                </Button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
