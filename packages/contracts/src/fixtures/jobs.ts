/**
 * DEMO FIXTURE — Job nền (long-running request).
 *
 * MỤC ĐÍCH: demo cách UI theo dõi tiến độ THEO BƯỚC (không chỉ thanh %), và
 * cách phân biệt job đang chạy / xong / lỗi có gợi ý / còn trong hàng đợi / đã huỷ.
 * Mọi `label` là tiếng Việt do backend trả về — UI hiển thị thẳng, không tự dịch.
 */

import type { Job } from '../common';
import { JOB_KINDS, JOB_STATUSES, JOB_STEP_STATUSES } from '../enums';
import {
  DOC_FB_FANPAGE_REPORT,
  DOC_FB_SCAN_BROCHURE,
  EXPORT_QUEUED,
  JOB_BRAND_EXTRACT_SUCCEEDED,
  JOB_DOC_INGEST_CANCELLED,
  JOB_DOC_INGEST_FAILED,
  JOB_DOC_INGEST_RUNNING,
  JOB_EXPORT_QUEUED,
  WS_FB,
  demoAgo,
  demoAhead,
} from './ids';

/**
 * `demoJobs` — 5 job phủ các trạng thái UI cần xử lý riêng:
 * 1. RUNNING có tiến độ từng bước (đọc báo cáo Fanpage).
 * 2. SUCCEEDED có `result` để UI điều hướng sang kết quả.
 * 3. FAILED có `error.hint` tiếng Việt nói người dùng nên làm gì.
 * 4. QUEUED chưa bắt đầu — mọi bước còn `pending`.
 * 5. CANCELLED — có bước `skipped`, không phải bước nào cũng chạy.
 */
export const demoJobs: Job[] = [
  {
    id: JOB_DOC_INGEST_RUNNING,
    kind: JOB_KINDS.DOCUMENT_INGEST,
    status: JOB_STATUSES.RUNNING,
    title: 'Đang đọc tài liệu “bao-cao-fanpage-thang-2.pdf”',
    progress: 45,
    steps: [
      {
        key: 'receive_file',
        label: 'Nhận tệp tải lên',
        status: JOB_STEP_STATUSES.SUCCEEDED,
        progress: 100,
        message: 'Đã nhận 1,2 MB.',
        started_at: demoAgo({ minutes: 8 }),
        finished_at: demoAgo({ minutes: 8 }),
      },
      {
        key: 'detect_type',
        label: 'Nhận dạng định dạng tệp',
        status: JOB_STEP_STATUSES.SUCCEEDED,
        progress: 100,
        message: 'PDF có lớp văn bản, không cần OCR.',
        started_at: demoAgo({ minutes: 8 }),
        finished_at: demoAgo({ minutes: 7 }),
      },
      {
        key: 'extract_text',
        label: 'Đọc nội dung văn bản',
        status: JOB_STEP_STATUSES.RUNNING,
        progress: 45,
        message: 'Đã đọc 5/12 trang.',
        started_at: demoAgo({ minutes: 7 }),
      },
      {
        key: 'chunk_and_index',
        label: 'Chia đoạn và lập chỉ mục tra cứu',
        status: JOB_STEP_STATUSES.PENDING,
      },
      {
        key: 'extract_brand_fields',
        label: 'Trích xuất thông tin thương hiệu',
        status: JOB_STEP_STATUSES.PENDING,
      },
    ],
    created_at: demoAgo({ minutes: 8 }),
    started_at: demoAgo({ minutes: 8 }),
    cancellable: true,
    expires_at: demoAhead({ days: 7 }),
  },

  {
    id: JOB_BRAND_EXTRACT_SUCCEEDED,
    kind: JOB_KINDS.BRAND_EXTRACT,
    status: JOB_STATUSES.SUCCEEDED,
    title: 'Trích xuất Brand Profile từ hồ sơ thương hiệu',
    progress: 100,
    steps: [
      {
        key: 'load_documents',
        label: 'Nạp tài liệu đã xử lý',
        status: JOB_STEP_STATUSES.SUCCEEDED,
        progress: 100,
        message: 'Dùng 2 tài liệu: hồ sơ thương hiệu và thực đơn.',
        started_at: demoAgo({ days: 28, hours: 6 }),
        finished_at: demoAgo({ days: 28, hours: 6 }),
      },
      {
        key: 'extract_fields',
        label: 'Trích xuất 10 trường thông tin',
        status: JOB_STEP_STATUSES.SUCCEEDED,
        progress: 100,
        message: 'Điền được 9/10 trường, 2 trường cần bạn xác nhận.',
        started_at: demoAgo({ days: 28, hours: 6 }),
        finished_at: demoAgo({ days: 28, hours: 5, minutes: 56 }),
      },
      {
        key: 'attach_provenance',
        label: 'Gắn trích dẫn nguồn cho từng trường',
        status: JOB_STEP_STATUSES.SUCCEEDED,
        progress: 100,
        started_at: demoAgo({ days: 28, hours: 5, minutes: 56 }),
        finished_at: demoAgo({ days: 28, hours: 5, minutes: 55 }),
      },
    ],
    result: {
      workspace_id: WS_FB,
      brand_profile_version: 4,
      field_count: 10,
      suggested_count: 2,
      missing_count: 1,
    },
    created_at: demoAgo({ days: 28, hours: 6, minutes: 2 }),
    started_at: demoAgo({ days: 28, hours: 6 }),
    finished_at: demoAgo({ days: 28, hours: 5, minutes: 55 }),
    cancellable: false,
    expires_at: demoAhead({ days: 60 }),
  },

  {
    id: JOB_DOC_INGEST_FAILED,
    kind: JOB_KINDS.DOCUMENT_INGEST,
    status: JOB_STATUSES.FAILED,
    title: 'Đọc tài liệu “to-roi-khai-truong-ban-scan.pdf”',
    progress: 100,
    steps: [
      {
        key: 'receive_file',
        label: 'Nhận tệp tải lên',
        status: JOB_STEP_STATUSES.SUCCEEDED,
        progress: 100,
        started_at: demoAgo({ days: 12, hours: 4 }),
        finished_at: demoAgo({ days: 12, hours: 4 }),
      },
      {
        key: 'detect_type',
        label: 'Nhận dạng định dạng tệp',
        status: JOB_STEP_STATUSES.SUCCEEDED,
        progress: 100,
        message: 'Tệp là PDF nhưng chỉ chứa ảnh scan.',
        started_at: demoAgo({ days: 12, hours: 4 }),
        finished_at: demoAgo({ days: 12, hours: 3, minutes: 59 }),
      },
      {
        key: 'extract_text',
        label: 'Đọc nội dung văn bản',
        status: JOB_STEP_STATUSES.FAILED,
        progress: 100,
        message: 'Không tìm thấy lớp văn bản nào trong tệp.',
        started_at: demoAgo({ days: 12, hours: 3, minutes: 59 }),
        finished_at: demoAgo({ days: 12, hours: 3, minutes: 58 }),
        error: {
          code: 'pdf_no_text_layer',
          message: 'PDF không có lớp văn bản (là ảnh scan).',
        },
      },
      {
        key: 'chunk_and_index',
        label: 'Chia đoạn và lập chỉ mục tra cứu',
        status: JOB_STEP_STATUSES.SKIPPED,
        message: 'Bỏ qua vì bước đọc nội dung đã lỗi.',
      },
      {
        key: 'extract_brand_fields',
        label: 'Trích xuất thông tin thương hiệu',
        status: JOB_STEP_STATUSES.SKIPPED,
        message: 'Bỏ qua vì bước đọc nội dung đã lỗi.',
      },
    ],
    result: { document_id: DOC_FB_SCAN_BROCHURE },
    error: {
      code: 'pdf_no_text_layer',
      message:
        'Không đọc được nội dung tệp “to-roi-khai-truong-ban-scan.pdf” vì đây là bản scan ảnh, không có lớp văn bản.',
      hint: 'Hãy tải lên bản PDF có thể chọn/copy chữ (xuất lại từ Word hoặc Canva), hoặc nhập tay nội dung tờ rơi.',
      retryable: true,
    },
    created_at: demoAgo({ days: 12, hours: 4, minutes: 1 }),
    started_at: demoAgo({ days: 12, hours: 4 }),
    finished_at: demoAgo({ days: 12, hours: 3, minutes: 58 }),
    cancellable: false,
    expires_at: demoAhead({ days: 18 }),
  },

  {
    id: JOB_EXPORT_QUEUED,
    kind: JOB_KINDS.EXPORT_BUILD,
    status: JOB_STATUSES.QUEUED,
    title: 'Đang chờ dựng tệp CSV lịch nội dung',
    progress: 0,
    steps: [
      {
        key: 'collect_posts',
        label: 'Tập hợp bài viết trong chiến dịch',
        status: JOB_STEP_STATUSES.PENDING,
      },
      {
        key: 'build_rows',
        label: 'Dựng bảng dữ liệu',
        status: JOB_STEP_STATUSES.PENDING,
      },
      {
        key: 'write_file',
        label: 'Ghi tệp và tạo link tải',
        status: JOB_STEP_STATUSES.PENDING,
      },
    ],
    result: { export_id: EXPORT_QUEUED },
    created_at: demoAgo({ minutes: 2 }),
    cancellable: true,
    expires_at: demoAhead({ days: 7 }),
  },

  {
    id: JOB_DOC_INGEST_CANCELLED,
    kind: JOB_KINDS.DOCUMENT_INGEST,
    status: JOB_STATUSES.CANCELLED,
    title: 'Đọc tài liệu “bao-cao-fanpage-thang-2.pdf” (bản tải lên lần trước)',
    progress: 20,
    steps: [
      {
        key: 'receive_file',
        label: 'Nhận tệp tải lên',
        status: JOB_STEP_STATUSES.SUCCEEDED,
        progress: 100,
        started_at: demoAgo({ minutes: 26 }),
        finished_at: demoAgo({ minutes: 26 }),
      },
      {
        key: 'detect_type',
        label: 'Nhận dạng định dạng tệp',
        status: JOB_STEP_STATUSES.SUCCEEDED,
        progress: 100,
        started_at: demoAgo({ minutes: 26 }),
        finished_at: demoAgo({ minutes: 25 }),
      },
      {
        key: 'extract_text',
        label: 'Đọc nội dung văn bản',
        status: JOB_STEP_STATUSES.SKIPPED,
        message: 'Người dùng đã huỷ job trước khi bước này chạy.',
      },
      {
        key: 'chunk_and_index',
        label: 'Chia đoạn và lập chỉ mục tra cứu',
        status: JOB_STEP_STATUSES.SKIPPED,
      },
      {
        key: 'extract_brand_fields',
        label: 'Trích xuất thông tin thương hiệu',
        status: JOB_STEP_STATUSES.SKIPPED,
      },
    ],
    result: { document_id: DOC_FB_FANPAGE_REPORT },
    created_at: demoAgo({ minutes: 27 }),
    started_at: demoAgo({ minutes: 26 }),
    finished_at: demoAgo({ minutes: 24 }),
    cancellable: false,
    expires_at: demoAhead({ days: 7 }),
  },
];
