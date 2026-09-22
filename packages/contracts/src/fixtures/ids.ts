/**
 * DEMO FIXTURE — Định danh & mốc thời gian cố định cho toàn bộ dữ liệu demo.
 *
 * Vì sao có file này: các màn hình demo cần trỏ vào CÙNG một đối tượng
 * (bài viết → bản xuất bản → số liệu → khuyến nghị) mà không cần backend.
 * Mọi fixture khác import id từ đây thay vì tự bịa chuỗi riêng.
 *
 * QUY ƯỚC BẮT BUỘC:
 * - Id là chuỗi cố định, đọc được. KHÔNG sinh ngẫu nhiên, KHÔNG UUID thật.
 * - Mọi mốc thời gian suy ra từ `DEMO_NOW`. KHÔNG dùng `Date.now()`,
 *   KHÔNG dùng `Math.random()` → chạy lại luôn ra đúng một kết quả.
 * - Đây là dữ liệu DEMO: nơi nào type cho phép `origin` thì luôn đặt `'demo'`.
 */

import type { DateString, Timestamp } from '../common';

// ---------------------------------------------------------------------------
// Mốc thời gian
// ---------------------------------------------------------------------------

/** "Bây giờ" của toàn bộ fixture: 16:00 giờ Việt Nam ngày 15/03/2026. */
export const DEMO_NOW: Timestamp = '2026-03-15T09:00:00Z';

/** Ngày "hôm nay" theo giờ Việt Nam, dạng `YYYY-MM-DD`. */
export const DEMO_TODAY: DateString = '2026-03-15';

/** Múi giờ dùng để cắt ngày khi tổng hợp số liệu (brief: giờ Việt Nam). */
export const DEMO_TIMEZONE = 'Asia/Ho_Chi_Minh';

const MS_PER_MINUTE = 60_000;
const MS_PER_DAY = 86_400_000;
const DEMO_NOW_MS = Date.parse(DEMO_NOW);

function toIso(ms: number): Timestamp {
  return new Date(ms).toISOString().replace(/\.\d{3}Z$/, 'Z');
}

/** Mốc thời gian TRONG QUÁ KHỨ so với `DEMO_NOW` (dùng cho dữ liệu đã xảy ra). */
export function demoAgo(offset: {
  days?: number;
  hours?: number;
  minutes?: number;
} = {}): Timestamp {
  const { days = 0, hours = 0, minutes = 0 } = offset;
  return toIso(DEMO_NOW_MS - (days * 24 * 60 + hours * 60 + minutes) * MS_PER_MINUTE);
}

/** Mốc thời gian TRONG TƯƠNG LAI so với `DEMO_NOW` (hẹn giờ, hết hạn token…). */
export function demoAhead(offset: {
  days?: number;
  hours?: number;
  minutes?: number;
} = {}): Timestamp {
  const { days = 0, hours = 0, minutes = 0 } = offset;
  return toIso(DEMO_NOW_MS + (days * 24 * 60 + hours * 60 + minutes) * MS_PER_MINUTE);
}

/** Ngày `YYYY-MM-DD` cách `DEMO_TODAY` `daysAgo` ngày về trước. */
export function demoDay(daysAgo = 0): DateString {
  return toIso(DEMO_NOW_MS - daysAgo * MS_PER_DAY).slice(0, 10);
}

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------

/** Workspace F&B — quán phở. Đây là workspace "đầy đủ" để demo luồng chính. */
export const WS_FB = 'ws_pho_bac_co_huong';

/** Workspace bán lẻ — tạp hoá. Đang nhập dở brand knowledge (onboarding giữa đường). */
export const WS_RETAIL = 'ws_tap_hoa_an_nhien';

/** Workspace mới tạo, chưa có gì — để demo mọi màn hình rỗng. */
export const WS_EMPTY = 'ws_moi_thanh_lap';

export const WORKSPACE_IDS = [WS_FB, WS_RETAIL, WS_EMPTY] as const;
export type DemoWorkspaceId = (typeof WORKSPACE_IDS)[number];

// ---------------------------------------------------------------------------
// Người dùng & thành viên
// ---------------------------------------------------------------------------

/** Chủ quán phở — người dùng đăng nhập trong bộ demo này (owner của WS_FB). */
export const USR_OWNER_HUONG = 'usr_nguyen_thi_huong';

/** Nhân viên marketing kiêm chủ tạp hoá — vai editor. */
export const USR_EDITOR_MINH = 'usr_tran_van_minh';

/** Kế toán — vai viewer, chỉ xem. */
export const USR_VIEWER_TRANG = 'usr_le_thu_trang';

/** Người được mời nhưng CHƯA tham gia (Member.status = 'invited'). */
export const USR_INVITED_HA = 'usr_pham_thu_ha';

/** Nhân viên cũ đã bị tạm ngưng (Member.status = 'suspended'). */
export const USR_SUSPENDED_TUAN = 'usr_do_anh_tuan';

export const MEM_FB_OWNER = 'mem_fb_huong_owner';
export const MEM_FB_EDITOR = 'mem_fb_minh_editor';
export const MEM_FB_VIEWER = 'mem_fb_trang_viewer';
export const MEM_RETAIL_OWNER = 'mem_retail_minh_owner';
export const MEM_RETAIL_EDITOR = 'mem_retail_huong_editor';
export const MEM_RETAIL_INVITED = 'mem_retail_ha_invited';
export const MEM_EMPTY_OWNER = 'mem_empty_minh_owner';
export const MEM_EMPTY_VIEWER = 'mem_empty_huong_viewer';
export const MEM_EMPTY_SUSPENDED = 'mem_empty_tuan_suspended';

// ---------------------------------------------------------------------------
// Tài liệu (Brand knowledge)
// ---------------------------------------------------------------------------

/** Hồ sơ thương hiệu dạng PDF có lớp text → trạng thái `ready`. */
export const DOC_FB_BRAND_GUIDE = 'doc_fb_ho_so_thuong_hieu_2026';

/** Thực đơn dạng XLSX → `ready`, nguồn của trường `products`. */
export const DOC_FB_MENU = 'doc_fb_thuc_don_thang_3_2026';

/** Báo cáo Fanpage tháng 2 (PDF) → đang `processing`, có `job_id`. */
export const DOC_FB_FANPAGE_REPORT = 'doc_fb_bao_cao_fanpage_thang_2';

/** Tờ rơi scan không có lớp text → `failed` / `pdf_no_text_layer`. */
export const DOC_FB_SCAN_BROCHURE = 'doc_fb_to_roi_scan_khong_co_text';

/** Ảnh menu gốc 42 MB → `failed` / `file_too_large`. */
export const DOC_FB_MENU_PHOTO = 'doc_fb_anh_menu_goc_dung_luong_lon';

/** Tệp thiết kế .psd → `unsupported` / `unsupported_type`. */
export const DOC_FB_BANNER_PSD = 'doc_fb_banner_khai_truong_psd';

/** Ảnh vừa chọn, chưa tải lên xong → `pending`. */
export const DOC_FB_INTERIOR_PHOTO = 'doc_fb_anh_khong_gian_quan';

/** Hoá đơn nhà cung cấp (CSV) của workspace bán lẻ → `ready`. */
export const DOC_RETAIL_SUPPLIER_CSV = 'doc_retail_hoa_don_nha_cung_cap';

/** Danh mục sản phẩm (XLSX) của workspace bán lẻ → `ready`. */
export const DOC_RETAIL_CATALOG = 'doc_retail_danh_muc_san_pham';

/** Ảnh chụp bảng giá bị mờ → `failed` / `ocr_failed`, không đọc được chữ. */
export const DOC_RETAIL_PRICE_PHOTO = 'doc_retail_anh_bang_gia_bi_mo';

/** Bảng báo giá đang được tải lên → `uploading`, tiến độ 62%. */
export const DOC_RETAIL_QUOTE_UPLOADING = 'doc_retail_bao_gia_dang_tai_len';

/** Tệp CSV rỗng của workspace bán lẻ → `failed` / `empty_content`. */
export const DOC_RETAIL_EMPTY_CSV = 'doc_retail_tep_rong';

// ---------------------------------------------------------------------------
// Job nền
// ---------------------------------------------------------------------------

/** Job đang chạy, có tiến độ từng bước — đọc báo cáo Fanpage. */
export const JOB_DOC_INGEST_RUNNING = 'job_doc_ingest_dang_chay';

/** Job đã xong — trích xuất Brand Profile. */
export const JOB_BRAND_EXTRACT_SUCCEEDED = 'job_brand_extract_hoan_tat';

/** Job thất bại — PDF scan không có lớp text. */
export const JOB_DOC_INGEST_FAILED = 'job_doc_ingest_that_bai';

/** Job đang chờ trong hàng đợi — dựng tệp export. */
export const JOB_EXPORT_QUEUED = 'job_export_dang_cho';

/** Job người dùng tự huỷ — để demo trạng thái `cancelled`. */
export const JOB_DOC_INGEST_CANCELLED = 'job_doc_ingest_da_huy';

// ---------------------------------------------------------------------------
// Sản phẩm & campaign
// ---------------------------------------------------------------------------

export const PROD_PHO_BO_TAI_NAM = 'prod_pho_bo_tai_nam';
export const PROD_PHO_GA_TA = 'prod_pho_ga_ta';
export const PROD_COMBO_TRUA = 'prod_combo_trua_van_phong';
export const PROD_PHO_CHAY_NAM = 'prod_pho_chay_nam_huong';
export const PROD_PHO_CUON = 'prod_pho_cuon_cua_bac';

export const PROD_RETAIL_GAO_ST25 = 'prod_gao_st25_tui_5kg';
export const PROD_RETAIL_DAU_AN = 'prod_dau_an_dau_nanh_1l';
export const PROD_RETAIL_NUOC_MAM = 'prod_nuoc_mam_ca_com_500ml';

/** Campaign đang chạy — "Combo trưa văn phòng". */
export const CMP_PHO_TRUA = 'cmp_combo_trua_van_phong_t3';

/** Campaign còn là bản nháp — "Khai trương chi nhánh 2". */
export const CMP_PHO_CHI_NHANH_2 = 'cmp_khai_truong_chi_nhanh_2';

// ---------------------------------------------------------------------------
// Bài viết (phủ hết POST_STATUSES)
// ---------------------------------------------------------------------------

/** `published`, đăng qua API — bài chủ lực của campaign combo trưa. */
export const POST_PUBLISHED_API = 'post_p01_combo_trua_dang_qua_api';

/** `published` nhưng người dùng tự đăng rồi ghi nhận lại (manual_recorded). */
export const POST_PUBLISHED_MANUAL = 'post_p02_khuyen_mai_8_3_dang_thu_cong';

/** `approved` — đang được gửi lên Facebook (publication `sending`). */
export const POST_APPROVED = 'post_p03_hau_truong_noi_nuoc_dung';

/** `approved` + `requires_reapproval: true` — sửa sau khi duyệt phải duyệt lại. */
export const POST_APPROVED_REAPPROVAL = 'post_p04_combo_trua_doi_gia';

/** `scheduled` — đã hẹn giờ 11:00 ngày 16/03. */
export const POST_SCHEDULED = 'post_p05_hen_gio_pho_chay';

/** `failed` — đăng lỗi, kết quả lần gửi thứ 2 chưa rõ. */
export const POST_FAILED = 'post_p06_uu_dai_khach_quen';

/** `needs_review` — đang chờ duyệt. */
export const POST_NEEDS_REVIEW = 'post_p07_pho_cuon_cho_duyet';

/** `rejected` — bị từ chối kèm lý do tiếng Việt. */
export const POST_REJECTED = 'post_p08_khuyen_mai_sai_gia_bi_tu_choi';

/** `draft` — bản nháp trong campaign khai trương chi nhánh 2. */
export const POST_DRAFT = 'post_p09_nhap_khai_truong_chi_nhanh_2';

export const POST_IDS = [
  POST_PUBLISHED_API,
  POST_PUBLISHED_MANUAL,
  POST_APPROVED,
  POST_APPROVED_REAPPROVAL,
  POST_SCHEDULED,
  POST_FAILED,
  POST_NEEDS_REVIEW,
  POST_REJECTED,
  POST_DRAFT,
] as const;
export type DemoPostId = (typeof POST_IDS)[number];

// ---------------------------------------------------------------------------
// Duyệt bài
// ---------------------------------------------------------------------------

export const APR_P01_APPROVED = 'apr_p01_duyet_ban_3';
export const APR_P02_APPROVED = 'apr_p02_duyet_ban_2';
export const APR_P03_APPROVED = 'apr_p03_duyet_ban_4';
export const APR_P04_APPROVED = 'apr_p04_duyet_ban_2';
export const APR_P05_APPROVED = 'apr_p05_duyet_ban_2';
export const APR_P06_APPROVED = 'apr_p06_duyet_ban_3';
export const APR_P08_REJECTED = 'apr_p08_tu_choi_ban_2';

// ---------------------------------------------------------------------------
// Kết nối & Page
// ---------------------------------------------------------------------------

/** Kết nối Facebook tốt, đủ quyền đăng bài. */
export const CONN_FB_OK = 'conn_fb_pho_bac_dang_hoat_dong';

/** Kết nối Facebook hỏng token — cần kết nối lại. */
export const CONN_FB_RECONNECT = 'conn_fb_pho_bac_can_ket_noi_lai';

/** Page chính của quán — đăng được. Id theo dạng số của Meta. */
export const PAGE_PHO_CHINH = '108452319776401';

/** Page chi nhánh 2 — chưa có quyền đăng. */
export const PAGE_PHO_CHI_NHANH_2 = '108452319776402';

/** Page của workspace bán lẻ — đã chọn nhưng thuộc workspace khác. */
export const PAGE_AN_NHIEN = '223987410556231';

// ---------------------------------------------------------------------------
// Xuất bản (Publication)
// ---------------------------------------------------------------------------

export const PUB_P01_PUBLISHED = 'pub_p01_da_dang_qua_api';
export const PUB_P02_MANUAL = 'pub_p02_ghi_nhan_dang_thu_cong';
export const PUB_P03_SENDING = 'pub_p03_dang_gui';
export const PUB_P04_NEEDS_RECONNECT = 'pub_p04_can_ket_noi_lai';
export const PUB_P05_PENDING = 'pub_p05_cho_gui_den_gio';
export const PUB_P06_FAILED = 'pub_p06_gui_loi_lan_1';
export const PUB_P06_OUTCOME_UNKNOWN = 'pub_p06_chua_ro_ket_qua_lan_2';

// ---------------------------------------------------------------------------
// Khuyến nghị
// ---------------------------------------------------------------------------

export const REC_CAROUSEL = 'rec_uu_tien_bai_nhieu_anh';
export const REC_GIO_DANG = 'rec_doi_gio_dang_sang_bua_trua';
export const REC_REEL = 'rec_reel_chua_du_du_lieu';
export const REC_DISMISSED = 'rec_giam_gia_sau_20h_da_bo_qua';

/** Bản nháp điều chỉnh brief do "Áp dụng khuyến nghị" tạo ra. */
export const BRIEF_DRAFT_CS2 = 'brief_draft_khai_truong_doi_khan_gia';
export const BRIEF_DRAFT_TRUA = 'brief_draft_combo_trua_them_cta';

/** Tệp export đã dựng xong. */
export const EXPORT_READY = 'export_combo_trua_thang_3_xlsx';
export const EXPORT_QUEUED = 'export_khai_truong_chi_nhanh_2_csv';
export const EXPORT_FAILED = 'export_bao_cao_hieu_suat_csv';
