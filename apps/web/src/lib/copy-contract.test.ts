/**
 * Cổng kiểm tra câu chữ và trạng thái bắt buộc.
 *
 * Test này đọc thẳng mã nguồn và KHÔNG cho phép một số câu/trạng thái sai quay
 * lại. Lý do tồn tại: những lỗi kiểu này không làm build đỏ, không làm test
 * logic đỏ — chúng chỉ âm thầm nói sai với người dùng. Cách duy nhất giữ được là
 * biến chúng thành lỗi build.
 *
 * Ý tưởng lấy từ repo tham chiếu `agenticAI_VNS_mkt` (`copy-contract.test.ts`).
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

import { describe, expect, it } from 'vitest';

const SRC = join(__dirname, '..');
const APP = join(SRC, 'app');

function walk(directory: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(directory)) {
    const full = join(directory, entry);
    if (statSync(full).isDirectory()) out.push(...walk(full));
    else out.push(full);
  }
  return out;
}

function read(path: string): string {
  return readFileSync(path, 'utf8');
}

const allSourceFiles = walk(SRC).filter(
  (path) =>
    (path.endsWith('.ts') || path.endsWith('.tsx')) &&
    !path.endsWith('.test.ts') &&
    !path.endsWith('.test.tsx'),
);

const pageFiles = walk(APP).filter((path) => path.endsWith('page.tsx'));

/**
 * Câu bị CẤM. Mỗi câu kèm lý do — nếu ai đó thực sự cần dùng, họ phải đọc lý do
 * trước khi gỡ khỏi danh sách này.
 */
const BANNED: Array<{ text: string; why: string }> = [
  {
    text: 'đã đăng thành công',
    why: 'Không được khẳng định bài đã lên Facebook khi chưa có permalink xác nhận từ backend.',
  },
  {
    text: 'chưa triển khai trong phiên bản này',
    why: 'Câu này từng bị dùng sai: tính năng có trong mã nguồn nhưng chưa bật ở triển khai. Phải nói rõ lý do cụ thể.',
  },
];

/**
 * Câu/đoạn mã BẮT BUỘC còn tồn tại. Nếu ai đó xoá, tính năng im lặng biến mất
 * khỏi giao diện.
 */
const REQUIRED: Array<{ file: string; text: string; why: string }> = [
  {
    file: 'components/ui.tsx',
    text: 'chưa xác định được tổng khối lượng',
    why: 'Thanh tiến độ phải có nhánh không xác định. Nếu thiếu, ai đó có thể bịa phần trăm.',
  },
  {
    file: 'components/ui.tsx',
    text: 'VersionConflictNotice',
    why: 'Xung đột phiên bản phải có lối thoát riêng, không được retry mù.',
  },
  {
    file: 'components/ui.tsx',
    text: 'DemoBadge',
    why: 'Dữ liệu demo phải luôn có nhãn nhìn thấy được.',
  },
  {
    file: 'components/session-gate.tsx',
    text: 'Phiên làm việc đã hết hạn',
    why: 'Phiên hết hạn phải được phân biệt với "chưa từng đăng nhập".',
  },
];

describe('cổng kiểm tra câu chữ', () => {
  it('không chứa câu bị cấm', () => {
    const offenders: string[] = [];

    for (const file of allSourceFiles) {
      const content = read(file);
      for (const rule of BANNED) {
        if (content.includes(rule.text)) {
          offenders.push(`${relative(SRC, file)} chứa “${rule.text}” — ${rule.why}`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it('giữ đủ các câu và component bắt buộc', () => {
    const missing: string[] = [];

    for (const rule of REQUIRED) {
      const content = read(join(SRC, rule.file));
      if (!content.includes(rule.text)) {
        missing.push(`${rule.file} thiếu “${rule.text}” — ${rule.why}`);
      }
    }

    expect(missing).toEqual([]);
  });

  it('thanh tiến độ không nhận phần trăm bịa', () => {
    const ui = read(join(SRC, 'components/ui.tsx'));

    // ProgressBar phải khai báo value là `number | null`.
    expect(ui).toMatch(/value:\s*number\s*\|\s*null/);
  });
});

describe('mọi màn hình phải có đủ trạng thái', () => {
  it('có ít nhất một màn hình để kiểm tra', () => {
    // Nếu không tìm thấy page nào thì cổng này vô nghĩa — báo lỗi thay vì im lặng.
    expect(pageFiles.length).toBeGreaterThan(0);
  });

  it.each(pageFiles.map((path) => [relative(SRC, path), path] as const))(
    '%s có trạng thái đang tải và lỗi',
    (_name, path) => {
      const content = read(path);
      const relativePath = relative(SRC, path);

      const hasLoading =
        content.includes('LoadingBlock') ||
        content.includes('SkeletonLines') ||
        content.includes('Spinner') ||
        content.includes('role="status"') ||
        // `Button loading` hiển thị spinner có role="status" — với form thì đây
        // chính là trạng thái đang xử lý, không cần thêm khối tải riêng.
        content.includes('loading={');
      expect(hasLoading, 'thiếu trạng thái đang tải').toBe(true);

      /*
       * Bề mặt lỗi có thể do trang tự render (`ErrorPanel`, `role="alert"`) hoặc
       * do `SessionGate` bọc ngoài — SessionGate đã render ErrorPanel và màn hình
       * hết phiên, nên trang uỷ quyền cho nó là hợp lệ.
       */
      const hasError =
        content.includes('ErrorPanel') ||
        content.includes('VersionConflictNotice') ||
        content.includes('role="alert"') ||
        content.includes('SessionGate');
      expect(hasError, 'thiếu trạng thái lỗi').toBe(true);
      expect(relativePath).toBeTruthy();
    },
  );

  /**
   * Trạng thái rỗng chỉ có nghĩa ở màn hình hiển thị danh sách dữ liệu.
   * Trang đăng nhập không có "danh sách rỗng" — bắt nó phải có EmptyState sẽ dẫn
   * tới việc thêm một khối rỗng vô nghĩa cho đủ test, làm hỏng UX thật.
   */
  const collectionPages = pageFiles.filter((path) =>
    relative(SRC, path).startsWith('app/w/'),
  );

  it.each(collectionPages.map((path) => [relative(SRC, path), path] as const))(
    '%s (màn hình danh sách) có trạng thái rỗng',
    (_name, path) => {
      const content = read(path);
      expect(content.includes('EmptyState'), 'thiếu trạng thái rỗng').toBe(true);
    },
  );

  it('có ít nhất một màn hình danh sách để kiểm tra trạng thái rỗng', () => {
    expect(collectionPages.length).toBeGreaterThan(0);
  });
});

describe('quy tắc an toàn dữ liệu', () => {
  it('không render số 0 thay cho dữ liệu thiếu', () => {
    const format = read(join(SRC, 'lib/format.ts'));

    // Các hàm định dạng số phải trả '—' khi giá trị null/undefined.
    expect(format).toContain("return '—'");
  });

  it('không gọi Meta hoặc LLM trực tiếp từ trình duyệt', () => {
    const offenders: string[] = [];

    for (const file of allSourceFiles) {
      // Bỏ qua tài liệu hợp đồng — chỉ kiểm tra mã chạy thật.
      if (file.includes(`${'lib'}/api`)) continue;
      const content = read(file);
      for (const host of ['graph.facebook.com', 'api.openai.com', 'api.anthropic.com']) {
        if (content.includes(host)) offenders.push(`${relative(SRC, file)} gọi thẳng ${host}`);
      }
    }

    expect(offenders).toEqual([]);
  });

  it('chỉ có duy nhất một tệp được gọi fetch', () => {
    const callers = allSourceFiles.filter((file) => {
      const content = read(file);
      return /\bfetch\s*\(/.test(content);
    });

    // `lib/api/client.ts` là nơi duy nhất được gọi fetch.
    // `app-shell.tsx` gọi logout qua fetch trực tiếp — nợ kỹ thuật đã biết,
    // sẽ chuyển sang `api.auth.logout` khi có màn hình đăng xuất riêng.
    const allowed = ['lib/api/client.ts', 'components/app-shell.tsx'];
    const unexpected = callers
      .map((file) => relative(SRC, file))
      .filter((name) => !allowed.includes(name));

    expect(unexpected).toEqual([]);
  });
});
