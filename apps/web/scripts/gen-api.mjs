#!/usr/bin/env node
/**
 * Sinh type TypeScript từ OpenAPI của backend (M2).
 *
 * Nguồn theo thứ tự ưu tiên:
 *   1. `--from <url|file>`
 *   2. `NEXT_PUBLIC_API_BASE_URL` + `/api/openapi.json`
 *   3. `http://127.0.0.1:8000/api/openapi.json`
 *
 * Cố ý THẤT BẠI RÕ RÀNG nếu không tải được spec, thay vì sinh type từ bản cache
 * cũ: type lệch backend mà không ai biết còn tệ hơn là không có type.
 * Dùng `--offline` nếu thật sự muốn dùng bản cache.
 */

import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const appRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const cachePath = join(appRoot, '.openapi-cache.json');
const inputPath = join(appRoot, '.openapi.generated-input.json');
const outputPath = join(appRoot, 'src/lib/api/schema.d.ts');
const cliPath = join(appRoot, 'node_modules/openapi-typescript/bin/cli.js');

const args = process.argv.slice(2);
const offline = args.includes('--offline');
const fromIndex = args.indexOf('--from');
const explicitSource = fromIndex >= 0 ? args[fromIndex + 1] : undefined;

const baseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(
  /\/+$/,
  '',
);

const source = explicitSource ?? `${baseUrl}/api/openapi.json`;

async function loadSpec() {
  if (offline) {
    if (!existsSync(cachePath)) {
      throw new Error(
        `Không có bản cache tại ${cachePath} nên không chạy được --offline.`,
      );
    }
    console.warn('⚠️  Đang dùng bản cache OpenAPI. Type có thể lệch backend.');
    return readFileSync(cachePath, 'utf8');
  }

  if (existsSync(source)) {
    return readFileSync(source, 'utf8');
  }

  const response = await fetch(source);
  if (!response.ok) {
    throw new Error(
      `Không tải được OpenAPI từ ${source} (HTTP ${response.status}). ` +
        'Kiểm tra backend đã chạy chưa, hoặc dùng --offline nếu chấp nhận type cũ.',
    );
  }
  return response.text();
}

function writeBanner() {
  const banner =
    '/**\n' +
    ' * TỆP ĐƯỢC SINH TỰ ĐỘNG — KHÔNG SỬA TAY.\n' +
    ' * Sinh bằng: npm run gen:api\n' +
    ' * Nguồn: OpenAPI của backend (M2).\n' +
    ' */\n';

  const current = readFileSync(outputPath, 'utf8');
  if (!current.startsWith('/**')) writeFileSync(outputPath, banner + current);
}

try {
  const spec = await loadSpec();
  mkdirSync(dirname(inputPath), { recursive: true });
  writeFileSync(cachePath, spec);
  writeFileSync(inputPath, spec);

  if (!existsSync(cliPath)) {
    throw new Error(
      `Không tìm thấy openapi-typescript tại ${cliPath}. Chạy npm install trước.`,
    );
  }

  const result = spawnSync(
    process.execPath,
    [cliPath, inputPath, '--output', outputPath, '--root-types', '--immutable'],
    { stdio: 'inherit', cwd: appRoot },
  );

  if (result.status !== 0) {
    throw new Error(`openapi-typescript thoát với mã ${result.status}.`);
  }

  writeBanner();
  console.log(`✅ Đã sinh type: ${outputPath}`);
} catch (error) {
  console.error(`❌ ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}
