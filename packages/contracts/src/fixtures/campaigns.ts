/**
 * DEMO FIXTURE — Campaign, bài viết, lịch sử phiên bản, export, bản nháp brief.
 *
 * MỤC ĐÍCH: demo trọn vòng đời nội dung của quán phở:
 * - 2 campaign: một ĐANG CHẠY (combo trưa văn phòng) và một còn là BẢN NHÁP
 *   (khai trương chi nhánh 2) — brief đầy đủ, mục tiêu và số liệu ở mức quán nhỏ.
 * - 9 bài phủ HẾT `POST_STATUSES`, trong đó có:
 *   + 1 bài `approved` + `requires_reapproval: true` → demo "sửa bài đã duyệt
 *     phải duyệt lại" (nút Đăng bị khoá kèm lý do);
 *   + 1 bài `rejected` kèm `rejection_reason` tiếng Việt;
 *   + 1 bài `failed` (đăng lỗi) và 1 bài `scheduled` (đã hẹn giờ).
 * - Mỗi bài có 2–4 version với lịch sử `VERSION_SOURCES` (ai_generated →
 *   ai_revised → human) và ít nhất một `AiReview` có `checks` tiếng Việt.
 *
 * Con số cố tình ở mức SME: 4.218 người theo dõi, 120–500 lượt cảm xúc/bài.
 */

import type {
  BriefRevisionDraft,
  Campaign,
  ExportJob,
  Post,
  PostMedia,
  PostVersion,
  PostVersionList,
} from '../campaign.js';
import {
  CAMPAIGN_OBJECTIVES,
  CAMPAIGN_STATUSES,
  CHANNELS,
  CONTENT_PILLARS,
  EXPORT_FORMATS,
  POST_FORMATS,
  POST_STATUSES,
  VERSION_SOURCES,
} from '../enums.js';
import {
  BRIEF_DRAFT_CS2,
  BRIEF_DRAFT_TRUA,
  CMP_PHO_CHI_NHANH_2,
  CMP_PHO_TRUA,
  EXPORT_FAILED,
  EXPORT_QUEUED,
  EXPORT_READY,
  JOB_EXPORT_QUEUED,
  POST_APPROVED,
  POST_APPROVED_REAPPROVAL,
  POST_DRAFT,
  POST_FAILED,
  POST_IDS,
  POST_NEEDS_REVIEW,
  POST_PUBLISHED_API,
  POST_PUBLISHED_MANUAL,
  POST_REJECTED,
  POST_SCHEDULED,
  PROD_COMBO_TRUA,
  PROD_PHO_BO_TAI_NAM,
  PROD_PHO_CHAY_NAM,
  PROD_PHO_CUON,
  REC_CAROUSEL,
  REC_GIO_DANG,
  USR_EDITOR_MINH,
  USR_OWNER_HUONG,
  WS_FB,
  demoAgo,
  demoAhead,
  type DemoPostId,
} from './ids.js';

/** Lấy version mới nhất — fixture luôn có ít nhất 1 version nên `!` là an toàn. */
function lastVersion(versions: PostVersion[]): PostVersion {
  const last = versions[versions.length - 1];
  if (!last) {
    throw new Error('Fixture lỗi: bài viết phải có ít nhất một version.');
  }
  return last;
}

// ---------------------------------------------------------------------------
// Phương tiện dùng lại
// ---------------------------------------------------------------------------

const mediaComboTruaReel: PostMedia[] = [
  {
    id: 'media_p01_reel_combo_trua',
    url: 'https://cdn.demo.local/media/pho-bac/combo-trua-reel-thang-3.mp4',
    alt: 'Cô Hương múc nước dùng từ nồi lớn rồi chan vào bát phở bò tái nạm, kèm đĩa quẩy vàng.',
    width: 1080,
    height: 1920,
    mime_type: 'video/mp4',
    source: 'uploaded',
  },
];

const mediaKhuyenMai83: PostMedia[] = [
  {
    id: 'media_p02_anh_8_3',
    url: 'https://cdn.demo.local/media/pho-bac/khuyen-mai-8-3.jpg',
    alt: 'Bát phở bò tái nạm nóng hổi, đĩa quẩy và cốc trà đá trên bàn gỗ của quán.',
    width: 1200,
    height: 900,
    mime_type: 'image/jpeg',
    source: 'uploaded',
  },
];

const mediaNoiNuocDung: PostMedia[] = [
  {
    id: 'media_p03_noi_nuoc_dung',
    url: 'https://cdn.demo.local/media/pho-bac/noi-xuong-4h-sang.jpg',
    alt: 'Nồi nước dùng xương ống bò đang sôi lăn tăn lúc 4 giờ sáng trong bếp quán.',
    width: 1200,
    height: 900,
    mime_type: 'image/jpeg',
    source: 'uploaded',
  },
];

const mediaBangGiaCombo: PostMedia[] = [
  {
    id: 'media_p04_bang_gia_combo',
    url: 'https://cdn.demo.local/media/pho-bac/bang-gia-combo-trua.jpg',
    alt: 'Bảng giá combo trưa văn phòng viết tay treo trước quầy, ghi 59.000đ.',
    width: 1080,
    height: 1080,
    mime_type: 'image/jpeg',
    source: 'uploaded',
  },
];

const mediaPhoChay: PostMedia[] = [
  {
    id: 'media_p05_pho_chay',
    url: 'https://cdn.demo.local/media/pho-bac/pho-chay-nam-huong.jpg',
    alt: 'Bát phở chay nấm hương với nấm hương, củ sen và táo đỏ, nước dùng trong.',
    width: 1200,
    height: 900,
    mime_type: 'image/jpeg',
    source: 'ai_suggested',
  },
];

const mediaTheKhachQuen: PostMedia[] = [
  {
    id: 'media_p06_the_khach_quen',
    url: 'https://cdn.demo.local/media/pho-bac/the-khach-quen.jpg',
    alt: 'Thẻ giấy nhỏ ghi số điện thoại khách quen, đặt cạnh 10 que tính bằng tre.',
    width: 1080,
    height: 1080,
    mime_type: 'image/jpeg',
    source: 'uploaded',
  },
];

const mediaPhoCuon: PostMedia[] = [
  {
    id: 'media_p07_pho_cuon_1',
    url: 'https://cdn.demo.local/media/pho-bac/pho-cuon-1.jpg',
    alt: 'Đĩa phở cuốn nhân bò xào và rau sống, bên cạnh bát nước chấm chua ngọt.',
    width: 1200,
    height: 900,
    mime_type: 'image/jpeg',
    source: 'uploaded',
  },
  {
    id: 'media_p07_pho_cuon_2',
    url: 'https://cdn.demo.local/media/pho-bac/pho-cuon-2.jpg',
    alt: 'Cô Hương tráng bánh phở mỏng trên khuôn vải căng, khói bốc lên nghi ngút.',
    width: 1200,
    height: 900,
    mime_type: 'image/jpeg',
    source: 'uploaded',
  },
  {
    id: 'media_p07_pho_cuon_3',
    url: 'https://cdn.demo.local/media/pho-bac/pho-cuon-3.jpg',
    alt: 'Nước chấm chua ngọt pha trong bát nhỏ, có ớt tươi thái lát.',
    width: 1200,
    height: 900,
    mime_type: 'image/jpeg',
    source: 'ai_suggested',
  },
];

const mediaGiam30: PostMedia[] = [
  {
    id: 'media_p08_giam_30',
    url: 'https://cdn.demo.local/media/pho-bac/banner-giam-30.jpg',
    alt: 'Băng rôn đỏ ghi “GIẢM 30% TẤT CẢ CÁC MÓN” treo trước cửa quán.',
    width: 1200,
    height: 630,
    mime_type: 'image/jpeg',
    source: 'uploaded',
  },
];

const mediaKhaiTruong: PostMedia[] = [
  {
    id: 'media_p09_mat_tien_chi_nhanh_2',
    url: 'https://cdn.demo.local/media/pho-bac/mat-tien-tran-duy-hung.jpg',
    alt: 'Mặt tiền chi nhánh 2 đang được sơn sửa, biển hiệu chưa gắn chữ.',
    width: 1600,
    height: 900,
    mime_type: 'image/jpeg',
    source: 'uploaded',
  },
];

// ---------------------------------------------------------------------------
// Campaign
// ---------------------------------------------------------------------------

/**
 * 2 campaign của quán phở: một ĐANG CHẠY, một BẢN NHÁP.
 * Số lượng bài (`post_count`, `approved_count`, `published_count`) khớp với
 * danh sách bài bên dưới để UI hiển thị không bị lệch.
 */
export const demoCampaigns: Campaign[] = [
  {
    id: CMP_PHO_TRUA,
    workspace_id: WS_FB,
    name: 'Combo trưa văn phòng – Tháng 3',
    status: CAMPAIGN_STATUSES.ACTIVE,
    brief: {
      objective: CAMPAIGN_OBJECTIVES.SALES,
      objective_note:
        'Tăng số suất combo trưa bán ra trong khung 11h–13h cho khách văn phòng quanh phố Cửa Bắc: từ 38 suất/ngày lên 60 suất/ngày trước 31/03.',
      audience: [
        'Nhân viên văn phòng 22–35 tuổi làm việc trong bán kính 1 km quanh phố Cửa Bắc',
        'Khách quen đã ăn tại quán ít nhất 2 lần',
        'Người ăn trưa một mình, cần lên món nhanh dưới 10 phút',
      ],
      product_ids: [PROD_COMBO_TRUA, PROD_PHO_BO_TAI_NAM],
      key_message:
        'Bữa trưa nóng hổi, nước dùng ninh 12 tiếng, lên món trong 5 phút – chỉ 55.000đ.',
      must_include: [
        'Giá combo 55.000đ',
        'Khung giờ phục vụ 11:00–13:00',
        'Số điện thoại đặt trước 024 3825 1976',
      ],
      must_avoid: [
        'Không nói quán “rẻ nhất Hà Nội”',
        'Không dùng ảnh có mặt khách hàng khi chưa xin phép',
        'Không hứa giao hàng ngoài bán kính 2 km',
      ],
      start_date: '2026-03-02',
      end_date: '2026-03-31',
    },
    pillars: [
      CONTENT_PILLARS.PRODUCT,
      CONTENT_PILLARS.PROMOTION,
      CONTENT_PILLARS.BEHIND_THE_SCENES,
      CONTENT_PILLARS.COMMUNITY,
    ],
    channels: [CHANNELS.FACEBOOK_PAGE],
    version: 4,
    post_count: 8,
    approved_count: 3,
    published_count: 2,
    created_by: USR_OWNER_HUONG,
    created_at: demoAgo({ days: 27 }),
    updated_at: demoAgo({ days: 1 }),
  },
  {
    id: CMP_PHO_CHI_NHANH_2,
    workspace_id: WS_FB,
    name: 'Khai trương chi nhánh 2 – Trần Duy Hưng',
    status: CAMPAIGN_STATUSES.DRAFT,
    brief: {
      objective: CAMPAIGN_OBJECTIVES.AWARENESS,
      objective_note:
        'Giới thiệu chi nhánh thứ hai ở Trần Duy Hưng (Cầu Giấy) tới khách cũ và dân văn phòng khu vực mới, mục tiêu 300 người theo dõi mới trong tháng khai trương.',
      audience: [
        'Khách quen hiện tại sống ở khu Cầu Giấy – Thanh Xuân',
        'Nhân viên văn phòng toà nhà trên đường Trần Duy Hưng',
      ],
      product_ids: [PROD_PHO_BO_TAI_NAM, PROD_PHO_CUON],
      key_message:
        'Vẫn công thức nước dùng 12 tiếng của cô Hương, giờ đây ở Trần Duy Hưng – Cầu Giấy.',
      must_include: ['Địa chỉ chi nhánh 2', 'Giờ mở cửa 06:00–22:00'],
      must_avoid: ['Không công bố ngày khai trương khi chưa chốt với chủ nhà'],
      start_date: '2026-04-01',
      end_date: '2026-04-30',
    },
    pillars: [CONTENT_PILLARS.COMMUNITY, CONTENT_PILLARS.BEHIND_THE_SCENES],
    channels: [CHANNELS.FACEBOOK_PAGE],
    version: 2,
    post_count: 1,
    approved_count: 0,
    published_count: 0,
    created_by: USR_OWNER_HUONG,
    created_at: demoAgo({ days: 5 }),
    updated_at: demoAgo({ days: 2 }),
  },
];

// ---------------------------------------------------------------------------
// Lịch sử phiên bản (khai báo trước để `current` trỏ đúng version mới nhất)
// ---------------------------------------------------------------------------

/** p01 — bài chủ lực đã đăng qua API: 3 version, có 2 lần AI review. */
const versionsP01: PostVersion[] = [
  {
    version: 1,
    caption:
      'Quán Phở Bắc Cô Hương xin giới thiệu combo trưa văn phòng: một bát phở bò tái nạm, một đĩa quẩy nóng và một cốc trà đá với giá ưu đãi chỉ 55.000đ. Nước dùng được ninh từ xương ống trong nhiều giờ nên rất ngọt và đậm đà. Quý khách làm việc quanh khu vực Cửa Bắc hãy ghé quán để thưởng thức. Quán phục vụ từ 6h đến 22h hằng ngày và có nhận đặt trước qua điện thoại. #PhoBacCoHuong #ComboTrua #AnTruaVanPhong',
    hashtags: ['#PhoBacCoHuong', '#ComboTrua', '#AnTruaVanPhong'],
    media: mediaComboTruaReel,
    source: VERSION_SOURCES.AI_GENERATED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 10, hours: 3 }),
    note: 'AI sinh từ brief “Combo trưa văn phòng – Tháng 3”.',
    review: {
      score: 7.4,
      summary:
        'Đúng thông tin nhưng câu dài và dùng từ “Quý khách” không hợp giọng điệu của quán.',
      checks: [
        {
          key: 'brand_voice',
          label: 'Giọng điệu thương hiệu',
          status: 'warn',
          message:
            'Quán xưng “quán” và gọi khách là “bạn”, không dùng “Quý khách”.',
          char_start: 289,
          char_end: 299,
        },
        {
          key: 'length',
          label: 'Độ dài bài viết',
          status: 'fail',
          message: 'Bài dài 520 ký tự, nên gọn dưới 400 ký tự cho bài reel.',
        },
        {
          key: 'cta',
          label: 'Lời kêu gọi hành động',
          status: 'warn',
          message: 'Chưa có số điện thoại đặt trước trong phần kết.',
        },
      ],
    },
  },
  {
    version: 2,
    caption:
      'Trưa nay ăn gì cho nhanh mà vẫn nóng? Combo trưa văn phòng của quán: một bát phở bò tái nạm, một đĩa quẩy nóng và một cốc trà đá – chỉ 55.000đ. Nước dùng ninh xương ống 12 tiếng nên bát phở lúc nào cũng ngọt thịt. Bạn gọi trước 024 3825 1976 là 11h15 có ngay trên bàn. #PhoBacCoHuong #ComboTrua #AnTruaVanPhong',
    hashtags: ['#PhoBacCoHuong', '#ComboTrua', '#AnTruaVanPhong'],
    media: mediaComboTruaReel,
    source: VERSION_SOURCES.AI_REVISED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 10, hours: 1 }),
    note: 'Yêu cầu AI: ngắn hơn, bỏ “Quý khách”, thêm CTA gọi điện.',
    review: {
      score: 8.6,
      summary: 'Gọn hơn, đúng giọng điệu, đã có CTA và số điện thoại.',
      checks: [
        {
          key: 'brand_voice',
          label: 'Giọng điệu thương hiệu',
          status: 'pass',
          message: 'Xưng “quán”, gọi khách là “bạn” — đúng giọng điệu đã xác nhận.',
        },
        {
          key: 'price_accuracy',
          label: 'Độ chính xác của giá',
          status: 'pass',
          message: 'Giá 55.000đ khớp với thực đơn tháng 3.',
        },
        {
          key: 'cta',
          label: 'Lời kêu gọi hành động',
          status: 'pass',
          message: 'Đã có số đặt trước và mốc thời gian rõ ràng.',
        },
      ],
    },
  },
  {
    // Version hiện tại do con người viết lại — bài đã được duyệt ở version này.
    version: 3,
    caption:
      '11h trưa nay ăn gì cho nhanh mà vẫn nóng?\n\nCombo trưa văn phòng của quán mình: một bát phở bò tái nạm đầy đặn, một đĩa quẩy nóng và một cốc trà đá – chỉ 55.000đ. Nước dùng ninh xương ống 12 tiếng, bắt đầu từ 4h sáng, nên bát phở lúc nào cũng ngọt thịt.\n\nQuán nhận đặt trước qua số 024 3825 1976. Bạn làm ở quanh phố Cửa Bắc ghé thử nhé, quán ở số 18 Cửa Bắc ạ.\n\n#PhoBacCoHuong #ComboTrua #AnTruaVanPhong #PhoHaNoi',
    hashtags: [
      '#PhoBacCoHuong',
      '#ComboTrua',
      '#AnTruaVanPhong',
      '#PhoHaNoi',
    ],
    media: mediaComboTruaReel,
    source: VERSION_SOURCES.HUMAN,
    created_by: USR_OWNER_HUONG,
    created_by_name: 'Nguyễn Thị Hương',
    created_at: demoAgo({ days: 9, hours: 6 }),
    note: 'Cô Hương thêm giờ ninh xương và địa chỉ quán.',
    approved_at: demoAgo({ days: 9, hours: 4 }),
    approved_by: USR_OWNER_HUONG,
  },
];

/** p02 — bài khuyến mãi 8/3: người dùng tự đăng rồi ghi nhận lại. */
const versionsP02: PostVersion[] = [
  {
    version: 1,
    caption:
      'Nhân ngày Quốc tế Phụ nữ 8/3, quán Phở Bắc Cô Hương tặng trà đá và quẩy cho khách nữ ghé quán trong ngày hôm nay. Hẹn gặp các chị em tại 18 phố Cửa Bắc! #PhoBacCoHuong #83',
    hashtags: ['#PhoBacCoHuong', '#83'],
    media: mediaKhuyenMai83,
    source: VERSION_SOURCES.HUMAN,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 8, hours: 5 }),
    note: 'Minh viết vội buổi sáng, chưa có giờ mở cửa.',
  },
  {
    // Version hiện tại = bản đã duyệt & đã đăng (người dùng tự đăng rồi nhập URL).
    version: 2,
    caption:
      'Hôm nay 8/3, quán mời tất cả các chị em ghé ăn một bát phở nóng: quán tặng thêm một cốc trà đá và một đĩa quẩy. Không cần đặt trước, chỉ cần nói với cô Hương là bạn biết quán qua Facebook nhé. Chúc các chị em một ngày thật vui và được yêu thương. Quán mở từ 6h đến 22h tại 18 phố Cửa Bắc. #PhoBacCoHuong #QuocTePhuNu #83 #PhoHaNoi',
    hashtags: ['#PhoBacCoHuong', '#QuocTePhuNu', '#83', '#PhoHaNoi'],
    media: mediaKhuyenMai83,
    source: VERSION_SOURCES.HUMAN,
    created_by: USR_OWNER_HUONG,
    created_by_name: 'Nguyễn Thị Hương',
    created_at: demoAgo({ days: 8, hours: 2 }),
    note: 'Cô Hương thêm giờ mở cửa và lời chúc.',
    review: {
      score: 9,
      summary: 'Bài ngắn, ấm áp, đúng dịp — không có lỗi cần sửa.',
      checks: [
        {
          key: 'brand_voice',
          label: 'Giọng điệu thương hiệu',
          status: 'pass',
          message: 'Ấm áp, gần gũi, đúng giọng điệu quán.',
        },
        {
          key: 'hashtags',
          label: 'Hashtag',
          status: 'pass',
          message: '4 hashtag, có hashtag thương hiệu.',
        },
      ],
    },
    approved_at: demoAgo({ days: 8, hours: 1 }),
    approved_by: USR_OWNER_HUONG,
  },
];

/** p03 — bài hậu trường: 4 version, đang được gửi lên Facebook (publication `sending`). */
const versionsP03: PostVersion[] = [
  {
    version: 1,
    caption:
      'Nước dùng là linh hồn của bát phở. Quán Phở Bắc Cô Hương ninh xương ống bò trong nhiều giờ để có nồi nước trong và ngọt. Mời bạn ghé quán thưởng thức bát phở nóng hổi vào bữa sáng hoặc bữa trưa. #PhoBacCoHuong #NuocDung #PhoHaNoi',
    hashtags: ['#PhoBacCoHuong', '#NuocDung', '#PhoHaNoi'],
    media: mediaNoiNuocDung,
    source: VERSION_SOURCES.AI_GENERATED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 3, hours: 6 }),
    note: 'AI sinh từ brief, ý tưởng hậu trường nấu nước dùng.',
  },
  {
    version: 2,
    caption:
      '4 giờ sáng, khi cả phố Cửa Bắc còn ngủ, quán đã bắc nồi xương ống bò lên bếp. Xương được chần sạch rồi ninh lửa nhỏ suốt 12 tiếng, hớt bọt liên tục nên nước dùng trong và ngọt thịt chứ không đục. Mời bạn ghé quán ăn bát phở nóng vào bữa sáng. #PhoBacCoHuong #HauTruong #NuocDung12Tieng #PhoHaNoi',
    hashtags: [
      '#PhoBacCoHuong',
      '#HauTruong',
      '#NuocDung12Tieng',
      '#PhoHaNoi',
    ],
    media: mediaNoiNuocDung,
    source: VERSION_SOURCES.AI_REVISED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 3, hours: 4 }),
    note: 'Yêu cầu AI: kể như chuyện hậu trường, thêm mốc 4h sáng và 12 tiếng.',
  },
  {
    version: 3,
    caption:
      '4 giờ sáng, khi cả phố Cửa Bắc còn ngủ, quán đã bắc nồi xương ống bò lên bếp. Xương chần sạch rồi ninh lửa nhỏ suốt 12 tiếng, hớt bọt liên tục nên nước dùng trong và ngọt thịt. Cô Hương vẫn tự tay nêm nếm nồi nước đầu tiên mỗi sáng. Bạn có muốn quán quay lại cảnh ninh xương không? Comment để quán biết nhé! #PhoBacCoHuong #HauTruong #NuocDung12Tieng #PhoHaNoi',
    hashtags: [
      '#PhoBacCoHuong',
      '#HauTruong',
      '#NuocDung12Tieng',
      '#PhoHaNoi',
    ],
    media: mediaNoiNuocDung,
    source: VERSION_SOURCES.AI_REVISED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 3, hours: 2 }),
    note: 'Yêu cầu AI: thêm chi tiết cô Hương nêm nếm và câu hỏi tương tác.',
    review: {
      score: 8.1,
      summary:
        'Nội dung tốt, chỉ còn một cụm từ nên tránh theo ghi chú thương hiệu.',
      checks: [
        {
          key: 'brand_voice',
          label: 'Giọng điệu thương hiệu',
          status: 'pass',
          message: 'Kể chuyện gần gũi, đúng giọng điệu đã xác nhận.',
        },
        {
          key: 'do_not_use',
          label: 'Cụm từ cần tránh',
          status: 'warn',
          message:
            'Cụm “ngon nhất Hà Nội” không có trong bài này, nhưng tránh dùng ở các bài sau theo ghi chú thương hiệu.',
        },
        {
          key: 'legal',
          label: 'Hình ảnh và quyền riêng tư',
          status: 'pass',
          message: 'Ảnh chỉ có cô Hương, đã có sự đồng ý.',
        },
      ],
    },
  },
  {
    // Version hiện tại: bản người viết lại + ảnh thật, đã duyệt và đang được gửi.
    version: 4,
    caption:
      '“Nước dùng ngon thì bát phở mới ngon” – câu cô Hương nói mỗi sáng.\n\n4 giờ sáng, khi cả phố Cửa Bắc còn ngủ, quán đã bắc nồi xương ống bò lên bếp. Xương chần sạch rồi ninh lửa nhỏ đúng 12 tiếng, hớt bọt liên tục nên nước trong và ngọt thịt. Cô Hương vẫn tự tay nêm nếm nồi nước đầu tiên.\n\nBạn có muốn quán quay lại cảnh ninh xương không? Comment để quán biết nhé!\n\n#PhoBacCoHuong #HauTruong #NuocDung12Tieng #PhoHaNoi',
    hashtags: [
      '#PhoBacCoHuong',
      '#HauTruong',
      '#NuocDung12Tieng',
      '#PhoHaNoi',
    ],
    media: mediaNoiNuocDung,
    source: VERSION_SOURCES.HUMAN,
    created_by: USR_OWNER_HUONG,
    created_by_name: 'Nguyễn Thị Hương',
    created_at: demoAgo({ hours: 2 }),
    note: 'Cô Hương thêm câu nói của mình ở đầu bài.',
    approved_at: demoAgo({ hours: 1 }),
    approved_by: USR_OWNER_HUONG,
  },
];

/** p04 — bài ĐÃ DUYỆT nhưng bị sửa: `requires_reapproval: true` (đổi giá combo). */
const versionsP04: PostVersion[] = [
  {
    version: 1,
    caption:
      'Combo trưa văn phòng của quán chỉ 55.000đ gồm phở bò tái nạm, quẩy nóng và trà đá. Quán phục vụ nhanh trong 5 phút cho khách văn phòng quanh phố Cửa Bắc. #PhoBacCoHuong #ComboTrua #AnTruaVanPhong',
    hashtags: ['#PhoBacCoHuong', '#ComboTrua', '#AnTruaVanPhong'],
    media: mediaBangGiaCombo,
    source: VERSION_SOURCES.AI_GENERATED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 4, hours: 5 }),
  },
  {
    version: 2,
    caption:
      'Trưa nay bạn ăn gì? Combo trưa văn phòng của quán mình: bát phở bò tái nạm đầy đặn, đĩa quẩy nóng và cốc trà đá – 55.000đ, lên món trong 5 phút. Quán ở 18 phố Cửa Bắc, bạn gọi trước 024 3825 1976 cho khỏi chờ nhé. #PhoBacCoHuong #ComboTrua #AnTruaVanPhong',
    hashtags: ['#PhoBacCoHuong', '#ComboTrua', '#AnTruaVanPhong'],
    media: mediaBangGiaCombo,
    source: VERSION_SOURCES.HUMAN,
    created_by: USR_OWNER_HUONG,
    created_by_name: 'Nguyễn Thị Hương',
    created_at: demoAgo({ days: 4, hours: 2 }),
    note: 'Cô Hương viết lại theo giọng của quán.',
    approved_at: demoAgo({ days: 3, hours: 8 }),
    approved_by: USR_OWNER_HUONG,
  },
  {
    // Version hiện tại SINH SAU KHI ĐÃ DUYỆT → backend bật `requires_reapproval`.
    version: 3,
    caption:
      'Từ 20/3, combo trưa văn phòng của quán điều chỉnh lên 59.000đ (tăng 4.000đ) vì giá xương ống và thịt bò tăng suốt hai tuần nay. Quán giữ nguyên định lượng: bát phở bò tái nạm đầy đặn, quẩy nóng và trà đá. Cảm ơn bạn đã thông cảm cho quán. Bạn vẫn đặt trước qua 024 3825 1976 như cũ nhé. #PhoBacCoHuong #ComboTrua #AnTruaVanPhong',
    hashtags: ['#PhoBacCoHuong', '#ComboTrua', '#AnTruaVanPhong'],
    media: mediaBangGiaCombo,
    source: VERSION_SOURCES.AI_REVISED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ hours: 20 }),
    note: 'Yêu cầu AI: đổi giá combo từ 55.000đ thành 59.000đ, giữ nguyên giọng điệu và CTA.',
    review: {
      score: 8.4,
      summary:
        'Giá mới đã cập nhật đúng và có giải thích lý do tăng giá, nên duyệt lại trước khi đăng.',
      checks: [
        {
          key: 'price_accuracy',
          label: 'Độ chính xác của giá',
          status: 'pass',
          message: 'Giá 59.000đ khớp bảng giá mới cập nhật ngày 14/03.',
        },
        {
          key: 'state_change',
          label: 'Thay đổi sau khi đã duyệt',
          status: 'warn',
          message:
            'Bài đã được duyệt ở bản 2, nay đổi giá nên cần người có quyền duyệt lại bản 3.',
        },
        {
          key: 'must_include',
          label: 'Thông tin bắt buộc',
          status: 'pass',
          message: 'Có mốc thời gian áp dụng, giá mới và số đặt trước.',
        },
      ],
    },
  },
];

/** p05 — bài đã hẹn giờ 11:00 ngày 16/03 (publication `pending`). */
const versionsP05: PostVersion[] = [
  {
    version: 1,
    caption:
      'Quán có món phở chay nấm hương cho bạn nào muốn ăn nhẹ. Nước dùng nấu từ nấm hương và củ sen nên thanh vị, một bát 45.000đ. #PhoBacCoHuong #PhoChay #AnChay',
    hashtags: ['#PhoBacCoHuong', '#PhoChay', '#AnChay'],
    media: mediaPhoChay,
    source: VERSION_SOURCES.AI_GENERATED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 2, hours: 4 }),
  },
  {
    version: 2,
    caption:
      'Thứ Hai ăn chay một bữa cho nhẹ bụng nhé? Phở chay nấm hương của quán nấu nồi riêng từ củ sen, nấm hương và táo đỏ, không dùng chung nước thịt nên bạn ăn chay được yên tâm. Một bát 45.000đ, thêm quẩy là 55.000đ. Quán ở 18 phố Cửa Bắc, mở từ 6h sáng. #PhoBacCoHuong #PhoChay #AnChay #PhoHaNoi',
    hashtags: ['#PhoBacCoHuong', '#PhoChay', '#AnChay', '#PhoHaNoi'],
    media: mediaPhoChay,
    source: VERSION_SOURCES.HUMAN,
    created_by: USR_OWNER_HUONG,
    created_by_name: 'Nguyễn Thị Hương',
    created_at: demoAgo({ days: 1, hours: 6 }),
    note: 'Cô Hương thêm giá và địa chỉ.',
    approved_at: demoAgo({ days: 1, hours: 2 }),
    approved_by: USR_OWNER_HUONG,
  },
];

/** p06 — bài đăng LỖI: đã duyệt nhưng lần gửi thứ hai không rõ kết quả. */
const versionsP06: PostVersion[] = [
  {
    version: 1,
    caption:
      'Quán tri ân khách quen bằng chương trình tích bát: đủ 10 bát tặng 1 bát. Chương trình áp dụng cho khách đã ăn tại quán từ 3 lần trở lên. #PhoBacCoHuong #KhachQuen #UuDai',
    hashtags: ['#PhoBacCoHuong', '#KhachQuen', '#UuDai'],
    media: mediaTheKhachQuen,
    source: VERSION_SOURCES.AI_GENERATED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 3, hours: 5 }),
    review: {
      score: 6.8,
      summary: 'Ý rõ nhưng điều kiện “từ 3 lần trở lên” khó kiểm soát ở quán nhỏ.',
      checks: [
        {
          key: 'feasibility',
          label: 'Khả năng thực hiện tại quán',
          status: 'warn',
          message:
            'Quán chưa có cách đếm số lần khách đã ăn, nên điều kiện này khó làm.',
        },
        {
          key: 'brand_voice',
          label: 'Giọng điệu thương hiệu',
          status: 'warn',
          message: 'Câu văn còn khô, giống thông báo hơn là nói chuyện với khách.',
        },
      ],
    },
  },
  {
    version: 2,
    caption:
      'Quán cảm ơn các bạn khách quen đã ăn ở đây hơn một năm nay. Từ hôm nay, cứ đủ 10 bát là quán tặng bạn 1 bát, quán ghi sổ theo số điện thoại đặt trước, không cần thẻ gì cả. Bạn chỉ cần nói “cho con 10 bát tính sổ” là được ạ. #PhoBacCoHuong #KhachQuen #UuDai #PhoHaNoi',
    hashtags: ['#PhoBacCoHuong', '#KhachQuen', '#UuDai', '#PhoHaNoi'],
    media: mediaTheKhachQuen,
    source: VERSION_SOURCES.AI_REVISED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 3, hours: 3 }),
    note: 'Yêu cầu AI: bỏ điều kiện khó kiểm soát, viết như đang nói với khách.',
  },
  {
    version: 3,
    caption:
      'Quán cảm ơn các bạn khách quen đã ăn ở đây hơn một năm nay. Từ hôm nay, cứ đủ 10 bát là quán tặng bạn 1 bát – quán ghi sổ theo số điện thoại đặt trước, không cần thẻ gì cả. Bạn chỉ cần nói “cho con 10 bát tính sổ” là được ạ. Quán mở 6h–22h tại 18 phố Cửa Bắc, số đặt trước 024 3825 1976. #PhoBacCoHuong #KhachQuen #UuDai #PhoHaNoi',
    hashtags: ['#PhoBacCoHuong', '#KhachQuen', '#UuDai', '#PhoHaNoi'],
    media: mediaTheKhachQuen,
    source: VERSION_SOURCES.HUMAN,
    created_by: USR_OWNER_HUONG,
    created_by_name: 'Nguyễn Thị Hương',
    created_at: demoAgo({ days: 3, hours: 1 }),
    note: 'Cô Hương thêm giờ mở cửa và số điện thoại.',
    approved_at: demoAgo({ days: 2, hours: 20 }),
    approved_by: USR_OWNER_HUONG,
  },
];

/** p07 — bài đang CHỜ DUYỆT (carousel 3 ảnh phở cuốn). */
const versionsP07: PostVersion[] = [
  {
    version: 1,
    caption:
      'Phở cuốn là món mới của quán, bán từ 15h mỗi ngày. Bánh phở tráng mỏng cuốn thịt bò xào và rau sống, chấm nước mắm chua ngọt. Một suất 60.000đ. #PhoBacCoHuong #PhoCuon #AnChieu',
    hashtags: ['#PhoBacCoHuong', '#PhoCuon', '#AnChieu'],
    media: mediaPhoCuon,
    source: VERSION_SOURCES.AI_GENERATED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 1, hours: 4 }),
    review: {
      score: 7.9,
      summary: 'Thông tin đúng, nên thêm cảm giác thèm ăn và lý do nên thử.',
      checks: [
        {
          key: 'appetite_appeal',
          label: 'Sức hấp dẫn của món',
          status: 'warn',
          message: 'Bài liệt kê nguyên liệu nhưng chưa tả được vị hay độ tươi.',
        },
        {
          key: 'hashtags',
          label: 'Hashtag',
          status: 'pass',
          message: 'Có hashtag thương hiệu và hashtag món.',
        },
      ],
    },
  },
  {
    // Version đang chờ duyệt: `pending_approval_version = 2`.
    version: 2,
    caption:
      'Buổi chiều ở Cửa Bắc ăn gì nhỉ? Quán mở bán phở cuốn từ 15h: bánh phở tráng mỏng cuốn thịt bò xào cùng rau sống, chấm bát nước mắm chua ngọt pha theo công thức của cô Hương. Một suất 60.000đ, hai người ăn chung cũng vừa. Bạn ghé quán hoặc gọi 024 3825 1976 để quán cuốn sẵn nhé! #PhoBacCoHuong #PhoCuon #AnChieu #PhoHaNoi',
    hashtags: ['#PhoBacCoHuong', '#PhoCuon', '#AnChieu', '#PhoHaNoi'],
    media: mediaPhoCuon,
    source: VERSION_SOURCES.AI_REVISED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ hours: 5 }),
    note: 'Yêu cầu AI: thêm cảm giác thèm ăn, mở bài bằng câu hỏi, thêm CTA gọi điện.',
    review: {
      score: 8.8,
      summary: 'Bài đã đủ tốt để gửi duyệt: có món, giá, giờ bán và CTA.',
      checks: [
        {
          key: 'brand_voice',
          label: 'Giọng điệu thương hiệu',
          status: 'pass',
          message: 'Cách nói tự nhiên, đúng giọng điệu của quán.',
        },
        {
          key: 'price_accuracy',
          label: 'Độ chính xác của giá',
          status: 'pass',
          message: 'Giá 60.000đ khớp thực đơn tháng 3.',
        },
      ],
    },
  },
];

/** p08 — bài BỊ TỪ CHỐI: nội dung sai so với brief (giảm 30% tất cả các món). */
const versionsP08: PostVersion[] = [
  {
    version: 1,
    caption:
      'Ưu đãi tháng 3: quán giảm giá cho khách ghé ăn trong tuần này. Bạn ghé quán Phở Bắc Cô Hương để biết chi tiết nhé! #PhoBacCoHuong #KhuyenMai #PhoHaNoi',
    hashtags: ['#PhoBacCoHuong', '#KhuyenMai', '#PhoHaNoi'],
    media: mediaGiam30,
    source: VERSION_SOURCES.AI_GENERATED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 2, hours: 6 }),
    review: {
      score: 6.2,
      summary: 'Bài quá chung chung, không nói rõ mức giảm hay món nào được giảm.',
      checks: [
        {
          key: 'must_include',
          label: 'Thông tin bắt buộc',
          status: 'fail',
          message: 'Thiếu mức giảm cụ thể và thời gian áp dụng.',
        },
      ],
    },
  },
  {
    // Version hiện tại — chính là bản bị từ chối (kèm AiReview chỉ ra lỗi giá).
    version: 2,
    caption:
      'Ưu đãi lớn nhất tháng 3: giảm 30% tất cả các món trong tuần này, không giới hạn số lượng. Bạn chỉ cần ghé quán và đọc mã “PHO30” là được giảm ngay. Nhanh tay nhé, chương trình chỉ kéo dài đến hết Chủ nhật! #PhoBacCoHuong #Giam30 #KhuyenMai #PhoHaNoi',
    hashtags: ['#PhoBacCoHuong', '#Giam30', '#KhuyenMai', '#PhoHaNoi'],
    media: mediaGiam30,
    source: VERSION_SOURCES.AI_REVISED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 2, hours: 1 }),
    note: 'Yêu cầu AI: làm nổi bật mức giảm và thêm mã khuyến mãi.',
    review: {
      score: 5.1,
      summary:
        'Nội dung tự thêm mức giảm 30% cho tất cả các món — không có trong brief và không đúng thực tế.',
      checks: [
        {
          key: 'brief_alignment',
          label: 'Khớp với brief chiến dịch',
          status: 'fail',
          message:
            'Brief chỉ cho phép giảm cho combo trưa; bài này giảm 30% tất cả các món.',
        },
        {
          key: 'price_accuracy',
          label: 'Độ chính xác của giá',
          status: 'fail',
          message: 'Mức giảm 30% và mã “PHO30” không có trong bảng giá của quán.',
          char_start: 28,
          char_end: 64,
        },
        {
          key: 'must_avoid',
          label: 'Điều cần tránh',
          status: 'fail',
          message: 'Dùng từ ngữ khuyến mãi quá đà (“lớn nhất tháng 3”).',
        },
      ],
    },
  },
];

/** p09 — BẢN NHÁP của campaign khai trương chi nhánh 2. */
const versionsP09: PostVersion[] = [
  {
    version: 1,
    caption:
      'Quán Phở Bắc Cô Hương thông báo mở chi nhánh thứ hai tại khu vực Cầu Giấy. Chi nhánh mới phục vụ các món phở như quán cũ. Thông tin chi tiết sẽ được cập nhật sau. #PhoBacCoHuong #KhaiTruong #CauGiay',
    hashtags: ['#PhoBacCoHuong', '#KhaiTruong', '#CauGiay'],
    media: mediaKhaiTruong,
    source: VERSION_SOURCES.AI_GENERATED,
    created_by: USR_EDITOR_MINH,
    created_by_name: 'Trần Văn Minh',
    created_at: demoAgo({ days: 2, hours: 3 }),
    review: {
      score: 6.5,
      summary: 'Đúng nhưng khô, thiếu địa chỉ cụ thể và chưa có lời mời khách.',
      checks: [
        {
          key: 'must_include',
          label: 'Thông tin bắt buộc',
          status: 'fail',
          message: 'Thiếu địa chỉ chi nhánh 2 và giờ mở cửa.',
        },
        {
          key: 'brand_voice',
          label: 'Giọng điệu thương hiệu',
          status: 'warn',
          message: 'Câu văn giống thông báo hành chính, chưa ấm áp.',
        },
      ],
    },
  },
  {
    // Version hiện tại — vẫn là bản nháp, cô Hương đang viết tiếp.
    version: 2,
    caption:
      'Cả nhà ơi, quán mình sắp mở chi nhánh thứ hai ở đường Trần Duy Hưng, Cầu Giấy. Chi nhánh mới rộng hơn, có chỗ để xe máy và mở từ 6h đến 22h như quán cũ. Ngày khai trương quán sẽ thông báo sau, cả nhà nhớ theo dõi Page nhé. Ai ở Cầu Giấy thì comment cho quán biết với, quán muốn mời mọi người đến thử đầu tiên! #PhoBacCoHuong #KhaiTruong #CauGiay',
    hashtags: ['#PhoBacCoHuong', '#KhaiTruong', '#CauGiay'],
    media: mediaKhaiTruong,
    source: VERSION_SOURCES.HUMAN,
    created_by: USR_OWNER_HUONG,
    created_by_name: 'Nguyễn Thị Hương',
    created_at: demoAgo({ days: 1, hours: 2 }),
    note: 'Đang chờ chốt ngày khai trương với chủ nhà rồi mới gửi duyệt.',
  },
];

// ---------------------------------------------------------------------------
// Bài viết
// ---------------------------------------------------------------------------

/**
 * 9 bài viết của quán phở, phủ HẾT `POST_STATUSES` (có bài thứ hai ở trạng thái
 * `published` để demo cả bài đăng qua API và bài người dùng tự đăng).
 */
export const demoPosts: Post[] = [
  {
    // PUBLISHED qua API — bài chủ lực, đã có số liệu hiệu suất.
    id: POST_PUBLISHED_API,
    campaign_id: CMP_PHO_TRUA,
    workspace_id: WS_FB,
    channel: CHANNELS.FACEBOOK_PAGE,
    pillar: CONTENT_PILLARS.PRODUCT,
    format: POST_FORMATS.REEL,
    status: POST_STATUSES.PUBLISHED,
    version: 3,
    current: lastVersion(versionsP01),
    publish_mode: 'now',
    requires_reapproval: false,
    created_at: demoAgo({ days: 10, hours: 3 }),
    updated_at: demoAgo({ days: 9, hours: 4 }),
  },
  {
    // PUBLISHED nhưng NGƯỜI DÙNG TỰ ĐĂNG rồi ghi nhận lại (`manual_recorded`).
    id: POST_PUBLISHED_MANUAL,
    campaign_id: CMP_PHO_TRUA,
    workspace_id: WS_FB,
    channel: CHANNELS.FACEBOOK_PAGE,
    pillar: CONTENT_PILLARS.PROMOTION,
    format: POST_FORMATS.IMAGE,
    status: POST_STATUSES.PUBLISHED,
    version: 2,
    current: lastVersion(versionsP02),
    publish_mode: 'manual',
    requires_reapproval: false,
    created_at: demoAgo({ days: 8, hours: 5 }),
    updated_at: demoAgo({ days: 8, hours: 1 }),
  },
  {
    // APPROVED — đang được gửi lên Facebook (publication `sending`).
    id: POST_APPROVED,
    campaign_id: CMP_PHO_TRUA,
    workspace_id: WS_FB,
    channel: CHANNELS.FACEBOOK_PAGE,
    pillar: CONTENT_PILLARS.BEHIND_THE_SCENES,
    format: POST_FORMATS.IMAGE,
    status: POST_STATUSES.APPROVED,
    version: 4,
    current: lastVersion(versionsP03),
    publish_mode: 'now',
    requires_reapproval: false,
    created_at: demoAgo({ days: 3, hours: 6 }),
    updated_at: demoAgo({ hours: 1 }),
  },
  {
    // APPROVED + requires_reapproval — SỬA BÀI ĐÃ DUYỆT THÌ PHẢI DUYỆT LẠI.
    // UI phải khoá nút “Đăng ngay” và giải thích: bản 3 chưa được duyệt.
    id: POST_APPROVED_REAPPROVAL,
    campaign_id: CMP_PHO_TRUA,
    workspace_id: WS_FB,
    channel: CHANNELS.FACEBOOK_PAGE,
    pillar: CONTENT_PILLARS.PROMOTION,
    format: POST_FORMATS.IMAGE,
    status: POST_STATUSES.APPROVED,
    version: 3,
    current: lastVersion(versionsP04),
    publish_mode: 'now',
    requires_reapproval: true,
    created_at: demoAgo({ days: 4, hours: 5 }),
    updated_at: demoAgo({ hours: 20 }),
  },
  {
    // SCHEDULED — sẽ tự đăng lúc 11:00 ngày 16/03/2026 (giờ Việt Nam).
    id: POST_SCHEDULED,
    campaign_id: CMP_PHO_TRUA,
    workspace_id: WS_FB,
    channel: CHANNELS.FACEBOOK_PAGE,
    pillar: CONTENT_PILLARS.PRODUCT,
    format: POST_FORMATS.IMAGE,
    status: POST_STATUSES.SCHEDULED,
    version: 2,
    current: lastVersion(versionsP05),
    scheduled_at: demoAhead({ hours: 19 }),
    publish_mode: 'scheduled',
    requires_reapproval: false,
    created_at: demoAgo({ days: 2, hours: 4 }),
    updated_at: demoAgo({ days: 1, hours: 2 }),
  },
  {
    // FAILED — đã duyệt nhưng lần gửi thứ hai không rõ kết quả (xem publishing.ts).
    id: POST_FAILED,
    campaign_id: CMP_PHO_TRUA,
    workspace_id: WS_FB,
    channel: CHANNELS.FACEBOOK_PAGE,
    pillar: CONTENT_PILLARS.COMMUNITY,
    format: POST_FORMATS.IMAGE,
    status: POST_STATUSES.FAILED,
    version: 3,
    current: lastVersion(versionsP06),
    publish_mode: 'now',
    requires_reapproval: false,
    created_at: demoAgo({ days: 3, hours: 5 }),
    updated_at: demoAgo({ days: 2, hours: 6 }),
  },
  {
    // NEEDS_REVIEW — đang chờ người có quyền duyệt (bản 2).
    id: POST_NEEDS_REVIEW,
    campaign_id: CMP_PHO_TRUA,
    workspace_id: WS_FB,
    channel: CHANNELS.FACEBOOK_PAGE,
    pillar: CONTENT_PILLARS.PRODUCT,
    format: POST_FORMATS.CAROUSEL,
    status: POST_STATUSES.NEEDS_REVIEW,
    version: 2,
    current: lastVersion(versionsP07),
    requires_reapproval: false,
    created_at: demoAgo({ days: 1, hours: 4 }),
    updated_at: demoAgo({ hours: 5 }),
  },
  {
    // REJECTED — kèm lý do tiếng Việt để UI hiển thị ngay trên thẻ bài.
    id: POST_REJECTED,
    campaign_id: CMP_PHO_TRUA,
    workspace_id: WS_FB,
    channel: CHANNELS.FACEBOOK_PAGE,
    pillar: CONTENT_PILLARS.PROMOTION,
    format: POST_FORMATS.IMAGE,
    status: POST_STATUSES.REJECTED,
    version: 2,
    current: lastVersion(versionsP08),
    requires_reapproval: false,
    rejection_reason:
      'Bài ghi “giảm 30% tất cả các món” nhưng tháng này quán chỉ giảm cho combo trưa. Minh sửa lại đúng mức giảm rồi gửi duyệt lại giúp cô nhé.',
    created_at: demoAgo({ days: 2, hours: 6 }),
    updated_at: demoAgo({ days: 1, hours: 4 }),
  },
  {
    // DRAFT — bản nháp trong campaign khai trương chi nhánh 2.
    id: POST_DRAFT,
    campaign_id: CMP_PHO_CHI_NHANH_2,
    workspace_id: WS_FB,
    channel: CHANNELS.FACEBOOK_PAGE,
    pillar: CONTENT_PILLARS.COMMUNITY,
    format: POST_FORMATS.IMAGE,
    status: POST_STATUSES.DRAFT,
    version: 2,
    current: lastVersion(versionsP09),
    requires_reapproval: false,
    created_at: demoAgo({ days: 2, hours: 3 }),
    updated_at: demoAgo({ days: 1, hours: 2 }),
  },
];

/**
 * Lịch sử phiên bản của từng bài (`GET /posts/{id}/versions`).
 * `pending_approval_version` chỉ có ở bài đang chờ duyệt — dùng để duyệt ĐÚNG bản.
 */
export const demoPostVersions: Record<DemoPostId, PostVersionList> = {
  [POST_PUBLISHED_API]: {
    post_id: POST_PUBLISHED_API,
    versions: versionsP01,
    current_version: 3,
  },
  [POST_PUBLISHED_MANUAL]: {
    post_id: POST_PUBLISHED_MANUAL,
    versions: versionsP02,
    current_version: 2,
  },
  [POST_APPROVED]: {
    post_id: POST_APPROVED,
    versions: versionsP03,
    current_version: 4,
  },
  [POST_APPROVED_REAPPROVAL]: {
    post_id: POST_APPROVED_REAPPROVAL,
    versions: versionsP04,
    current_version: 3,
    // Bản 2 đã duyệt; bản 3 mới sửa nên chưa có bản nào đang chờ duyệt.
  },
  [POST_SCHEDULED]: {
    post_id: POST_SCHEDULED,
    versions: versionsP05,
    current_version: 2,
  },
  [POST_FAILED]: {
    post_id: POST_FAILED,
    versions: versionsP06,
    current_version: 3,
  },
  [POST_NEEDS_REVIEW]: {
    post_id: POST_NEEDS_REVIEW,
    versions: versionsP07,
    current_version: 2,
    // Đang chờ duyệt bản 2 — nút Duyệt phải gửi kèm version này.
    pending_approval_version: 2,
  },
  [POST_REJECTED]: {
    post_id: POST_REJECTED,
    versions: versionsP08,
    current_version: 2,
  },
  [POST_DRAFT]: {
    post_id: POST_DRAFT,
    versions: versionsP09,
    current_version: 2,
  },
};

// ---------------------------------------------------------------------------
// Export & bản nháp brief (dữ liệu phụ trợ cho UI)
// ---------------------------------------------------------------------------

/**
 * Tệp export của campaign: một tệp đã xong, một tệp đang chờ dựng, một tệp lỗi.
 * LƯU Ý: export KHÔNG phải là “đã đăng bài” — UI không được gộp hai việc này.
 */
export const demoExportJobs: ExportJob[] = [
  {
    id: EXPORT_READY,
    campaign_id: CMP_PHO_TRUA,
    format: EXPORT_FORMATS.XLSX,
    status: 'ready',
    download_url: 'https://cdn.demo.local/exports/combo-trua-thang-3.xlsx',
    filename: 'combo-trua-van-phong-thang-3-2026.xlsx',
    size: 48_216,
    created_at: demoAgo({ days: 1, hours: 3 }),
    ready_at: demoAgo({ days: 1, hours: 3 }),
  },
  {
    // Đang chờ trong hàng đợi — khớp với job `JOB_EXPORT_QUEUED` trong jobs.ts.
    id: EXPORT_QUEUED,
    campaign_id: CMP_PHO_CHI_NHANH_2,
    format: EXPORT_FORMATS.CSV,
    status: 'queued',
    job_id: JOB_EXPORT_QUEUED,
    created_at: demoAgo({ minutes: 2 }),
  },
  {
    // Lỗi khi dựng tệp: UI phải hiện thông điệp tiếng Việt và cho thử lại.
    id: EXPORT_FAILED,
    campaign_id: CMP_PHO_TRUA,
    format: EXPORT_FORMATS.CSV,
    status: 'failed',
    error: {
      code: 'export_too_many_rows',
      message:
        'Chiến dịch có 8 bài nhưng chỉ chọn được 0 bài để xuất. Hãy chọn ít nhất một bài rồi xuất lại.',
    },
    created_at: demoAgo({ days: 2, hours: 4 }),
  },
];

/**
 * Bản nháp điều chỉnh brief do “Áp dụng khuyến nghị” tạo ra — CHỜ người dùng
 * xem lại, không tự đổi campaign đang chạy.
 */
export const demoBriefRevisionDrafts: BriefRevisionDraft[] = [
  {
    id: BRIEF_DRAFT_CS2,
    campaign_id: CMP_PHO_CHI_NHANH_2,
    base_version: 2,
    changes: [
      {
        field: 'audience',
        label: 'Khán giả mục tiêu',
        before: [
          'Khách quen hiện tại sống ở khu Cầu Giấy – Thanh Xuân',
          'Nhân viên văn phòng toà nhà trên đường Trần Duy Hưng',
        ],
        after: [
          'Khách quen hiện tại sống ở khu Cầu Giấy – Thanh Xuân',
          'Nhân viên văn phòng toà nhà trên đường Trần Duy Hưng',
          'Phụ huynh đưa con đi học ở các trường quanh Trần Duy Hưng',
        ],
        rationale:
          'Bằng chứng cho thấy nhóm phụ huynh chiếm 22% lượt tiếp cận khung 6h–7h, nhưng brief chưa nhắc tới nhóm này.',
      },
      {
        field: 'must_include',
        label: 'Thông tin bắt buộc',
        before: ['Địa chỉ chi nhánh 2', 'Giờ mở cửa 06:00–22:00'],
        after: [
          'Địa chỉ chi nhánh 2',
          'Giờ mở cửa 06:00–22:00',
          'Chỗ để xe máy cho khách',
        ],
        rationale: 'Bình luận của khách hỏi về chỗ để xe nhiều nhất trong tháng 2.',
      },
    ],
    source_recommendation_id: REC_GIO_DANG,
    status: 'pending_review',
    created_at: demoAgo({ hours: 6 }),
  },
  {
    id: BRIEF_DRAFT_TRUA,
    campaign_id: CMP_PHO_TRUA,
    base_version: 3,
    changes: [
      {
        field: 'key_message',
        label: 'Thông điệp chính',
        before:
          'Bữa trưa nóng hổi, nước dùng ninh 12 tiếng, lên món trong 5 phút – chỉ 55.000đ.',
        after:
          'Bữa trưa nóng hổi, nước dùng ninh 12 tiếng, lên món trong 5 phút – đặt trước là có ngay.',
        rationale:
          'Giá đã thay đổi từ 20/3 nên thông điệp không nên gắn cứng vào con số giá.',
      },
    ],
    source_recommendation_id: REC_CAROUSEL,
    status: 'discarded',
    created_at: demoAgo({ days: 1, hours: 5 }),
  },
];

/** Danh sách id bài viết — UI dùng để lọc/đối chiếu nhanh khi demo. */
export const demoPostIds = POST_IDS;
