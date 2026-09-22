/**
 * DEMO FIXTURE — Kết nối Facebook, Page, và các lần xuất bản.
 *
 * MỤC ĐÍCH: demo những chỗ dễ gây mất dữ liệu hoặc đăng trùng nếu UI làm sai:
 * - Kết nối `connected` có đủ `capabilities` (kèm lý do khi một năng lực bị khoá).
 * - Kết nối `needs_reconnect` có `status_reason` tiếng Việt.
 * - Page `can_publish: false` kèm `cannot_publish_reason` (thiếu quyền Meta).
 * - `demoPublications` phủ HẾT `PUBLICATION_STATUSES`, trong đó:
 *   + `outcome_unknown`: `retry_allowed: false` + `requires_manual_reconciliation: true`
 *     → TUYỆT ĐỐI không hiện nút “Thử lại”, phải hướng dẫn đối soát thủ công;
 *   + `manual_recorded`: người dùng tự đăng rồi nhập URL.
 * - `demoPublicationEvents`: dòng thời gian giải thích chuyện gì đã xảy ra, để
 *   người dùng đối soát được (contract chưa gắn mảng này vào `Publication`).
 */

import type { Capability, Id } from '../common.js';
import type {
  FacebookPage,
  Publication,
  PublicationEvent,
  SocialConnection,
} from '../publishing.js';
import {
  CAPABILITY_KEYS,
  CONNECTION_STATUSES,
  PUBLICATION_SOURCES,
  PUBLICATION_STATUSES,
} from '../enums.js';
import {
  CONN_FB_OK,
  CONN_FB_RECONNECT,
  PAGE_AN_NHIEN,
  PAGE_PHO_CHI_NHANH_2,
  PAGE_PHO_CHINH,
  POST_APPROVED,
  POST_APPROVED_REAPPROVAL,
  POST_FAILED,
  POST_PUBLISHED_API,
  POST_PUBLISHED_MANUAL,
  POST_SCHEDULED,
  PUB_P01_PUBLISHED,
  PUB_P02_MANUAL,
  PUB_P03_SENDING,
  PUB_P04_NEEDS_RECONNECT,
  PUB_P05_PENDING,
  PUB_P06_FAILED,
  PUB_P06_OUTCOME_UNKNOWN,
  WS_FB,
  WS_RETAIL,
  demoAgo,
  demoAhead,
} from './ids.js';

// ---------------------------------------------------------------------------
// Kết nối
// ---------------------------------------------------------------------------

/**
 * 2 kết nối của quán phở: một TỐT (đăng được) và một HỎNG TOKEN (cần kết nối lại),
 * cộng thêm 1 kết nối đã HẾT HẠN của workspace bán lẻ để phủ `expired`.
 */
export const demoConnections: SocialConnection[] = [
  {
    // CONNECTED — đủ quyền đăng bài; chỉ thiếu quyền quản lý bình luận.
    id: CONN_FB_OK,
    workspace_id: WS_FB,
    provider: 'facebook',
    status: CONNECTION_STATUSES.CONNECTED,
    connected_by_name: 'Nguyễn Thị Hương',
    scopes: [
      'pages_show_list',
      'pages_read_engagement',
      'pages_manage_posts',
      'read_insights',
    ],
    selected_page_id: PAGE_PHO_CHINH,
    connected_at: demoAgo({ days: 40 }),
    expires_at: demoAhead({ days: 45 }),
    last_checked_at: demoAgo({ hours: 2 }),
    capabilities: [
      {
        key: CAPABILITY_KEYS.PUBLISH_NOW,
        available: true,
      },
      {
        key: CAPABILITY_KEYS.SCHEDULE,
        available: true,
      },
      {
        key: CAPABILITY_KEYS.SYNC_METRICS,
        available: true,
      },
      {
        key: CAPABILITY_KEYS.READ_INSIGHTS,
        available: true,
      },
      {
        // Không khoá im lặng: nói rõ vì sao và cần làm gì.
        key: CAPABILITY_KEYS.COMMENT_MODERATION,
        available: false,
        reason:
          'Kết nối hiện tại chưa có quyền quản lý bình luận trên Page “Phở Bắc Cô Hương”.',
        remedy:
          'Kết nối lại Facebook và bật quyền “Quản lý bình luận” (pages_manage_engagement) khi Meta hỏi.',
      },
    ],
  },
  {
    // NEEDS_RECONNECT — token Page hết hiệu lực: mọi năng lực gửi bài đều bị khoá.
    id: CONN_FB_RECONNECT,
    workspace_id: WS_FB,
    provider: 'facebook',
    status: CONNECTION_STATUSES.NEEDS_RECONNECT,
    connected_by_name: 'Trần Văn Minh',
    scopes: ['pages_show_list', 'pages_read_engagement', 'read_insights'],
    missing_scopes: ['pages_manage_posts'],
    selected_page_id: PAGE_PHO_CHINH,
    connected_at: demoAgo({ days: 35 }),
    expires_at: demoAgo({ days: 1, hours: 3 }),
    last_checked_at: demoAgo({ hours: 1 }),
    status_reason:
      'Token truy cập Page đã hết hiệu lực lúc 06:00 hôm nay, nên hệ thống chưa gửi được bài nào lên Facebook.',
    capabilities: [
      {
        key: CAPABILITY_KEYS.PUBLISH_NOW,
        available: false,
        reason: 'Kết nối Facebook đã hết hiệu lực.',
        remedy: 'Kết nối lại Facebook Page rồi bấm gửi bài lại.',
      },
      {
        key: CAPABILITY_KEYS.SCHEDULE,
        available: false,
        reason: 'Không hẹn giờ đăng bài được khi kết nối đã hết hiệu lực.',
        remedy: 'Kết nối lại Facebook Page.',
      },
      {
        key: CAPABILITY_KEYS.SYNC_METRICS,
        available: false,
        reason: 'Số liệu sẽ không đồng bộ cho tới khi kết nối lại.',
        remedy: 'Kết nối lại Facebook Page để tiếp tục đồng bộ số liệu.',
      },
      {
        key: CAPABILITY_KEYS.READ_INSIGHTS,
        available: true,
      },
      {
        key: CAPABILITY_KEYS.COMMENT_MODERATION,
        available: false,
        reason: 'Kết nối Facebook đã hết hiệu lực.',
        remedy: 'Kết nối lại Facebook Page.',
      },
    ],
  },
  {
    // EXPIRED — token cũ đã quá hạn từ lâu ở workspace bán lẻ (chưa kết nối lại).
    id: 'conn_fb_tap_hoa_an_nhien_het_han',
    workspace_id: WS_RETAIL,
    provider: 'facebook',
    status: CONNECTION_STATUSES.EXPIRED,
    connected_by_name: 'Trần Văn Minh',
    scopes: ['pages_show_list', 'pages_read_engagement'],
    missing_scopes: ['pages_manage_posts', 'read_insights'],
    connected_at: demoAgo({ days: 120 }),
    expires_at: demoAgo({ days: 60 }),
    last_checked_at: demoAgo({ days: 58 }),
    status_reason:
      'Kết nối đã hết hạn từ 60 ngày trước và chưa được gia hạn, nên cửa hàng chưa đăng bài tự động được.',
    capabilities: [
      {
        key: CAPABILITY_KEYS.PUBLISH_NOW,
        available: false,
        reason: 'Kết nối Facebook đã hết hạn.',
        remedy: 'Kết nối lại Facebook Page của Tạp hoá An Nhiên.',
      },
      {
        key: CAPABILITY_KEYS.SCHEDULE,
        available: false,
        reason: 'Kết nối Facebook đã hết hạn.',
        remedy: 'Kết nối lại Facebook Page.',
      },
      {
        key: CAPABILITY_KEYS.SYNC_METRICS,
        available: false,
        reason: 'Kết nối Facebook đã hết hạn nên không đồng bộ được số liệu.',
        remedy: 'Kết nối lại Facebook Page rồi đồng bộ số liệu.',
      },
      {
        key: CAPABILITY_KEYS.READ_INSIGHTS,
        available: false,
        reason: 'Kết nối Facebook đã hết hạn.',
        remedy: 'Kết nối lại Facebook Page.',
      },
      {
        key: CAPABILITY_KEYS.COMMENT_MODERATION,
        available: false,
        reason: 'Kết nối Facebook đã hết hạn.',
        remedy: 'Kết nối lại Facebook Page.',
      },
    ],
  },
];

/**
 * 3 Page mà tài khoản đang kết nối nhìn thấy:
 * - Page chính: đăng được, đang được chọn (4.218 người theo dõi — mức quán nhỏ).
 * - Page chi nhánh 2: `can_publish: false` + lý do thiếu quyền.
 * - Page của tạp hoá: thuộc workspace khác nên `already_selected: true`.
 */
export const demoFacebookPages: FacebookPage[] = [
  {
    id: PAGE_PHO_CHINH,
    name: 'Phở Bắc Cô Hương',
    picture_url: 'https://cdn.demo.local/pages/pho-bac-co-huong.jpg',
    category: 'Quán ăn',
    followers_count: 4_218,
    can_publish: true,
    already_selected: true,
  },
  {
    id: PAGE_PHO_CHI_NHANH_2,
    name: 'Phở Bắc Cô Hương – Chi nhánh Trần Duy Hưng',
    picture_url: 'https://cdn.demo.local/pages/pho-bac-chi-nhanh-2.jpg',
    category: 'Quán ăn',
    followers_count: 312,
    can_publish: false,
    cannot_publish_reason:
      'Tài khoản Facebook đang kết nối chưa được cấp quyền “pages_manage_posts” trên Page này. Hãy nhờ quản trị viên của Page cấp quyền rồi kết nối lại.',
  },
  {
    id: PAGE_AN_NHIEN,
    name: 'Tạp hoá An Nhiên',
    picture_url: 'https://cdn.demo.local/pages/tap-hoa-an-nhien.jpg',
    category: 'Cửa hàng tạp hoá',
    followers_count: 1_036,
    can_publish: true,
    already_selected: true,
  },
];

/** Trang Facebook của Page chính — dùng cho `permalink` của bài đã đăng. */
export const demoPageProfileUrl = 'https://www.facebook.com/phobaccohuong';

// ---------------------------------------------------------------------------
// Xuất bản
// ---------------------------------------------------------------------------

/**
 * 7 lần xuất bản, phủ ĐỦ `PUBLICATION_STATUSES`.
 * Lưu ý cách đọc: một bài có thể có NHIỀU bản ghi (mỗi lần gửi là một bản ghi),
 * nên bài p06 vừa có lần gửi lỗi vừa có lần gửi không rõ kết quả.
 */
export const demoPublications: Publication[] = [
  {
    // PUBLISHED — đăng thành công qua API.
    id: PUB_P01_PUBLISHED,
    post_id: POST_PUBLISHED_API,
    post_version: 3,
    channel: 'facebook_page',
    page_id: PAGE_PHO_CHINH,
    page_name: 'Phở Bắc Cô Hương',
    status: PUBLICATION_STATUSES.PUBLISHED,
    source: PUBLICATION_SOURCES.API,
    permalink: `${demoPageProfileUrl}/posts/122145678901234567`,
    published_at: demoAgo({ days: 9, hours: 4 }),
    sent_at: demoAgo({ days: 9, hours: 4 }),
    external_post_id: '108452319776401_122145678901234567',
    attempt_count: 1,
    retry_allowed: false,
    requires_manual_reconciliation: false,
    created_at: demoAgo({ days: 9, hours: 4, minutes: 1 }),
    updated_at: demoAgo({ days: 9, hours: 4 }),
  },
  {
    // MANUAL_RECORDED — người dùng tự đăng trên Facebook rồi nhập lại URL + giờ đăng.
    id: PUB_P02_MANUAL,
    post_id: POST_PUBLISHED_MANUAL,
    post_version: 2,
    channel: 'facebook_page',
    page_id: PAGE_PHO_CHINH,
    page_name: 'Phở Bắc Cô Hương',
    status: PUBLICATION_STATUSES.MANUAL_RECORDED,
    source: PUBLICATION_SOURCES.MANUAL,
    permalink: `${demoPageProfileUrl}/posts/122145678901298765`,
    published_at: demoAgo({ days: 8, hours: 1 }),
    attempt_count: 0,
    retry_allowed: false,
    requires_manual_reconciliation: false,
    created_at: demoAgo({ days: 8, hours: 1 }),
    updated_at: demoAgo({ days: 8, hours: 1 }),
  },
  {
    // SENDING — đang gửi, chưa có kết quả; UI chỉ được hiện “Đang gửi…”.
    id: PUB_P03_SENDING,
    post_id: POST_APPROVED,
    post_version: 4,
    channel: 'facebook_page',
    page_id: PAGE_PHO_CHINH,
    page_name: 'Phở Bắc Cô Hương',
    status: PUBLICATION_STATUSES.SENDING,
    source: PUBLICATION_SOURCES.API,
    sent_at: demoAgo({ minutes: 4 }),
    attempt_count: 1,
    retry_allowed: false,
    requires_manual_reconciliation: false,
    created_at: demoAgo({ minutes: 5 }),
    updated_at: demoAgo({ minutes: 4 }),
  },
  {
    // NEEDS_RECONNECT — token hỏng: phải kết nối lại rồi mới gửi tiếp.
    id: PUB_P04_NEEDS_RECONNECT,
    post_id: POST_APPROVED_REAPPROVAL,
    post_version: 3,
    channel: 'facebook_page',
    page_id: PAGE_PHO_CHINH,
    page_name: 'Phở Bắc Cô Hương',
    status: PUBLICATION_STATUSES.NEEDS_RECONNECT,
    source: PUBLICATION_SOURCES.API,
    error: {
      code: 'token_expired',
      message:
        'Token truy cập Page đã hết hiệu lực nên hệ thống chưa gửi được bài lên Facebook.',
      hint: 'Hãy vào mục Kết nối để kết nối lại Facebook Page, sau đó bấm gửi lại.',
    },
    attempt_count: 1,
    retry_allowed: false,
    requires_manual_reconciliation: false,
    created_at: demoAgo({ hours: 19 }),
    updated_at: demoAgo({ hours: 19 }),
  },
  {
    // PENDING — bài đã hẹn giờ, đang chờ đến 11:00 ngày 16/03 để gửi.
    id: PUB_P05_PENDING,
    post_id: POST_SCHEDULED,
    post_version: 2,
    channel: 'facebook_page',
    page_id: PAGE_PHO_CHINH,
    page_name: 'Phở Bắc Cô Hương',
    status: PUBLICATION_STATUSES.PENDING,
    source: PUBLICATION_SOURCES.API,
    attempt_count: 0,
    retry_allowed: false,
    requires_manual_reconciliation: false,
    created_at: demoAgo({ days: 1, hours: 2 }),
    updated_at: demoAgo({ days: 1, hours: 2 }),
  },
  {
    // FAILED — lần gửi thứ nhất bị Facebook chặn tạm thời; THỬ LẠI ĐƯỢC.
    id: PUB_P06_FAILED,
    post_id: POST_FAILED,
    post_version: 3,
    channel: 'facebook_page',
    page_id: PAGE_PHO_CHINH,
    page_name: 'Phở Bắc Cô Hương',
    status: PUBLICATION_STATUSES.FAILED,
    source: PUBLICATION_SOURCES.API,
    sent_at: demoAgo({ days: 2, hours: 8 }),
    error: {
      code: 'rate_limited',
      message:
        'Facebook tạm chặn yêu cầu đăng bài vì gửi quá nhanh. Bài CHƯA lên Facebook.',
      hint: 'Chờ khoảng 15 phút rồi bấm “Thử lại”.',
    },
    attempt_count: 1,
    retry_allowed: true,
    requires_manual_reconciliation: false,
    created_at: demoAgo({ days: 2, hours: 8 }),
    updated_at: demoAgo({ days: 2, hours: 8 }),
  },
  {
    // OUTCOME_UNKNOWN — GỬI RỒI NHƯNG KHÔNG RÕ KẾT QUẢ.
    // `retry_allowed: false`: thử lại ngay có thể làm bài bị ĐĂNG TRÙNG.
    // `requires_manual_reconciliation: true`: bắt buộc người dùng kiểm tra thủ công.
    id: PUB_P06_OUTCOME_UNKNOWN,
    post_id: POST_FAILED,
    post_version: 3,
    channel: 'facebook_page',
    page_id: PAGE_PHO_CHINH,
    page_name: 'Phở Bắc Cô Hương',
    status: PUBLICATION_STATUSES.OUTCOME_UNKNOWN,
    source: PUBLICATION_SOURCES.API,
    sent_at: demoAgo({ days: 2, hours: 6 }),
    error: {
      code: 'upstream_error',
      message:
        'Mất kết nối tới Facebook sau khi yêu cầu đăng bài đã được gửi đi. Hệ thống chưa xác định được bài đã lên hay chưa.',
      hint: 'Hãy mở Facebook Page kiểm tra thủ công rồi ghi nhận kết quả. Không bấm “Thử lại” để tránh đăng trùng.',
    },
    attempt_count: 2,
    retry_allowed: false,
    requires_manual_reconciliation: true,
    created_at: demoAgo({ days: 2, hours: 6 }),
    updated_at: demoAgo({ days: 2, hours: 5 }),
  },
];

/**
 * Dòng thời gian của từng lần xuất bản, khoá theo `publication.id`.
 * Quan trọng nhất là timeline của lần gửi `outcome_unknown`: nó giải thích vì sao
 * không được thử lại, để người dùng hiểu thay vì chỉ thấy một thông báo lỗi.
 */
export const demoPublicationEvents: Record<Id, PublicationEvent[]> = {
  [PUB_P01_PUBLISHED]: [
    {
      at: demoAgo({ days: 9, hours: 4, minutes: 1 }),
      type: 'queued',
      message: 'Bài đã vào hàng đợi gửi tới Page “Phở Bắc Cô Hương”.',
    },
    {
      at: demoAgo({ days: 9, hours: 4 }),
      type: 'sending',
      message: 'Hệ thống đã gửi yêu cầu đăng bài lên Facebook.',
    },
    {
      at: demoAgo({ days: 9, hours: 4 }),
      type: 'response',
      message:
        'Facebook trả về mã bài viết 108452319776401_122145678901234567. Bài đã lên Page.',
    },
  ],
  [PUB_P02_MANUAL]: [
    {
      at: demoAgo({ days: 8, hours: 1 }),
      type: 'manual_note',
      message:
        'Cô Hương tự đăng bài trên Facebook lúc 9h ngày 8/3 vì trang quản trị Page bị lỗi.',
    },
    {
      at: demoAgo({ days: 8, hours: 1 }),
      type: 'manual_note',
      message:
        'Minh đã nhập lại link bài và thời gian đăng để hệ thống ghi nhận là “Đã đăng thủ công”.',
    },
  ],
  [PUB_P03_SENDING]: [
    {
      at: demoAgo({ minutes: 5 }),
      type: 'queued',
      message: 'Bài đã vào hàng đợi gửi ngay.',
    },
    {
      at: demoAgo({ minutes: 4 }),
      type: 'sending',
      message: 'Đang gửi yêu cầu đăng bài lên Facebook. Vui lòng chờ trong giây lát.',
    },
  ],
  [PUB_P04_NEEDS_RECONNECT]: [
    {
      at: demoAgo({ hours: 19, minutes: 1 }),
      type: 'queued',
      message: 'Bài đã vào hàng đợi gửi tới Page “Phở Bắc Cô Hương”.',
    },
    {
      at: demoAgo({ hours: 19 }),
      type: 'error',
      message:
        'Facebook từ chối yêu cầu: token truy cập Page đã hết hiệu lực (hết hạn lúc 06:00 ngày 15/03).',
    },
    {
      at: demoAgo({ hours: 19 }),
      type: 'manual_note',
      message:
        'Bài CHƯA lên Facebook. Cần kết nối lại Page trong mục Kết nối rồi gửi lại.',
    },
  ],
  [PUB_P05_PENDING]: [
    {
      at: demoAgo({ days: 1, hours: 2 }),
      type: 'queued',
      message: 'Đã hẹn giờ đăng lúc 11:00 ngày 16/03/2026 (giờ Việt Nam).',
    },
  ],
  [PUB_P06_FAILED]: [
    {
      at: demoAgo({ days: 2, hours: 8, minutes: 1 }),
      type: 'queued',
      message: 'Bài đã vào hàng đợi gửi ngay sau khi được duyệt.',
    },
    {
      at: demoAgo({ days: 2, hours: 8 }),
      type: 'sending',
      message: 'Hệ thống đã gửi yêu cầu đăng bài lên Facebook.',
    },
    {
      at: demoAgo({ days: 2, hours: 8 }),
      type: 'error',
      message:
        'Facebook trả về lỗi tạm chặn (gửi quá nhanh). Bài chưa lên Facebook — có thể thử lại an toàn.',
    },
  ],
  [PUB_P06_OUTCOME_UNKNOWN]: [
    {
      at: demoAgo({ days: 2, hours: 6, minutes: 2 }),
      type: 'queued',
      message: 'Thử lại lần 2 sau khi lần gửi trước bị Facebook tạm chặn.',
    },
    {
      at: demoAgo({ days: 2, hours: 6, minutes: 1 }),
      type: 'sending',
      message: 'Hệ thống đã gửi yêu cầu đăng bài lên Facebook (lần thử thứ 2).',
    },
    {
      at: demoAgo({ days: 2, hours: 6 }),
      type: 'error',
      message:
        'Mất kết nối tới Facebook sau khi yêu cầu đã được gửi đi. Không nhận được phản hồi nên CHƯA xác định được bài đã lên hay chưa.',
    },
    {
      at: demoAgo({ days: 2, hours: 5 }),
      type: 'manual_note',
      message:
        'Cần đối soát thủ công: mở Facebook Page xem bài đã lên chưa rồi ghi nhận kết quả. Không bấm “Thử lại” để tránh đăng trùng.',
    },
  ],
};
