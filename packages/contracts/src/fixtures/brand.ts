/**
 * DEMO FIXTURE — Brand Profile (kiến thức thương hiệu đã trích xuất) & sản phẩm.
 *
 * MỤC ĐÍCH: demo đủ 5 trạng thái của một trường (`FIELD_REVIEW_STATES`) trong
 * CÙNG một profile, vì đây là màn hình khó nhất của sản phẩm:
 * - `confirmed` : người dùng đã xác nhận (kèm trích dẫn nguồn để xem lại).
 * - `suggested` : AI gợi ý, CÓ `confidence`, cần người dùng xác nhận.
 * - `conflict`  : hai tài liệu nói khác nhau → có 2 `alternatives` để chọn.
 * - `missing`   : chưa có thông tin, cần bổ sung.
 * - `edited`    : người dùng sửa tay (dùng ở profile workspace bán lẻ).
 *
 * Ghi chú nghiệp vụ: profile quán phở đã được xác nhận ngày 19/02/2026, nhưng
 * sau đó quán tải thêm báo cáo Fanpage nên 3 trường được trích xuất lại và đang
 * chờ xác nhận (`suggested` / `conflict` / `missing`) → `completeness` = 0.7.
 */

import type { BrandProduct, BrandProfile } from '../brand';
import { BRAND_FIELD_KEYS, FIELD_REVIEW_STATES } from '../enums';
import {
  DOC_FB_BRAND_GUIDE,
  DOC_FB_FANPAGE_REPORT,
  DOC_FB_MENU,
  DOC_RETAIL_CATALOG,
  DOC_RETAIL_SUPPLIER_CSV,
  PROD_COMBO_TRUA,
  PROD_PHO_BO_TAI_NAM,
  PROD_PHO_CHAY_NAM,
  PROD_PHO_CUON,
  PROD_PHO_GA_TA,
  PROD_RETAIL_DAU_AN,
  PROD_RETAIL_GAO_ST25,
  PROD_RETAIL_NUOC_MAM,
  WS_EMPTY,
  WS_FB,
  WS_RETAIL,
  USR_EDITOR_MINH,
  USR_OWNER_HUONG,
  demoAgo,
  type DemoWorkspaceId,
} from './ids';

/**
 * Sản phẩm của quán phở — nguồn của trường `products` và của `product_ids`
 * trong Campaign Brief. Giá là giá thật ở mức quán nhỏ (55.000đ – 75.000đ).
 */
export const demoProducts: BrandProduct[] = [
  {
    id: PROD_PHO_BO_TAI_NAM,
    name: 'Phở bò tái nạm',
    description: 'Bát phở bò tái nạm đầy đặn, nước dùng ninh xương ống 12 tiếng.',
    price_range: '55.000đ – 70.000đ',
    usp: ['Nước dùng ninh 12 tiếng', 'Bánh phở tráng tay trong ngày'],
  },
  {
    id: PROD_PHO_GA_TA,
    name: 'Phở gà ta',
    description: 'Phở gà ta thả vườn, thịt chắc và ngọt nước.',
    price_range: '50.000đ – 65.000đ',
    usp: ['Gà ta thả vườn lấy mỗi sáng'],
  },
  {
    id: PROD_COMBO_TRUA,
    name: 'Combo trưa văn phòng',
    description:
      'Một bát phở bò tái nạm, một đĩa quẩy nóng và một cốc trà đá, phục vụ trong 5 phút.',
    price_range: '55.000đ',
    usp: ['Lên món trong 5 phút', 'Đặt trước qua điện thoại', 'Giá cố định cho khách văn phòng'],
  },
  {
    id: PROD_PHO_CHAY_NAM,
    name: 'Phở chay nấm hương',
    description: 'Nước dùng nấu từ củ sen, nấm hương và táo đỏ, ăn chay được cả tháng.',
    price_range: '45.000đ – 55.000đ',
    usp: ['Nước dùng chay nấu riêng, không dùng nồi nước thịt'],
  },
  {
    id: PROD_PHO_CUON,
    name: 'Phở cuốn Cửa Bắc',
    description: 'Phở cuốn nhân bò xào và rau sống, dùng kèm nước chấm chua ngọt.',
    price_range: '60.000đ – 75.000đ',
    usp: ['Bán từ 15h hằng ngày', 'Món đông khách nhất buổi chiều'],
  },
];

/**
 * Brand Profile theo workspace:
 * - Quán phở: gần đủ, giàu trích dẫn, có `suggested` + `conflict` + `missing`.
 * - Tạp hoá : mới nhập một nửa, `products` còn ở mức gợi ý của AI.
 * - Rỗng    : mọi trường `missing`, `completeness = 0` → demo empty state + checklist.
 */
export const demoBrandProfiles: Record<DemoWorkspaceId, BrandProfile> = {
  [WS_FB]: {
    id: 'bp_pho_bac_co_huong_v4',
    workspace_id: WS_FB,
    version: 4,

    // CONFIRMED — trường nền tảng, trích thẳng từ hồ sơ thương hiệu.
    business_name: {
      key: BRAND_FIELD_KEYS.BUSINESS_NAME,
      label: 'Tên thương hiệu',
      value: 'Quán Phở Bắc Cô Hương',
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [
        {
          document_id: DOC_FB_BRAND_GUIDE,
          document_name: 'ho-so-thuong-hieu-pho-bac-co-huong-2026.pdf',
          page: 1,
          quote:
            'Tên thương hiệu: Quán Phở Bắc Cô Hương. Thành lập năm 2016 tại 18 phố Cửa Bắc, Ba Đình, Hà Nội.',
          char_start: 0,
          char_end: 104,
        },
      ],
      updated_at: demoAgo({ days: 24 }),
      updated_by: USR_OWNER_HUONG,
    },

    // CONFIRMED
    industry: {
      key: BRAND_FIELD_KEYS.INDUSTRY,
      label: 'Ngành nghề',
      value: 'Ăn uống – quán ăn phục vụ tại chỗ & đồ ăn mang về',
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [
        {
          document_id: DOC_FB_BRAND_GUIDE,
          document_name: 'ho-so-thuong-hieu-pho-bac-co-huong-2026.pdf',
          page: 1,
          quote:
            'Lĩnh vực kinh doanh: quán ăn phục vụ tại chỗ và bán mang về, phục vụ bữa sáng và bữa trưa.',
        },
      ],
      updated_at: demoAgo({ days: 24 }),
      updated_by: USR_OWNER_HUONG,
    },

    // CONFIRMED — mô tả dài, gộp bằng chứng từ 2 tài liệu.
    description: {
      key: BRAND_FIELD_KEYS.DESCRIPTION,
      label: 'Giới thiệu doanh nghiệp',
      value:
        'Quán Phở Bắc Cô Hương mở từ năm 2016 tại 18 phố Cửa Bắc, Ba Đình, Hà Nội. Nước dùng được ninh từ xương ống bò trong 12 tiếng, bánh phở tráng tay mỗi sáng, thịt bò lấy từ mối quen ở chợ Ngọc Hà. Quán có 32 chỗ ngồi, phục vụ bữa sáng và bữa trưa, đông nhất là khung 11h–13h với khách văn phòng quanh phố.',
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [
        {
          document_id: DOC_FB_BRAND_GUIDE,
          document_name: 'ho-so-thuong-hieu-pho-bac-co-huong-2026.pdf',
          page: 2,
          quote:
            'Quán có 32 chỗ ngồi, phục vụ bữa sáng và bữa trưa. Nước dùng ninh từ xương ống bò trong 12 tiếng, bánh phở tráng tay trong ngày.',
          char_start: 1_240,
          char_end: 1_362,
        },
        {
          document_id: DOC_FB_FANPAGE_REPORT,
          document_name: 'bao-cao-fanpage-thang-2.pdf',
          page: 1,
          quote:
            'Khung giờ đông khách nhất của Page là 11h–13h các ngày trong tuần, chiếm 46% lượt tương tác của tháng 2.',
        },
      ],
      updated_at: demoAgo({ days: 24 }),
      updated_by: USR_OWNER_HUONG,
    },

    // CONFIRMED — mảng sản phẩm, mỗi sản phẩm trích từ một dòng trong tệp thực đơn.
    products: {
      key: BRAND_FIELD_KEYS.PRODUCTS,
      label: 'Sản phẩm / dịch vụ',
      value: demoProducts,
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [
        {
          document_id: DOC_FB_MENU,
          document_name: 'thuc-don-thang-3-2026.xlsx',
          sheet: 'Thực đơn',
          row: 2,
          quote: 'Phở bò tái nạm | 55.000 – 70.000 | Nước dùng ninh 12 tiếng',
        },
        {
          document_id: DOC_FB_MENU,
          document_name: 'thuc-don-thang-3-2026.xlsx',
          sheet: 'Thực đơn',
          row: 3,
          quote: 'Combo trưa văn phòng | 55.000 | Phở bò tái nạm + quẩy + trà đá, lên món trong 5 phút',
        },
        {
          document_id: DOC_FB_MENU,
          document_name: 'thuc-don-thang-3-2026.xlsx',
          sheet: 'Thực đơn',
          row: 4,
          quote: 'Phở chay nấm hương | 45.000 – 55.000 | Nước dùng chay nấu riêng',
        },
      ],
      updated_at: demoAgo({ days: 24 }),
      updated_by: USR_OWNER_HUONG,
    },

    // CONFLICT — hai tài liệu nói khác nhau về khán giả mục tiêu.
    // UI phải cho người dùng CHỌN một phương án, không tự quyết.
    target_audience: {
      key: BRAND_FIELD_KEYS.TARGET_AUDIENCE,
      label: 'Khán giả mục tiêu',
      value: [
        'Nhân viên văn phòng 22–35 tuổi làm việc trong bán kính 1 km quanh phố Cửa Bắc',
        'Khách quen đã ăn tại quán ít nhất 2 lần',
      ],
      state: FIELD_REVIEW_STATES.CONFLICT,
      provenance: [
        {
          document_id: DOC_FB_BRAND_GUIDE,
          document_name: 'ho-so-thuong-hieu-pho-bac-co-huong-2026.pdf',
          page: 3,
          quote:
            'Khách hàng mục tiêu: nhân viên văn phòng và người đi làm quanh khu Cửa Bắc, độ tuổi 22–35, ăn trưa nhanh và quay lại thường xuyên.',
          char_start: 2_018,
          char_end: 2_140,
        },
      ],
      alternatives: [
        {
          value: [
            'Nhân viên văn phòng 22–35 tuổi làm việc trong bán kính 1 km quanh phố Cửa Bắc',
            'Khách quen đã ăn tại quán ít nhất 2 lần',
          ],
          provenance: [
            {
              document_id: DOC_FB_BRAND_GUIDE,
              document_name: 'ho-so-thuong-hieu-pho-bac-co-huong-2026.pdf',
              page: 3,
              quote:
                'Khách hàng mục tiêu: nhân viên văn phòng và người đi làm quanh khu Cửa Bắc, độ tuổi 22–35, ăn trưa nhanh và quay lại thường xuyên.',
              char_start: 2_018,
              char_end: 2_140,
            },
          ],
        },
        {
          value: [
            'Sinh viên và người trẻ 18–25 tuổi đi ăn theo nhóm 3–5 người',
            'Khách du lịch nước ngoài tìm phở Bắc truyền thống',
          ],
          provenance: [
            {
              document_id: DOC_FB_FANPAGE_REPORT,
              document_name: 'bao-cao-fanpage-thang-2.pdf',
              page: 2,
              quote:
                'Nhóm 18–25 tuổi chiếm 41% lượt tiếp cận của Page trong tháng 2; nhiều bình luận hỏi nhóm 4–5 người có cần đặt bàn không.',
            },
          ],
        },
      ],
      updated_at: demoAgo({ days: 2 }),
    },

    // CONFIRMED — giọng điệu thương hiệu.
    brand_voice: {
      key: BRAND_FIELD_KEYS.BRAND_VOICE,
      label: 'Giọng điệu thương hiệu',
      value:
        'Thân thiện, ấm áp, nói chuyện như hàng xóm lâu năm. Xưng “quán”, gọi khách là “bạn”; không dùng từ ngữ quảng cáo quá đà hay so sánh dìm quán khác.',
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [
        {
          document_id: DOC_FB_BRAND_GUIDE,
          document_name: 'ho-so-thuong-hieu-pho-bac-co-huong-2026.pdf',
          page: 4,
          quote:
            'Giọng điệu khi viết cho khách: gần gũi, ấm áp, như người nhà. Tránh giọng bán hàng gấp gáp, tránh so sánh với quán khác.',
        },
      ],
      updated_at: demoAgo({ days: 24 }),
      updated_by: USR_OWNER_HUONG,
    },

    // SUGGESTED — AI suy ra từ 3 bài đăng cũ, độ tin cậy chỉ 0.62 nên CẦN xác nhận.
    tone_keywords: {
      key: BRAND_FIELD_KEYS.TONE_KEYWORDS,
      label: 'Từ khoá giọng điệu',
      value: ['gần gũi', 'ấm áp', 'truyền thống', 'vui vẻ nhẹ nhàng'],
      state: FIELD_REVIEW_STATES.SUGGESTED,
      confidence: 0.62,
      provenance: [
        {
          document_id: DOC_FB_FANPAGE_REPORT,
          document_name: 'bao-cao-fanpage-thang-2.pdf',
          page: 3,
          quote:
            'Ba bài viết có tương tác cao nhất tháng 2 đều dùng cách gọi “quán mình” và kể chuyện nấu nước dùng, không dùng từ ngữ khuyến mãi mạnh.',
        },
      ],
      updated_at: demoAgo({ days: 2 }),
    },

    // MISSING — chưa có tài liệu nào nói về điều KHÔNG nên dùng → cần người dùng tự nhập.
    do_not_use: {
      key: BRAND_FIELD_KEYS.DO_NOT_USE,
      label: 'Điều cần tránh khi viết bài',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
      updated_at: demoAgo({ days: 2 }),
    },

    // CONFIRMED — đối thủ cùng khu vực.
    competitors: {
      key: BRAND_FIELD_KEYS.COMPETITORS,
      label: 'Đối thủ chính',
      value: [
        'Phở Bắc Hà Thành – cùng phố Cửa Bắc',
        'Phở Cô Thắm – phố Đặng Dung',
        'Chuỗi Phở 24 – chi nhánh gần quán',
      ],
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [
        {
          document_id: DOC_FB_BRAND_GUIDE,
          document_name: 'ho-so-thuong-hieu-pho-bac-co-huong-2026.pdf',
          page: 6,
          quote:
            'Đối thủ trực tiếp trong bán kính 500 m: Phở Bắc Hà Thành (cùng phố), Phở Cô Thắm (phố Đặng Dung) và chi nhánh Phở 24 gần ngã tư.',
        },
      ],
      updated_at: demoAgo({ days: 24 }),
      updated_by: USR_OWNER_HUONG,
    },

    // CONFIRMED — thông tin liên hệ dạng bảng khoá–giá trị.
    contact: {
      key: BRAND_FIELD_KEYS.CONTACT,
      label: 'Thông tin liên hệ',
      value: {
        phone: '024 3825 1976',
        zalo: '0912 345 678',
        email: 'hello@phobaccohuong.vn',
        address: '18 phố Cửa Bắc, Ba Đình, Hà Nội',
        fanpage: 'facebook.com/phobaccohuong',
        opening_hours: '06:00 – 22:00 hằng ngày',
      },
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [
        {
          document_id: DOC_FB_BRAND_GUIDE,
          document_name: 'ho-so-thuong-hieu-pho-bac-co-huong-2026.pdf',
          page: 12,
          quote:
            'Liên hệ: 18 phố Cửa Bắc, Ba Đình, Hà Nội. Điện thoại 024 3825 1976. Mở cửa 06:00 – 22:00 hằng ngày.',
        },
      ],
      updated_at: demoAgo({ days: 24 }),
      updated_by: USR_OWNER_HUONG,
    },

    // Đã xác nhận toàn bộ ngày 19/02/2026 (trước khi tải thêm báo cáo Fanpage).
    confirmed_at: demoAgo({ days: 24 }),
    confirmed_by: USR_OWNER_HUONG,
    // 7/10 trường đã xác nhận; còn 1 gợi ý + 1 mâu thuẫn + 1 thiếu.
    completeness: 0.7,
    updated_at: demoAgo({ days: 2 }),
  },

  [WS_RETAIL]: {
    id: 'bp_tap_hoa_an_nhien_v1',
    workspace_id: WS_RETAIL,
    version: 1,

    // CONFIRMED — chủ cửa hàng tự nhập.
    business_name: {
      key: BRAND_FIELD_KEYS.BUSINESS_NAME,
      label: 'Tên thương hiệu',
      value: 'Tạp hoá An Nhiên',
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [],
      updated_at: demoAgo({ days: 17 }),
      updated_by: USR_EDITOR_MINH,
    },

    // CONFIRMED
    industry: {
      key: BRAND_FIELD_KEYS.INDUSTRY,
      label: 'Ngành nghề',
      value: 'Bán lẻ – tạp hoá & đồ dùng gia đình',
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [],
      updated_at: demoAgo({ days: 17 }),
      updated_by: USR_EDITOR_MINH,
    },

    // EDITED — AI gợi ý ngắn, người dùng sửa lại thành câu đầy đủ hơn.
    description: {
      key: BRAND_FIELD_KEYS.DESCRIPTION,
      label: 'Giới thiệu doanh nghiệp',
      value:
        'Tạp hoá An Nhiên bán gạo, dầu ăn, nước mắm và đồ dùng thiết yếu cho các hộ gia đình trong ngõ 42 phố Kim Mã. Cửa hàng mở 6h30–21h30, giao hàng miễn phí trong bán kính 2 km cho đơn từ 150.000đ.',
      state: FIELD_REVIEW_STATES.EDITED,
      provenance: [
        {
          document_id: DOC_RETAIL_SUPPLIER_CSV,
          document_name: 'hoa-don-nha-cung-cap-thang-2.csv',
          sheet: 'HoaDon',
          row: 2,
          quote: 'Gạo ST25 túi 5kg | 24 bao | đại lý gạo Cô Lan | 165.000đ/bao',
        },
      ],
      updated_at: demoAgo({ days: 15 }),
      updated_by: USR_EDITOR_MINH,
    },

    // SUGGESTED — AI đọc danh mục sản phẩm và gợi ý, độ tin cậy thấp (0.55).
    products: {
      key: BRAND_FIELD_KEYS.PRODUCTS,
      label: 'Sản phẩm / dịch vụ',
      value: [
        {
          id: PROD_RETAIL_GAO_ST25,
          name: 'Gạo ST25 túi 5kg',
          price_range: '165.000đ – 180.000đ',
          usp: ['Gạo mới về mỗi tuần'],
        },
        {
          id: PROD_RETAIL_DAU_AN,
          name: 'Dầu ăn đậu nành 1L',
          price_range: '48.000đ – 55.000đ',
        },
        {
          id: PROD_RETAIL_NUOC_MAM,
          name: 'Nước mắm cá cơm 500ml',
          price_range: '62.000đ – 75.000đ',
        },
      ] satisfies BrandProduct[],
      state: FIELD_REVIEW_STATES.SUGGESTED,
      confidence: 0.55,
      provenance: [
        {
          document_id: DOC_RETAIL_CATALOG,
          document_name: 'danh-muc-san-pham-an-nhien.xlsx',
          sheet: 'Danh mục',
          row: 2,
          quote: 'Gạo ST25 | túi 5kg | 165.000 – 180.000 | nhà cung cấp: đại lý gạo Cô Lan',
        },
        {
          document_id: DOC_RETAIL_CATALOG,
          document_name: 'danh-muc-san-pham-an-nhien.xlsx',
          sheet: 'Danh mục',
          row: 8,
          quote: 'Dầu ăn đậu nành | chai 1L | 48.000 – 55.000',
        },
      ],
      updated_at: demoAgo({ days: 3 }),
    },

    // MISSING — chưa nhập khán giả mục tiêu.
    target_audience: {
      key: BRAND_FIELD_KEYS.TARGET_AUDIENCE,
      label: 'Khán giả mục tiêu',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },

    // MISSING
    brand_voice: {
      key: BRAND_FIELD_KEYS.BRAND_VOICE,
      label: 'Giọng điệu thương hiệu',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },

    // MISSING
    tone_keywords: {
      key: BRAND_FIELD_KEYS.TONE_KEYWORDS,
      label: 'Từ khoá giọng điệu',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },

    // MISSING
    do_not_use: {
      key: BRAND_FIELD_KEYS.DO_NOT_USE,
      label: 'Điều cần tránh khi viết bài',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },

    // MISSING
    competitors: {
      key: BRAND_FIELD_KEYS.COMPETITORS,
      label: 'Đối thủ chính',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },

    // CONFIRMED — chủ cửa hàng tự nhập.
    contact: {
      key: BRAND_FIELD_KEYS.CONTACT,
      label: 'Thông tin liên hệ',
      value: {
        phone: '024 3726 4488',
        zalo: '0987 654 321',
        address: '42 ngõ 145 phố Kim Mã, Ba Đình, Hà Nội',
        opening_hours: '06:30 – 21:30 hằng ngày',
      },
      state: FIELD_REVIEW_STATES.CONFIRMED,
      provenance: [],
      updated_at: demoAgo({ days: 17 }),
      updated_by: USR_EDITOR_MINH,
    },

    // CHƯA xác nhận toàn bộ → không có `confirmed_at` → chưa tạo được campaign.
    // 4/10 trường đã xác nhận hoặc sửa tay.
    completeness: 0.4,
    updated_at: demoAgo({ days: 3 }),
  },

  // Workspace mới: chưa nhập gì, mọi trường `missing` → demo empty state & checklist.
  [WS_EMPTY]: {
    id: 'bp_workspace_moi_v1',
    workspace_id: WS_EMPTY,
    version: 1,
    business_name: {
      key: BRAND_FIELD_KEYS.BUSINESS_NAME,
      label: 'Tên thương hiệu',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    industry: {
      key: BRAND_FIELD_KEYS.INDUSTRY,
      label: 'Ngành nghề',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    description: {
      key: BRAND_FIELD_KEYS.DESCRIPTION,
      label: 'Giới thiệu doanh nghiệp',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    products: {
      key: BRAND_FIELD_KEYS.PRODUCTS,
      label: 'Sản phẩm / dịch vụ',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    target_audience: {
      key: BRAND_FIELD_KEYS.TARGET_AUDIENCE,
      label: 'Khán giả mục tiêu',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    brand_voice: {
      key: BRAND_FIELD_KEYS.BRAND_VOICE,
      label: 'Giọng điệu thương hiệu',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    tone_keywords: {
      key: BRAND_FIELD_KEYS.TONE_KEYWORDS,
      label: 'Từ khoá giọng điệu',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    do_not_use: {
      key: BRAND_FIELD_KEYS.DO_NOT_USE,
      label: 'Điều cần tránh khi viết bài',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    competitors: {
      key: BRAND_FIELD_KEYS.COMPETITORS,
      label: 'Đối thủ chính',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    contact: {
      key: BRAND_FIELD_KEYS.CONTACT,
      label: 'Thông tin liên hệ',
      value: null,
      state: FIELD_REVIEW_STATES.MISSING,
      provenance: [],
    },
    completeness: 0,
    updated_at: demoAgo({ days: 2 }),
  },
};
