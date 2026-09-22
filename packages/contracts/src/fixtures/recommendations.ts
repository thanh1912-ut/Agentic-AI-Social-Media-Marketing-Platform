/**
 * DEMO FIXTURE — Khuyến nghị có bằng chứng (`Recommendation`).
 *
 * MỤC ĐÍCH: demo cấu trúc bắt buộc **bằng chứng → giả thuyết → hành động**, và
 * dạy người dùng rằng không phải khuyến nghị nào cũng đáng tin như nhau:
 * - `strong` / `moderate` : có số liệu lặp lại, nói rõ mẫu bao nhiêu bài.
 * - `weak`                : mẫu nhỏ, chỉ nên tham khảo.
 * - `insufficient`        : MẪU QUÁ NHỎ — `strength_reason` phải nói thẳng là
 *   chưa đủ dữ liệu để kết luận, không được giấu.
 *
 * `demoRecommendations` gồm 3 khuyến nghị phủ `new` / `acknowledged` / `applied`;
 * `demoDismissedRecommendation` tách riêng để phủ nốt trạng thái `dismissed`.
 *
 * Mọi khuyến nghị đều `origin: 'demo'` — UI phải hiện nhãn “Dữ liệu demo”.
 */

import type { MeasurementWindow } from '../common';
import type { Recommendation, RecommendationEvidence } from '../recommendation';
import {
  EVIDENCE_STRENGTHS,
  METRIC_KEYS,
  RECOMMENDATION_ACTIONS,
  RECOMMENDATION_FEEDBACK,
  RECOMMENDATION_STATUSES,
} from '../enums';
import {
  CMP_PHO_CHI_NHANH_2,
  CMP_PHO_TRUA,
  DEMO_TIMEZONE,
  REC_DISMISSED,
  REC_GIO_DANG,
  REC_PHU_HUYNH_SANG,
  REC_REEL_15S,
  USR_OWNER_HUONG,
  WS_FB,
  demoAgo,
  demoAhead,
} from './ids';

/** Cửa sổ 60 ngày dùng để phân tích cho khuyến nghị (15/01–14/03/2026). */
const ANALYSIS_WINDOW: MeasurementWindow = {
  start: '2026-01-15',
  end: '2026-03-14',
  timezone: DEMO_TIMEZONE,
};

/** Cửa sổ 14 ngày gần nhất (01/03–14/03/2026) — khớp với `demoAnalytics`. */
const RECENT_WINDOW: MeasurementWindow = {
  start: '2026-03-01',
  end: '2026-03-14',
  timezone: DEMO_TIMEZONE,
};

/** Đường dẫn xem chi tiết trên dashboard — UI mở đúng bộ lọc thay vì bắt tự tìm. */
function drilldown(query: string): string {
  return `/workspaces/${WS_FB}/analytics?${query}`;
}

/**
 * Khuyến nghị 1 — ĐÃ ÁP DỤNG: thêm nhóm phụ huynh buổi sáng vào chiến dịch
 * khai trương chi nhánh 2. Kết quả áp dụng là một `BriefRevisionDraft` đang chờ
 * người dùng xem lại (xem `demoBriefRevisionDrafts` trong campaigns.ts).
 */
const recPhuHuynhSang: Recommendation = {
  id: REC_PHU_HUYNH_SANG,
  workspace_id: WS_FB,
  campaign_id: CMP_PHO_CHI_NHANH_2,
  status: RECOMMENDATION_STATUSES.APPLIED,
  title: 'Thêm nhóm phụ huynh đưa con đi học vào khán giả chiến dịch',
  hypothesis:
    'Khung 6h–7h có một nhóm khách ăn sáng rồi đưa con đi học. Nhóm này chưa có trong brief khai trương chi nhánh 2, nên chiến dịch đang bỏ sót một phần khách ngay trước cửa.',
  action: RECOMMENDATION_ACTIONS.CAMPAIGN_BRIEF_REVISION,
  action_label: 'Tạo bản nháp điều chỉnh brief: thêm nhóm phụ huynh vào khán giả',
  expected_effect:
    'Nếu thêm nhóm phụ huynh và nêu chỗ để xe, dự kiến lượt tiếp cận khung 6h–7h tăng khoảng 15–20% trong tháng khai trương.',
  confidence: EVIDENCE_STRENGTHS.MODERATE,
  evidence: [
    {
      id: 'ev_phu_huynh_1',
      label:
        'Phụ huynh đưa con đi học chiếm 22% lượt tiếp cận khung 6h–7h (682/3.100 lượt)',
      metric: METRIC_KEYS.REACH,
      observed: 682,
      baseline: 3_100,
      sample_size: 14,
      window: RECENT_WINDOW,
      strength: EVIDENCE_STRENGTHS.MODERATE,
      strength_reason:
        'Số liệu đều qua 14 ngày và lặp lại vào các ngày trong tuần, nhưng chỉ từ một Page nhỏ nên chưa thể coi là bằng chứng mạnh.',
      drilldown_href: drilldown(
        'level=post&window_start=2026-03-01&window_end=2026-03-14&hour=6-7',
      ),
    },
    {
      id: 'ev_phu_huynh_2',
      label: 'Có 8/57 bình luận tháng 2 hỏi quán có chỗ để xe máy không',
      metric: METRIC_KEYS.COMMENTS,
      observed: 8,
      baseline: 57,
      sample_size: 57,
      window: ANALYSIS_WINDOW,
      strength: EVIDENCE_STRENGTHS.WEAK,
      strength_reason:
        'Chỉ 57 bình luận trong cả tháng 2 — đủ để tham khảo, chưa đủ để kết luận chắc chắn.',
      drilldown_href: drilldown(
        'level=post&window_start=2026-02-01&window_end=2026-02-28&metric=comments',
      ),
    },
  ],
  origin: 'demo',
  created_at: demoAgo({ days: 1, hours: 8 }),
  expires_at: demoAhead({ days: 20 }),
};

/**
 * Khuyến nghị 2 — ĐÃ XEM nhưng CHƯA áp dụng: dời bài giới thiệu món sang khung
 * 11:00–12:30. Bằng chứng mạnh nhất trong bộ demo (có cả đỉnh 08/03).
 */
const recGioDang: Recommendation = {
  id: REC_GIO_DANG,
  workspace_id: WS_FB,
  campaign_id: CMP_PHO_TRUA,
  status: RECOMMENDATION_STATUSES.ACKNOWLEDGED,
  title: 'Dời bài giới thiệu món sang khung 11:00–12:30',
  hypothesis:
    'Khách ăn trưa quyết định món ngay trước bữa trưa. Bài đăng trong khung 11h–12h30 tiếp cận đúng lúc khách đang chọn chỗ ăn, nên hiệu quả cao hơn hẳn bài đăng buổi tối.',
  action: RECOMMENDATION_ACTIONS.STRATEGY_REVISION,
  action_label: 'Tạo bản nháp điều chỉnh lịch đăng: dồn bài món sang khung 11:00–12:30',
  expected_effect:
    'Nếu chuyển 4 bài giới thiệu món mỗi tháng sang khung 11:00–12:30, dự kiến lượt tiếp cận trung bình mỗi bài tăng khoảng 25%.',
  confidence: EVIDENCE_STRENGTHS.STRONG,
  evidence: [
    {
      id: 'ev_gio_dang_1',
      label:
        'Bài đăng khung 11h–13h có lượt tiếp cận trung bình cao hơn 38% so với bài đăng sau 19h',
      metric: METRIC_KEYS.REACH,
      observed: 4_180,
      baseline: 3_030,
      sample_size: 21,
      window: ANALYSIS_WINDOW,
      strength: EVIDENCE_STRENGTHS.STRONG,
      strength_reason:
        'Chênh lệch lớn và lặp lại ở cả 8 tuần trong 60 ngày (21 bài), không phải hiện tượng của một bài may mắn.',
      drilldown_href: drilldown(
        'level=post&window_start=2026-01-15&window_end=2026-03-14&hour=11-13',
      ),
    },
    {
      id: 'ev_gio_dang_2',
      label:
        'Ngày 08/03 là ngày có lượt tiếp cận cao nhất cửa sổ: 3.480 lượt, gấp 1,6 lần ngày thường',
      metric: METRIC_KEYS.REACH,
      observed: 3_480,
      baseline: 2_175,
      sample_size: 14,
      window: RECENT_WINDOW,
      strength: EVIDENCE_STRENGTHS.MODERATE,
      strength_reason:
        'Đỉnh này trùng với bài khuyến mãi đăng buổi sáng, nhưng cũng có thể do dịp 8/3 nên chưa tách được hai nguyên nhân.',
      drilldown_href: drilldown(
        'level=post&window_start=2026-03-08&window_end=2026-03-08&metric=reach',
      ),
    },
    {
      id: 'ev_gio_dang_3',
      label:
        'Bài đăng sau 19h chỉ chiếm 11% lượt tương tác dù chiếm 30% số bài đã đăng',
      metric: METRIC_KEYS.ENGAGEMENTS,
      observed: 254,
      baseline: 2_311,
      sample_size: 5,
      window: ANALYSIS_WINDOW,
      strength: EVIDENCE_STRENGTHS.WEAK,
      strength_reason:
        'Chỉ có 5 bài đăng sau 19h trong 60 ngày — mẫu nhỏ, cần thêm dữ liệu mới kết luận được.',
      drilldown_href: drilldown(
        'level=format&window_start=2026-01-15&window_end=2026-03-14&hour=19-22',
      ),
    },
  ],
  origin: 'demo',
  feedback: {
    value: RECOMMENDATION_FEEDBACK.USEFUL,
    note: 'Đúng với thực tế quán: 11h trưa là lúc khách hỏi món nhiều nhất.',
    at: demoAgo({ days: 3, hours: 5 }),
    by: USR_OWNER_HUONG,
  },
  created_at: demoAgo({ days: 6, hours: 2 }),
  expires_at: demoAhead({ days: 12 }),
};

/**
 * Khuyến nghị 3 — MỚI, bằng chứng `insufficient`: thử reel 15 giây.
 * Đây là ví dụ QUAN TRỌNG NHẤT về trung thực dữ liệu: chỉ có 2 bài nên
 * `strength_reason` phải nói thẳng là mẫu quá nhỏ, không được hứa hẹn.
 */
const recReel15s: Recommendation = {
  id: REC_REEL_15S,
  workspace_id: WS_FB,
  campaign_id: CMP_PHO_TRUA,
  status: RECOMMENDATION_STATUSES.NEW,
  title: 'Thử reel ngắn 15 giây cho món mới',
  hypothesis:
    'Reel ngắn có thể giữ chân người xem tốt hơn reel dài, nhưng hiện chưa có đủ bài để kiểm chứng.',
  action: RECOMMENDATION_ACTIONS.CONTENT_BRIEF,
  action_label: 'Tạo content brief thử nghiệm: 3 reel 15 giây trong tháng 4',
  expected_effect:
    'CHƯA ƯỚC LƯỢNG ĐƯỢC. Cần ít nhất 8–10 bài reel ngắn rồi mới so sánh được với reel hiện tại.',
  confidence: EVIDENCE_STRENGTHS.INSUFFICIENT,
  evidence: [
    {
      id: 'ev_reel_1',
      label: 'Mới có 2 bài reel trong 60 ngày, không đủ để so sánh độ dài video',
      metric: METRIC_KEYS.ENGAGEMENT_RATE,
      observed: 5.2,
      baseline: 3.9,
      sample_size: 2,
      window: ANALYSIS_WINDOW,
      strength: EVIDENCE_STRENGTHS.INSUFFICIENT,
      strength_reason:
        'MẪU QUÁ NHỎ: chỉ 2 bài reel trong 60 ngày. Chênh lệch 5,2% so với 3,9% có thể chỉ do may mắn, chưa nói lên điều gì.',
      drilldown_href: drilldown(
        'level=format&window_start=2026-01-15&window_end=2026-03-14&format=reel',
      ),
    },
    {
      id: 'ev_reel_2',
      label: 'Chỉ số lượt xem video chưa đọc được vì thiếu quyền trên Page',
      sample_size: 0,
      window: RECENT_WINDOW,
      strength: EVIDENCE_STRENGTHS.INSUFFICIENT,
      strength_reason:
        'Không có số liệu lượt xem video (kết nối Facebook thiếu quyền xem chỉ số này), nên chưa đánh giá được reel nào giữ chân người xem tốt hơn.',
      drilldown_href: drilldown(
        'level=post&window_start=2026-03-01&window_end=2026-03-14&metric=video_views',
      ),
    },
  ],
  origin: 'demo',
  created_at: demoAgo({ hours: 9 }),
  expires_at: demoAhead({ days: 25 }),
};

/** 3 khuyến nghị chính: `applied`, `acknowledged`, `new`. */
export const demoRecommendations: Recommendation[] = [
  recPhuHuynhSang,
  recGioDang,
  recReel15s,
];

/**
 * Khuyến nghị ĐÃ BỎ QUA — tách riêng để bộ fixture chính vẫn đúng 3 khuyến nghị,
 * nhưng UI vẫn có dữ liệu demo cho trạng thái `dismissed` + phản hồi `not_useful`.
 */
export const demoDismissedRecommendation: Recommendation = {
  id: REC_DISMISSED,
  workspace_id: WS_FB,
  campaign_id: CMP_PHO_TRUA,
  status: RECOMMENDATION_STATUSES.DISMISSED,
  title: 'Giảm giá 20% cho khung 20h–22h để lấp giờ vắng khách',
  hypothesis:
    'Khung 20h–22h ít khách, giảm giá có thể kéo khách đến muộn và tăng doanh thu buổi tối.',
  action: RECOMMENDATION_ACTIONS.STRATEGY_REVISION,
  action_label: 'Tạo bản nháp điều chỉnh brief: thêm ưu đãi khung 20h–22h',
  expected_effect:
    'Dự kiến tăng 8–12 lượt khách mỗi tối, nhưng biên lợi nhuận mỗi bát giảm khoảng 9.000đ.',
  confidence: EVIDENCE_STRENGTHS.WEAK,
  evidence: [
    {
      id: 'ev_giam_gia_1',
      label: 'Bài đăng sau 20h có lượt tương tác thấp nhất trong ngày',
      metric: METRIC_KEYS.ENGAGEMENTS,
      observed: 41,
      baseline: 187,
      sample_size: 4,
      window: ANALYSIS_WINDOW,
      strength: EVIDENCE_STRENGTHS.WEAK,
      strength_reason:
        'Chỉ 4 bài đăng sau 20h và quán chưa có số liệu khách đến muộn, nên chưa rõ giảm giá có kéo được khách không.',
      drilldown_href: drilldown(
        'level=post&window_start=2026-01-15&window_end=2026-03-14&hour=20-22',
      ),
    },
    {
      id: 'ev_giam_gia_2',
      label: 'Giá vốn một bát phở bò tái nạm đã tăng 4.000đ từ đầu tháng 3',
      sample_size: 1,
      window: RECENT_WINDOW,
      strength: EVIDENCE_STRENGTHS.INSUFFICIENT,
      strength_reason:
        'Chỉ dựa trên một lần thay đổi giá của nhà cung cấp, chưa đủ để tính lại bài toán lợi nhuận.',
      drilldown_href: `/workspaces/${WS_FB}/brand#products`,
    },
  ],
  origin: 'demo',
  feedback: {
    value: RECOMMENDATION_FEEDBACK.NOT_USEFUL,
    note: 'Giá xương đang tăng, giảm giá buổi tối là lỗ. Không làm.',
    at: demoAgo({ days: 2, hours: 3 }),
    by: USR_OWNER_HUONG,
  },
  created_at: demoAgo({ days: 5, hours: 4 }),
  expires_at: demoAhead({ days: 9 }),
};

/** Bằng chứng rời (không kèm khuyến nghị) — dùng để test UI thẻ bằng chứng. */
export const demoRecommendationEvidence: RecommendationEvidence[] =
  demoRecommendations.flatMap((rec) => rec.evidence);
