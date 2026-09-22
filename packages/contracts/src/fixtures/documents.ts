/**
 * DEMO FIXTURE — Tài liệu đã tải lên (Brand knowledge) & hạn mức upload.
 *
 * MỤC ĐÍCH: phủ HẾT các trạng thái mà người dùng có thể gặp, để không màn hình
 * nào phải tự bịa dữ liệu:
 * - `ready`      : đọc được, có `extracted` (số trang/dòng/ký tự).
 * - `processing` : đang đọc, có `job_id` để UI theo dõi tiến độ.
 * - `uploading`  : đang tải lên, có `progress` trung gian.
 * - `pending`    : vừa chọn tệp, chưa bắt đầu tải.
 * - `failed`     : lỗi có mã + thông điệp + gợi ý tiếng Việt
 *                  (`pdf_no_text_layer`, `file_too_large`, `ocr_failed`, `empty_content`).
 * - `unsupported`: định dạng chưa hỗ trợ (tệp .psd).
 * Workspace rỗng cố tình để `[]` → demo empty state "chưa có tài liệu nào".
 */

import type { DocumentUpload, UploadLimits } from '../brand';
import { DOCUMENT_ERROR_CODES, DOCUMENT_KINDS, DOCUMENT_STATUSES } from '../enums';
import {
  DOC_FB_BANNER_PSD,
  DOC_FB_BRAND_GUIDE,
  DOC_FB_FANPAGE_REPORT,
  DOC_FB_INTERIOR_PHOTO,
  DOC_FB_MENU,
  DOC_FB_MENU_PHOTO,
  DOC_FB_SCAN_BROCHURE,
  DOC_RETAIL_CATALOG,
  DOC_RETAIL_EMPTY_CSV,
  DOC_RETAIL_PRICE_PHOTO,
  DOC_RETAIL_QUOTE_UPLOADING,
  DOC_RETAIL_SUPPLIER_CSV,
  JOB_BRAND_EXTRACT_SUCCEEDED,
  JOB_DOC_INGEST_FAILED,
  JOB_DOC_INGEST_RUNNING,
  USR_EDITOR_MINH,
  USR_OWNER_HUONG,
  WS_EMPTY,
  WS_FB,
  WS_RETAIL,
  demoAgo,
  type DemoWorkspaceId,
} from './ids';

/**
 * Hạn mức upload do backend công bố: 25 MB, 5 tệp mỗi lần. UI đọc để chặn
 * TRƯỚC khi người dùng chọn tệp, thay vì để họ tải lên rồi mới báo lỗi.
 */
export const demoUploadLimits: UploadLimits = {
  max_file_size_bytes: 26_214_400, // 25 MB
  max_files_per_request: 5,
  accepted_kinds: [
    DOCUMENT_KINDS.PDF,
    DOCUMENT_KINDS.DOCX,
    DOCUMENT_KINDS.XLSX,
    DOCUMENT_KINDS.CSV,
    DOCUMENT_KINDS.TXT,
    DOCUMENT_KINDS.IMAGE,
  ],
  accepted_mime_types: [
    'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv',
    'text/plain',
    'image/jpeg',
    'image/png',
    'image/webp',
  ],
};

/** Tài liệu theo workspace. Quán phở có đủ 7 trạng thái, tạp hoá có 5, workspace mới rỗng. */
export const demoDocuments: Record<DemoWorkspaceId, DocumentUpload[]> = {
  [WS_FB]: [
    {
      // READY — nguồn chính của Brand Profile (có lớp text, trích được 12 trang).
      id: DOC_FB_BRAND_GUIDE,
      workspace_id: WS_FB,
      filename: 'ho-so-thuong-hieu-pho-bac-co-huong-2026.pdf',
      kind: DOCUMENT_KINDS.PDF,
      mime_type: 'application/pdf',
      size: 2_418_336,
      status: DOCUMENT_STATUSES.READY,
      progress: 100,
      job_id: JOB_BRAND_EXTRACT_SUCCEEDED,
      extracted: { pages: 12, characters: 28_450 },
      uploaded_by: USR_OWNER_HUONG,
      uploaded_at: demoAgo({ days: 30, hours: 3 }),
      processed_at: demoAgo({ days: 30, hours: 2, minutes: 57 }),
    },
    {
      // READY — tệp bảng tính: đếm theo DÒNG chứ không theo trang.
      id: DOC_FB_MENU,
      workspace_id: WS_FB,
      filename: 'thuc-don-thang-3-2026.xlsx',
      kind: DOCUMENT_KINDS.XLSX,
      mime_type:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      size: 186_240,
      status: DOCUMENT_STATUSES.READY,
      progress: 100,
      extracted: { rows: 48, characters: 6_120 },
      uploaded_by: USR_EDITOR_MINH,
      uploaded_at: demoAgo({ days: 28, hours: 6 }),
      processed_at: demoAgo({ days: 28, hours: 6 }),
    },
    {
      // PROCESSING — đang đọc, UI phải hiện tiến độ theo bước qua `job_id`.
      id: DOC_FB_FANPAGE_REPORT,
      workspace_id: WS_FB,
      filename: 'bao-cao-fanpage-thang-2.pdf',
      kind: DOCUMENT_KINDS.PDF,
      mime_type: 'application/pdf',
      size: 1_204_512,
      status: DOCUMENT_STATUSES.PROCESSING,
      progress: 45,
      job_id: JOB_DOC_INGEST_RUNNING,
      uploaded_by: USR_EDITOR_MINH,
      uploaded_at: demoAgo({ minutes: 8 }),
    },
    {
      // FAILED / pdf_no_text_layer — PDF scan: đọc được ảnh nhưng không có chữ.
      id: DOC_FB_SCAN_BROCHURE,
      workspace_id: WS_FB,
      filename: 'to-roi-khai-truong-ban-scan.pdf',
      kind: DOCUMENT_KINDS.PDF,
      mime_type: 'application/pdf',
      size: 8_912_400,
      status: DOCUMENT_STATUSES.FAILED,
      progress: 100,
      job_id: JOB_DOC_INGEST_FAILED,
      error: {
        code: DOCUMENT_ERROR_CODES.PDF_NO_TEXT_LAYER,
        message:
          'Tệp PDF này là ảnh scan nên không có lớp văn bản để đọc. Quán cần bản có thể chọn/copy chữ.',
        hint: 'Hãy xuất lại tờ rơi từ Word/Canva thành PDF có chữ, hoặc nhập tay nội dung cần thiết.',
      },
      extracted: { pages: 4, images: 4, characters: 0 },
      uploaded_by: USR_OWNER_HUONG,
      uploaded_at: demoAgo({ days: 12, hours: 4 }),
      processed_at: demoAgo({ days: 12, hours: 3, minutes: 58 }),
    },
    {
      // FAILED / file_too_large — 43,9 MB > hạn mức 25 MB. Lỗi chặn ngay, không xử lý.
      id: DOC_FB_MENU_PHOTO,
      workspace_id: WS_FB,
      filename: 'anh-menu-goc-chup-tay.jpg',
      kind: DOCUMENT_KINDS.IMAGE,
      mime_type: 'image/jpeg',
      size: 43_981_120,
      status: DOCUMENT_STATUSES.FAILED,
      progress: 0,
      error: {
        code: DOCUMENT_ERROR_CODES.FILE_TOO_LARGE,
        message:
          'Tệp nặng 43,9 MB, vượt hạn mức 25 MB cho mỗi tệp nên quán chưa tải lên được.',
        hint: 'Hãy nén ảnh về dưới 25 MB (hoặc giảm còn 2000 px chiều rộng) rồi tải lên lại.',
      },
      uploaded_by: USR_OWNER_HUONG,
      uploaded_at: demoAgo({ days: 11, hours: 2 }),
    },
    {
      // UNSUPPORTED — tệp thiết kế .psd: đã nhận tệp nhưng định dạng chưa hỗ trợ.
      id: DOC_FB_BANNER_PSD,
      workspace_id: WS_FB,
      filename: 'banner-khai-truong-chi-nhanh-2.psd',
      kind: DOCUMENT_KINDS.IMAGE,
      mime_type: 'image/vnd.adobe.photoshop',
      size: 15_728_640,
      status: DOCUMENT_STATUSES.UNSUPPORTED,
      progress: 0,
      error: {
        code: DOCUMENT_ERROR_CODES.UNSUPPORTED_TYPE,
        message:
          'Định dạng .psd (tệp thiết kế Photoshop) chưa được hỗ trợ nên quán không đọc được nội dung.',
        hint: 'Hãy xuất bản thiết kế sang PDF hoặc PNG rồi tải lên lại.',
      },
      uploaded_by: USR_EDITOR_MINH,
      uploaded_at: demoAgo({ days: 9, hours: 5 }),
    },
    {
      // PENDING — người dùng vừa chọn tệp, chưa bắt đầu tải lên (progress = 0).
      id: DOC_FB_INTERIOR_PHOTO,
      workspace_id: WS_FB,
      filename: 'anh-khong-gian-quan-01.jpg',
      kind: DOCUMENT_KINDS.IMAGE,
      mime_type: 'image/jpeg',
      size: 3_120_000,
      status: DOCUMENT_STATUSES.PENDING,
      progress: 0,
      uploaded_by: USR_OWNER_HUONG,
      uploaded_at: demoAgo({ minutes: 3 }),
    },
  ],

  [WS_RETAIL]: [
    {
      // READY — CSV hoá đơn nhà cung cấp: chỉ có số dòng.
      id: DOC_RETAIL_SUPPLIER_CSV,
      workspace_id: WS_RETAIL,
      filename: 'hoa-don-nha-cung-cap-thang-2.csv',
      kind: DOCUMENT_KINDS.CSV,
      mime_type: 'text/csv',
      size: 74_310,
      status: DOCUMENT_STATUSES.READY,
      progress: 100,
      extracted: { rows: 132, characters: 9_840 },
      uploaded_by: USR_EDITOR_MINH,
      uploaded_at: demoAgo({ days: 17, hours: 4 }),
      processed_at: demoAgo({ days: 17, hours: 4 }),
    },
    {
      // READY — danh mục sản phẩm, nguồn của trường `products` (đang ở mức gợi ý).
      id: DOC_RETAIL_CATALOG,
      workspace_id: WS_RETAIL,
      filename: 'danh-muc-san-pham-an-nhien.xlsx',
      kind: DOCUMENT_KINDS.XLSX,
      mime_type:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      size: 268_800,
      status: DOCUMENT_STATUSES.READY,
      progress: 100,
      extracted: { rows: 264, characters: 14_260 },
      uploaded_by: USR_EDITOR_MINH,
      uploaded_at: demoAgo({ days: 16, hours: 1 }),
      processed_at: demoAgo({ days: 16, hours: 1 }),
    },
    {
      // UPLOADING — đang tải lên, tiến độ trung gian 62% (UI hiện thanh %).
      id: DOC_RETAIL_QUOTE_UPLOADING,
      workspace_id: WS_RETAIL,
      filename: 'bao-gia-nha-cung-cap-quy-2.xlsx',
      kind: DOCUMENT_KINDS.XLSX,
      mime_type:
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      size: 512_000,
      status: DOCUMENT_STATUSES.UPLOADING,
      progress: 62,
      uploaded_by: USR_EDITOR_MINH,
      uploaded_at: demoAgo({ minutes: 1 }),
    },
    {
      // FAILED / ocr_failed — ảnh chụp bảng giá bị mờ, không đọc được chữ.
      id: DOC_RETAIL_PRICE_PHOTO,
      workspace_id: WS_RETAIL,
      filename: 'anh-bang-gia-chup-voi-dien-thoai.jpg',
      kind: DOCUMENT_KINDS.IMAGE,
      mime_type: 'image/jpeg',
      size: 2_048_000,
      status: DOCUMENT_STATUSES.FAILED,
      progress: 100,
      error: {
        code: DOCUMENT_ERROR_CODES.OCR_FAILED,
        message:
          'Ảnh bị mờ và nghiêng nên không đọc được chữ trên bảng giá.',
        hint: 'Hãy chụp lại ở nơi đủ sáng, giữ máy thẳng và lấy trọn bảng giá, hoặc nhập tay bảng giá.',
      },
      extracted: { images: 1, characters: 0 },
      uploaded_by: USR_EDITOR_MINH,
      uploaded_at: demoAgo({ days: 5, hours: 7 }),
      processed_at: demoAgo({ days: 5, hours: 7 }),
    },
    {
      // FAILED / empty_content — tệp CSV chỉ có dòng tiêu đề, không có dữ liệu.
      id: DOC_RETAIL_EMPTY_CSV,
      workspace_id: WS_RETAIL,
      filename: 'ton-kho-thang-3.csv',
      kind: DOCUMENT_KINDS.CSV,
      mime_type: 'text/csv',
      size: 128,
      status: DOCUMENT_STATUSES.FAILED,
      progress: 100,
      error: {
        code: DOCUMENT_ERROR_CODES.EMPTY_CONTENT,
        message: 'Tệp chỉ có dòng tiêu đề, không có dòng dữ liệu nào.',
        hint: 'Hãy xuất lại tệp tồn kho kèm dữ liệu rồi tải lên lại.',
      },
      extracted: { rows: 0, characters: 86 },
      uploaded_by: USR_EDITOR_MINH,
      uploaded_at: demoAgo({ days: 4, hours: 2 }),
      processed_at: demoAgo({ days: 4, hours: 2 }),
    },
  ],

  // Workspace mới: CHƯA có tài liệu nào → mọi màn hình brand knowledge hiện empty state.
  [WS_EMPTY]: [],
};
