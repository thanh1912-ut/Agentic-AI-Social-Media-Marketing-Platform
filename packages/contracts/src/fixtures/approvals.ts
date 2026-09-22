/**
 * DEMO FIXTURE — Lịch sử duyệt bài (`ApprovalRecord`).
 *
 * MỤC ĐÍCH: mỗi bản ghi trả lời được câu hỏi “AI đã duyệt ĐÚNG BẢN NÀO, lúc nào,
 * vì sao”. Vì vậy `version` luôn khớp với `PostVersion.approved_at/approved_by`
 * trong campaigns.ts.
 *
 * Điểm đáng chú ý cho UI:
 * - Bài p04 đã duyệt ở bản 2, sau đó bị sửa thành bản 3 → KHÔNG có bản ghi duyệt
 *   cho bản 3, nên bài phải hiện `requires_reapproval` và khoá nút đăng.
 * - Bài p07 (`needs_review`) chưa có bản ghi nào — đây là trạng thái “chờ duyệt”.
 */

import type { ApprovalRecord } from '../campaign.js';
import { APPROVAL_DECISIONS } from '../enums.js';
import {
  APR_P01_APPROVED,
  APR_P02_APPROVED,
  APR_P03_APPROVED,
  APR_P04_APPROVED,
  APR_P05_APPROVED,
  APR_P06_APPROVED,
  APR_P08_REJECTED,
  POST_APPROVED,
  POST_APPROVED_REAPPROVAL,
  POST_FAILED,
  POST_PUBLISHED_API,
  POST_PUBLISHED_MANUAL,
  POST_REJECTED,
  POST_SCHEDULED,
  USR_OWNER_HUONG,
  demoAgo,
} from './ids.js';

/**
 * 7 quyết định duyệt: 6 lần DUYỆT và 1 lần TỪ CHỐI (có lý do tiếng Việt).
 * Người duyệt là chủ quán — người duy nhất có quyền `post:approve`.
 */
export const demoApprovalRecords: ApprovalRecord[] = [
  {
    // Duyệt bản 3 (bản người viết) của bài combo trưa → sau đó đăng qua API.
    id: APR_P01_APPROVED,
    post_id: POST_PUBLISHED_API,
    version: 3,
    decision: APPROVAL_DECISIONS.APPROVED,
    decided_by: USR_OWNER_HUONG,
    decided_by_name: 'Nguyễn Thị Hương',
    decided_at: demoAgo({ days: 9, hours: 4 }),
  },
  {
    // Duyệt bản 2 của bài khuyến mãi 8/3 trước khi cô Hương tự đăng.
    id: APR_P02_APPROVED,
    post_id: POST_PUBLISHED_MANUAL,
    version: 2,
    decision: APPROVAL_DECISIONS.APPROVED,
    reason: 'Bài ấm áp, đúng dịp 8/3. Cô đồng ý đăng.',
    decided_by: USR_OWNER_HUONG,
    decided_by_name: 'Nguyễn Thị Hương',
    decided_at: demoAgo({ days: 8, hours: 1 }),
  },
  {
    // Duyệt bản 4 (bài hậu trường) — hiện đang được gửi lên Facebook.
    id: APR_P03_APPROVED,
    post_id: POST_APPROVED,
    version: 4,
    decision: APPROVAL_DECISIONS.APPROVED,
    reason: 'Ảnh thật của quán, câu mở đầu đúng giọng cô. Duyệt đăng ngay.',
    decided_by: USR_OWNER_HUONG,
    decided_by_name: 'Nguyễn Thị Hương',
    decided_at: demoAgo({ hours: 1 }),
  },
  {
    // Duyệt bản 2 của bài combo trưa đổi giá. Bản 3 sửa sau đó → cần duyệt lại.
    id: APR_P04_APPROVED,
    post_id: POST_APPROVED_REAPPROVAL,
    version: 2,
    decision: APPROVAL_DECISIONS.APPROVED,
    decided_by: USR_OWNER_HUONG,
    decided_by_name: 'Nguyễn Thị Hương',
    decided_at: demoAgo({ days: 3, hours: 8 }),
  },
  {
    // Duyệt bản 2 của bài phở chay để hẹn giờ đăng 11:00 ngày 16/03.
    id: APR_P05_APPROVED,
    post_id: POST_SCHEDULED,
    version: 2,
    decision: APPROVAL_DECISIONS.APPROVED,
    reason: 'Duyệt. Hẹn 11h trưa mai đăng cho khách văn phòng đọc.',
    decided_by: USR_OWNER_HUONG,
    decided_by_name: 'Nguyễn Thị Hương',
    decided_at: demoAgo({ days: 1, hours: 2 }),
  },
  {
    // Duyệt bản 3 của bài ưu đãi khách quen — sau đó việc gửi bài bị lỗi.
    id: APR_P06_APPROVED,
    post_id: POST_FAILED,
    version: 3,
    decision: APPROVAL_DECISIONS.APPROVED,
    decided_by: USR_OWNER_HUONG,
    decided_by_name: 'Nguyễn Thị Hương',
    decided_at: demoAgo({ days: 2, hours: 20 }),
  },
  {
    // TỪ CHỐI kèm lý do — UI phải hiển thị lý do này ngay trên thẻ bài.
    id: APR_P08_REJECTED,
    post_id: POST_REJECTED,
    version: 2,
    decision: APPROVAL_DECISIONS.REJECTED,
    reason:
      'Bài ghi “giảm 30% tất cả các món” nhưng tháng này quán chỉ giảm cho combo trưa. Minh sửa lại đúng mức giảm rồi gửi duyệt lại giúp cô nhé.',
    decided_by: USR_OWNER_HUONG,
    decided_by_name: 'Nguyễn Thị Hương',
    decided_at: demoAgo({ days: 1, hours: 4 }),
  },
];
