import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { AppProviders } from '@/components/providers';
import { MockingProvider } from '@/components/mocking-provider';
import type { RuntimeConfig } from '@/lib/api/config';

import './globals.css';

/**
 * Trang nào cũng phải đọc runtime config theo từng request, nên không được
 * render tĩnh.
 */
export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'Agentic Marketing — Nền tảng marketing mạng xã hội cho doanh nghiệp nhỏ',
  description:
    'Nhập tài liệu doanh nghiệp, để AI soạn nội dung Facebook, duyệt và theo dõi hiệu quả.',
};

/**
 * Cấu hình được nhúng vào HTML LÚC CHẠY (không phải lúc build) để cùng một image
 * dùng được cho nhiều môi trường.
 *
 * ⚠️ Tên biến môi trường là `NEXT_PUBLIC_API_BASE_URL` và `NEXT_PUBLIC_USE_MOCKS`.
 * Khi viết compose/Dockerfile phải truyền đúng hai tên này.
 */
function readRuntimeConfig(): RuntimeConfig {
  return {
    apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? '',
    useMocks: process.env.NEXT_PUBLIC_USE_MOCKS === '1',
    environmentLabel: process.env.NEXT_PUBLIC_ENVIRONMENT_LABEL ?? '',
  };
}

export default function RootLayout({ children }: { children: ReactNode }) {
  const runtimeConfig = readRuntimeConfig();

  return (
    <html lang="vi">
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `window.__AGENTIC_RUNTIME_CONFIG__=${JSON.stringify(runtimeConfig)};`,
          }}
        />
      </head>
      <body className="min-h-screen antialiased">
        <AppProviders>
          {/* Bật mock TRƯỚC khi bất kỳ request nào chạy. */}
          <MockingProvider>{children}</MockingProvider>
        </AppProviders>
      </body>
    </html>
  );
}
