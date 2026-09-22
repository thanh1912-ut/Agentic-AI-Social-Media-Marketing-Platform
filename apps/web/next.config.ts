import path from 'node:path';
import type { NextConfig } from 'next';

/**
 * Cấu hình Next.js.
 *
 * `output: 'standalone'` là BẮT BUỘC để M2 đóng gói image: nó sinh ra
 * `.next/standalone` chỉ chứa đúng những gì cần để chạy.
 *
 * `outputFileTracingRoot` trỏ lên gốc repo vì đây là npm workspace —
 * `@agentic/contracts` nằm ngoài `apps/web` nên Next phải trace từ gốc.
 */
const nextConfig: NextConfig = {
  output: 'standalone',
  outputFileTracingRoot: path.join(__dirname, '../../'),
  reactStrictMode: true,
  poweredByHeader: false,
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  // `@agentic/contracts` là TypeScript nguồn, không qua bước build riêng.
  transpilePackages: ['@agentic/contracts'],
  eslint: {
    // Lint chạy ở lệnh `npm run lint` riêng, không chặn build.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
