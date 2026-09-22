/**
 * DEMO FIXTURE — Số liệu hiệu suất của quán phở (`AnalyticsResponse`).
 *
 * MỤC ĐÍCH: demo ba thứ KHÁC NHAU mà UI tuyệt đối không được render giống nhau:
 * - `state: 'value'` + `value: 0` → hiện số 0 THẬT (bài có 186 cảm xúc nhưng 0 bình luận).
 * - `state: 'no_data'`           → hiện “—” kèm “Chưa có dữ liệu”.
 * - `state: 'not_permitted'`     → hiện “—” kèm “Không có quyền xem”.
 * Ngoài ra có `state: 'stale'`/`not_supported` trong enum nhưng bộ demo này không dùng.
 *
 * Quy mô số liệu là quán nhỏ: Page 4.218 người theo dõi, 6.000–9.000 lượt hiển thị
 * mỗi bài, tương tác vài trăm — KHÔNG phải con số của một thương hiệu lớn.
 *
 * LƯU Ý VỀ PHẠM VI (đọc kỹ trước khi dùng):
 * - `rows` là số liệu theo từng đối tượng (bài viết / chiến dịch / pillar / format),
 *   chỉ gồm những bài hệ thống theo dõi được.
 * - `timeseries` và `totals` là số liệu CẤP PAGE cho cả cửa sổ 01/03–14/03, gồm cả
 *   những bài đăng trước cửa sổ và hoạt động chung của Page — nên KHÔNG cộng lại
 *   bằng tổng của `rows`.
 * - `origin: 'demo'`: đây là dữ liệu demo, UI phải hiện nhãn “Dữ liệu demo”.
 */

import type {
  AnalyticsMeta,
  AnalyticsResponse,
  MetricCell,
  MetricImportPreview,
  PerformanceRow,
} from '../analytics.js';
import type { MeasurementWindow } from '../common.js';
import type { MetricKey, MetricState } from '../enums.js';
import {
  AGGREGATION_LEVELS,
  METRIC_KEYS,
  METRIC_SOURCES,
  METRIC_STATES,
} from '../enums.js';
import {
  CMP_PHO_CHI_NHANH_2,
  CMP_PHO_TRUA,
  DEMO_TIMEZONE,
  POST_FAILED,
  POST_PUBLISHED_API,
  POST_PUBLISHED_MANUAL,
  PUB_P01_PUBLISHED,
  WS_FB,
  demoAgo,
} from './ids.js';

/** Cửa sổ đo của bộ demo: 14 ngày, cắt ngày theo giờ Việt Nam. */
const WINDOW: MeasurementWindow = {
  start: '2026-03-01',
  end: '2026-03-14',
  timezone: DEMO_TIMEZONE,
};

/** Kỳ trước dùng cho `delta` (14 ngày liền trước cửa sổ). */
const PREVIOUS_WINDOW: MeasurementWindow = {
  start: '2026-02-15',
  end: '2026-02-28',
  timezone: DEMO_TIMEZONE,
};

type Delta = NonNullable<MetricCell['delta']>;

/** So sánh với kỳ trước — chỉ dùng cho dòng tổng hợp, không dùng cho từng bài. */
function delta(
  absolute: number,
  percent: number,
  direction: Delta['direction'],
): Delta {
  return { absolute, percent, direction, compared_to: PREVIOUS_WINDOW };
}

/** Ô có số thật. `value: 0` là số 0 THẬT, không phải “không có dữ liệu”. */
function value(
  key: MetricKey,
  label: string,
  v: number,
  options: { unit?: MetricCell['unit']; delta?: Delta | null } = {},
): MetricCell {
  const cell: MetricCell = {
    key,
    label,
    value: v,
    state: METRIC_STATES.VALUE,
    unit: options.unit ?? 'count',
    source: METRIC_SOURCES.API,
    delta: options.delta ?? null,
  };
  return cell;
}

/** Ô CHƯA CÓ DỮ LIỆU — UI hiện “—” kèm lý do, tuyệt đối không hiện số 0. */
function noData(key: MetricKey, label: string, reason: string): MetricCell {
  return {
    key,
    label,
    value: null,
    state: METRIC_STATES.NO_DATA,
    unit: 'count',
    source: METRIC_SOURCES.API,
    delta: null,
    state_reason: reason,
  };
}

/** Ô KHÔNG CÓ QUYỀN XEM — khác hẳn “chưa có dữ liệu”, phải nói rõ vì sao. */
function notPermitted(key: MetricKey, label: string, reason: string): MetricCell {
  return {
    key,
    label,
    value: null,
    state: METRIC_STATES.NOT_PERMITTED,
    unit: 'count',
    source: METRIC_SOURCES.API,
    delta: null,
    state_reason: reason,
  };
}

/** Lý do dùng lại nhiều lần: kết nối thiếu quyền xem chỉ số video. */
const REASON_VIDEO_INSIGHTS =
  'Tài khoản Facebook đang kết nối chưa được cấp quyền xem chỉ số lượt xem video của Page này. Hãy kết nối lại Page và bật quyền xem thông tin chi tiết.';

/** Nhãn tiếng Việt của các chỉ số dùng trong bộ demo. */
const LABELS = {
  impressions: 'Lượt hiển thị',
  reach: 'Lượt tiếp cận',
  engagements: 'Lượt tương tác',
  reactions: 'Cảm xúc',
  comments: 'Bình luận',
  shares: 'Lượt chia sẻ',
  clicks: 'Nhấp vào liên kết',
  video_views: 'Lượt xem video',
  saves: 'Lượt lưu',
  engagement_rate: 'Tỉ lệ tương tác',
} as const;

/**
 * Ô số liệu dùng chung cho các dòng tổng hợp (campaign / pillar / format):
 * 7 chỉ số cơ bản, có `delta` so với kỳ trước.
 */
function aggregateCells(input: {
  impressions: number;
  reach: number;
  reactions: number;
  comments: number;
  shares: number;
  clicks: number;
  engagementRate: number;
  deltas?: Partial<Record<MetricKey, Delta>>;
}): MetricCell[] {
  const d = input.deltas ?? {};
  return [
    value(METRIC_KEYS.IMPRESSIONS, LABELS.impressions, input.impressions, {
      delta: d[METRIC_KEYS.IMPRESSIONS] ?? null,
    }),
    value(METRIC_KEYS.REACH, LABELS.reach, input.reach, {
      delta: d[METRIC_KEYS.REACH] ?? null,
    }),
    value(METRIC_KEYS.REACTIONS, LABELS.reactions, input.reactions, {
      delta: d[METRIC_KEYS.REACTIONS] ?? null,
    }),
    value(METRIC_KEYS.COMMENTS, LABELS.comments, input.comments, {
      delta: d[METRIC_KEYS.COMMENTS] ?? null,
    }),
    value(METRIC_KEYS.SHARES, LABELS.shares, input.shares, {
      delta: d[METRIC_KEYS.SHARES] ?? null,
    }),
    value(METRIC_KEYS.CLICKS, LABELS.clicks, input.clicks, {
      delta: d[METRIC_KEYS.CLICKS] ?? null,
    }),
    value(METRIC_KEYS.ENGAGEMENT_RATE, LABELS.engagement_rate, input.engagementRate, {
      unit: 'percent',
      delta: d[METRIC_KEYS.ENGAGEMENT_RATE] ?? null,
    }),
  ];
}

/** Dòng chưa có số liệu: MỌI ô đều `no_data`, kèm lý do ở cả dòng và ở từng ô. */
function emptyCells(reason: string): MetricCell[] {
  return [
    noData(METRIC_KEYS.IMPRESSIONS, LABELS.impressions, reason),
    noData(METRIC_KEYS.REACH, LABELS.reach, reason),
    noData(METRIC_KEYS.REACTIONS, LABELS.reactions, reason),
    noData(METRIC_KEYS.COMMENTS, LABELS.comments, reason),
    noData(METRIC_KEYS.SHARES, LABELS.shares, reason),
    noData(METRIC_KEYS.CLICKS, LABELS.clicks, reason),
  ];
}

/** Lý do dùng lại cho các dòng chưa đăng bài. */
const REASON_NOT_PUBLISHED = 'Bài chưa được đăng nên chưa có số liệu.';

/**
 * Bảng hiệu suất: 3 dòng cấp BÀI VIẾT, 2 dòng cấp CHIẾN DỊCH, 3 dòng cấp PILLAR
 * và 3 dòng cấp FORMAT — đủ để demo bộ lọc `AnalyticsQuery.level`.
 */
const rows: PerformanceRow[] = [
  {
    // CẤP BÀI VIẾT có số liệu, và có một ô số 0 THẬT (0 bình luận).
    id: POST_PUBLISHED_API,
    label:
      'Reel “11h trưa nay ăn gì?” – combo trưa văn phòng 55.000đ',
    state: METRIC_STATES.VALUE,
    post_id: POST_PUBLISHED_API,
    publication_id: PUB_P01_PUBLISHED,
    permalink: 'https://www.facebook.com/phobaccohuong/posts/122145678901234567',
    published_at: demoAgo({ days: 9, hours: 4 }),
    metrics: [
      value(METRIC_KEYS.IMPRESSIONS, LABELS.impressions, 6_240),
      value(METRIC_KEYS.REACH, LABELS.reach, 4_180),
      value(METRIC_KEYS.REACTIONS, LABELS.reactions, 186),
      // SỐ 0 THẬT: bài có 186 cảm xúc nhưng không ai bình luận.
      value(METRIC_KEYS.COMMENTS, LABELS.comments, 0),
      value(METRIC_KEYS.SHARES, LABELS.shares, 31),
      value(METRIC_KEYS.CLICKS, LABELS.clicks, 118),
      notPermitted(
        METRIC_KEYS.VIDEO_VIEWS,
        LABELS.video_views,
        REASON_VIDEO_INSIGHTS,
      ),
      noData(
        METRIC_KEYS.SAVES,
        LABELS.saves,
        'Facebook không trả về chỉ số lượt lưu cho bài này.',
      ),
      value(METRIC_KEYS.ENGAGEMENT_RATE, LABELS.engagement_rate, 5.2, {
        unit: 'percent',
      }),
    ],
  },
  {
    // CẤP BÀI VIẾT có số liệu: bài khuyến mãi 8/3 (người dùng tự đăng, số liệu
    // vẫn đồng bộ được từ Page vì bài nằm trên Facebook).
    id: POST_PUBLISHED_MANUAL,
    label: 'Ảnh “Quán mời các chị em 8/3” – tặng trà đá và quẩy',
    state: METRIC_STATES.VALUE,
    post_id: POST_PUBLISHED_MANUAL,
    permalink: 'https://www.facebook.com/phobaccohuong/posts/122145678901298765',
    published_at: demoAgo({ days: 8, hours: 1 }),
    metrics: [
      value(METRIC_KEYS.IMPRESSIONS, LABELS.impressions, 9_480),
      value(METRIC_KEYS.REACH, LABELS.reach, 6_320),
      value(METRIC_KEYS.REACTIONS, LABELS.reactions, 214),
      value(METRIC_KEYS.COMMENTS, LABELS.comments, 12),
      value(METRIC_KEYS.SHARES, LABELS.shares, 19),
      value(METRIC_KEYS.CLICKS, LABELS.clicks, 64),
      notPermitted(
        METRIC_KEYS.VIDEO_VIEWS,
        LABELS.video_views,
        REASON_VIDEO_INSIGHTS,
      ),
      noData(
        METRIC_KEYS.SAVES,
        LABELS.saves,
        'Facebook không trả về chỉ số lượt lưu cho bài này.',
      ),
      value(METRIC_KEYS.ENGAGEMENT_RATE, LABELS.engagement_rate, 3.9, {
        unit: 'percent',
      }),
    ],
  },
  {
    // CẤP BÀI VIẾT chưa có số liệu: lần gửi trước không rõ kết quả nên không thể
    // biết bài có lên Facebook hay không → KHÔNG được hiện 0.
    id: POST_FAILED,
    label: 'Ảnh “Cảm ơn khách quen – đủ 10 bát tặng 1 bát”',
    state: METRIC_STATES.NO_DATA,
    state_reason:
      'Chưa xác định được bài đã lên Facebook hay chưa (lần gửi trước không rõ kết quả), nên chưa có số liệu.',
    post_id: POST_FAILED,
    metrics: emptyCells(
      'Chưa xác định được bài đã lên Facebook hay chưa nên chưa có số liệu.',
    ),
  },
  {
    // CẤP CHIẾN DỊCH có số liệu: tổng của các bài theo dõi được trong cửa sổ.
    id: CMP_PHO_TRUA,
    label: 'Combo trưa văn phòng – Tháng 3',
    state: METRIC_STATES.VALUE,
    metrics: [
      value(METRIC_KEYS.IMPRESSIONS, LABELS.impressions, 15_720, {
        delta: delta(1_240, 8.6, 'up'),
      }),
      value(METRIC_KEYS.REACH, LABELS.reach, 10_500, {
        delta: delta(380, 3.8, 'up'),
      }),
      value(METRIC_KEYS.REACTIONS, LABELS.reactions, 400, {
        delta: delta(24, 6.4, 'up'),
      }),
      value(METRIC_KEYS.COMMENTS, LABELS.comments, 12, {
        delta: delta(-3, -20, 'down'),
      }),
      value(METRIC_KEYS.SHARES, LABELS.shares, 50, {
        delta: delta(6, 13.6, 'up'),
      }),
      value(METRIC_KEYS.CLICKS, LABELS.clicks, 182, {
        delta: delta(-14, -7.1, 'down'),
      }),
      notPermitted(
        METRIC_KEYS.VIDEO_VIEWS,
        LABELS.video_views,
        REASON_VIDEO_INSIGHTS,
      ),
      noData(
        METRIC_KEYS.SAVES,
        LABELS.saves,
        'Chỉ số lượt lưu chưa được Facebook trả về cho các bài trong cửa sổ này.',
      ),
      value(METRIC_KEYS.ENGAGEMENT_RATE, LABELS.engagement_rate, 4.4, {
        unit: 'percent',
        delta: delta(0.2, 4.8, 'up'),
      }),
    ],
  },
  {
    // CẤP CHIẾN DỊCH chưa chạy: campaign còn là bản nháp → cả dòng `no_data`
    // nhưng VẪN phải hiện trong bảng kèm lý do, không được ẩn im lặng.
    id: CMP_PHO_CHI_NHANH_2,
    label: 'Khai trương chi nhánh 2 – Trần Duy Hưng',
    state: METRIC_STATES.NO_DATA,
    state_reason:
      'Chiến dịch còn là bản nháp và chưa có bài nào được đăng trong cửa sổ này.',
    metrics: emptyCells(
      'Chiến dịch còn là bản nháp, chưa có bài nào được đăng trong cửa sổ này.',
    ),
  },
  {
    // CẤP PILLAR: Khuyến mãi — tổng hợp từ bài 8/3.
    id: 'promotion',
    label: 'Khuyến mãi',
    state: METRIC_STATES.VALUE,
    metrics: aggregateCells({
      impressions: 9_480,
      reach: 6_320,
      reactions: 214,
      comments: 12,
      shares: 19,
      clicks: 64,
      engagementRate: 3.9,
      deltas: {
        [METRIC_KEYS.IMPRESSIONS]: delta(1_980, 26.4, 'up'),
        [METRIC_KEYS.REACH]: delta(1_120, 21.5, 'up'),
        [METRIC_KEYS.REACTIONS]: delta(86, 67.2, 'up'),
      },
    }),
  },
  {
    // CẤP PILLAR: Sản phẩm — tổng hợp từ reel combo trưa.
    id: 'product',
    label: 'Sản phẩm',
    state: METRIC_STATES.VALUE,
    metrics: aggregateCells({
      impressions: 6_240,
      reach: 4_180,
      reactions: 186,
      comments: 0,
      shares: 31,
      clicks: 118,
      engagementRate: 5.2,
      deltas: {
        [METRIC_KEYS.IMPRESSIONS]: delta(-420, -6.3, 'down'),
        [METRIC_KEYS.ENGAGEMENT_RATE]: delta(0.6, 13.0, 'up'),
      },
    }),
  },
  {
    // CẤP PILLAR chưa có bài nào được đăng trong cửa sổ → `no_data` có lý do.
    id: 'behind_the_scenes',
    label: 'Hậu trường',
    state: METRIC_STATES.NO_DATA,
    state_reason:
      'Chưa có bài hậu trường nào được đăng trong cửa sổ này (bài nồi nước dùng đang chờ gửi).',
    metrics: emptyCells(
      'Chưa có bài hậu trường nào được đăng trong cửa sổ này.',
    ),
  },
  {
    // CẤP FORMAT: Một ảnh.
    id: 'image',
    label: 'Một ảnh',
    state: METRIC_STATES.VALUE,
    metrics: aggregateCells({
      impressions: 9_480,
      reach: 6_320,
      reactions: 214,
      comments: 12,
      shares: 19,
      clicks: 64,
      engagementRate: 3.9,
      deltas: {
        [METRIC_KEYS.REACH]: delta(640, 11.3, 'up'),
      },
    }),
  },
  {
    // CẤP FORMAT: Reel — tỉ lệ tương tác cao nhất trong cửa sổ.
    id: 'reel',
    label: 'Reel',
    state: METRIC_STATES.VALUE,
    metrics: aggregateCells({
      impressions: 6_240,
      reach: 4_180,
      reactions: 186,
      comments: 0,
      shares: 31,
      clicks: 118,
      engagementRate: 5.2,
      deltas: {
        [METRIC_KEYS.ENGAGEMENT_RATE]: delta(0.9, 20.9, 'up'),
      },
    }),
  },
  {
    // CẤP FORMAT: Nhiều ảnh — bài carousel còn chờ duyệt nên chưa có số liệu.
    id: 'carousel',
    label: 'Nhiều ảnh',
    state: METRIC_STATES.NO_DATA,
    state_reason:
      'Bài nhiều ảnh (phở cuốn) đang chờ duyệt, chưa đăng nên chưa có số liệu.',
    metrics: emptyCells(REASON_NOT_PUBLISHED),
  },
];

/** Điểm dữ liệu cho biểu đồ ECharts; `null` khi ngày đó không có số liệu. */
type TimeseriesPoint = NonNullable<AnalyticsResponse['timeseries']>[number];

const TIMESERIES_KEYS: MetricKey[] = [
  METRIC_KEYS.IMPRESSIONS,
  METRIC_KEYS.REACH,
  METRIC_KEYS.ENGAGEMENTS,
  METRIC_KEYS.REACTIONS,
  METRIC_KEYS.COMMENTS,
  METRIC_KEYS.SHARES,
  METRIC_KEYS.CLICKS,
];

const TIMESERIES_LABELS: Record<string, string> = {
  impressions: LABELS.impressions,
  reach: LABELS.reach,
  engagements: LABELS.engagements,
  reactions: LABELS.reactions,
  comments: LABELS.comments,
  shares: LABELS.shares,
  clicks: LABELS.clicks,
};

/**
 * Một ngày số liệu. `values = null` nghĩa là NGÀY ĐÓ KHÔNG CÓ DỮ LIỆU
 * (mất kết nối Facebook) → biểu đồ phải để trống, không được vẽ số 0.
 */
function point(
  date: string,
  values: Record<string, number> | null,
): TimeseriesPoint {
  return {
    date,
    values: TIMESERIES_KEYS.map((key) => {
      if (!values) {
        return {
          key,
          value: null,
          state: METRIC_STATES.NO_DATA as MetricState,
        };
      }
      return {
        key,
        value: values[key] ?? 0,
        state: METRIC_STATES.VALUE as MetricState,
      };
    }),
  };
}

/**
 * `demoAnalytics` — số liệu 14 ngày (01/03–14/03/2026) của quán phở.
 * Ngày 08/03 là đỉnh (bài khuyến mãi Quốc tế Phụ nữ); ngày 07/03 mất kết nối
 * Facebook nên KHÔNG có số liệu — đúng một khoảng trống trên biểu đồ.
 */
export const demoAnalytics: AnalyticsResponse = {
  meta: {
    // Mọi ô số liệu trong bộ này đều đến từ API Facebook, không có phần nhập tay.
    source: METRIC_SOURCES.API,
    source_label: 'Số liệu đồng bộ từ Facebook Page “Phở Bắc Cô Hương”',
    window: WINDOW,
    window_label: '01/03 – 14/03/2026',
    freshness: {
      last_synced_at: demoAgo({ hours: 2 }),
      age_seconds: 7_200,
      is_stale: false,
      label: 'Đồng bộ 2 giờ trước',
    },
    // Đếm trên toàn bộ ô của `rows` + `totals`: 28 ô “chưa có dữ liệu”,
    // 4 ô “không có quyền xem” (chỉ số lượt xem video).
    missing_count: 28,
    not_permitted_count: 4,
    // BẮT BUỘC: dữ liệu demo phải được dán nhãn, không giả thành dữ liệu thật.
    origin: 'demo',
  },
  rows,
  totals: [
    // Tổng cấp PAGE cho cả cửa sổ (khớp với `timeseries` bên dưới).
    value(METRIC_KEYS.IMPRESSIONS, LABELS.impressions, 44_890, {
      delta: delta(3_120, 7.5, 'up'),
    }),
    value(METRIC_KEYS.REACH, LABELS.reach, 30_450, {
      delta: delta(1_860, 6.5, 'up'),
    }),
    value(METRIC_KEYS.ENGAGEMENTS, LABELS.engagements, 2_311, {
      delta: delta(148, 6.8, 'up'),
    }),
    value(METRIC_KEYS.REACTIONS, LABELS.reactions, 1_828, {
      delta: delta(121, 7.1, 'up'),
    }),
    value(METRIC_KEYS.COMMENTS, LABELS.comments, 222, {
      delta: delta(-9, -3.9, 'down'),
    }),
    value(METRIC_KEYS.SHARES, LABELS.shares, 261, {
      delta: delta(36, 16.0, 'up'),
    }),
    value(METRIC_KEYS.CLICKS, LABELS.clicks, 861, {
      delta: delta(-42, -4.7, 'down'),
    }),
    notPermitted(
      METRIC_KEYS.VIDEO_VIEWS,
      LABELS.video_views,
      REASON_VIDEO_INSIGHTS,
    ),
    noData(
      METRIC_KEYS.SAVES,
      LABELS.saves,
      'Facebook không trả về chỉ số lượt lưu cho cửa sổ này.',
    ),
    value(METRIC_KEYS.ENGAGEMENT_RATE, LABELS.engagement_rate, 7.6, {
      unit: 'percent',
      delta: delta(0.1, 1.3, 'up'),
    }),
  ],
  timeseries: [
    point('2026-03-01', {
      impressions: 2_140,
      reach: 1_480,
      engagements: 96,
      reactions: 78,
      comments: 9,
      shares: 9,
      clicks: 41,
    }),
    point('2026-03-02', {
      impressions: 3_260,
      reach: 2_210,
      engagements: 168,
      reactions: 131,
      comments: 16,
      shares: 21,
      clicks: 63,
    }),
    point('2026-03-03', {
      impressions: 2_980,
      reach: 2_040,
      engagements: 142,
      reactions: 112,
      comments: 12,
      shares: 18,
      clicks: 55,
    }),
    point('2026-03-04', {
      impressions: 3_120,
      reach: 2_160,
      engagements: 155,
      reactions: 124,
      comments: 14,
      shares: 17,
      clicks: 58,
    }),
    point('2026-03-05', {
      impressions: 3_410,
      reach: 2_330,
      engagements: 176,
      reactions: 139,
      comments: 17,
      shares: 20,
      clicks: 66,
    }),
    point('2026-03-06', {
      impressions: 3_870,
      reach: 2_620,
      engagements: 204,
      reactions: 163,
      comments: 19,
      shares: 22,
      clicks: 78,
    }),
    // Mất kết nối Facebook cả ngày 07/03 → KHÔNG có số liệu (không phải số 0).
    point('2026-03-07', null),
    // Đỉnh 08/03: bài khuyến mãi Quốc tế Phụ nữ.
    point('2026-03-08', {
      impressions: 5_240,
      reach: 3_480,
      engagements: 312,
      reactions: 246,
      comments: 38,
      shares: 28,
      clicks: 104,
    }),
    point('2026-03-09', {
      impressions: 3_620,
      reach: 2_440,
      engagements: 187,
      reactions: 148,
      comments: 18,
      shares: 21,
      clicks: 69,
    }),
    point('2026-03-10', {
      impressions: 3_150,
      reach: 2_130,
      engagements: 149,
      reactions: 118,
      comments: 13,
      shares: 18,
      clicks: 56,
    }),
    point('2026-03-11', {
      impressions: 3_020,
      reach: 2_060,
      engagements: 141,
      reactions: 111,
      comments: 12,
      shares: 18,
      clicks: 54,
    }),
    point('2026-03-12', {
      impressions: 3_290,
      reach: 2_230,
      engagements: 163,
      reactions: 128,
      comments: 15,
      shares: 20,
      clicks: 61,
    }),
    point('2026-03-13', {
      impressions: 3_710,
      reach: 2_510,
      engagements: 192,
      reactions: 152,
      comments: 18,
      shares: 22,
      clicks: 72,
    }),
    point('2026-03-14', {
      impressions: 4_080,
      reach: 2_760,
      engagements: 226,
      reactions: 178,
      comments: 21,
      shares: 27,
      clicks: 84,
    }),
  ],
};

/** Nhãn tiếng Việt của chỉ số — UI có thể dùng lại thay vì tự viết. */
export const demoMetricLabels: Record<string, string> = {
  ...TIMESERIES_LABELS,
  video_views: LABELS.video_views,
  saves: LABELS.saves,
  engagement_rate: LABELS.engagement_rate,
};

/** Cấp tổng hợp có mặt trong `demoAnalytics.rows` — dùng để demo bộ lọc. */
export const demoAnalyticsLevels = [
  AGGREGATION_LEVELS.POST,
  AGGREGATION_LEVELS.CAMPAIGN,
  AGGREGATION_LEVELS.PILLAR,
  AGGREGATION_LEVELS.FORMAT,
] as const;

/**
 * Xem trước khi NHẬP SỐ LIỆU TỪ TỆP (`MetricImportPreview`): có 1 dòng lỗi và
 * 1 cột không nhận diện được → bắt buộc người dùng xem cảnh báo trước khi ghi.
 */
export const demoMetricImportPreview: MetricImportPreview = {
  job_id: 'job_metric_import_xem_truoc',
  filename: 'bao-cao-fanpage-thang-3.xlsx',
  columns: [
    {
      name: 'Ngày',
      mapped_to: null,
      sample_values: ['2026-03-01', '2026-03-02', '2026-03-03'],
    },
    {
      name: 'Lượt hiển thị',
      mapped_to: METRIC_KEYS.IMPRESSIONS,
      sample_values: ['2140', '3260', '2980'],
    },
    {
      name: 'Lượt tiếp cận',
      mapped_to: METRIC_KEYS.REACH,
      sample_values: ['1480', '2210', '2040'],
    },
    {
      name: 'Cảm xúc',
      mapped_to: METRIC_KEYS.REACTIONS,
      sample_values: ['78', '131', '112'],
    },
    {
      name: 'Bình luận',
      mapped_to: METRIC_KEYS.COMMENTS,
      sample_values: ['9', '16', '12'],
    },
    {
      name: 'Ghi chú của quán',
      mapped_to: null,
      sample_values: ['ngày mưa', 'đông khách', ''],
    },
  ],
  row_count: 14,
  valid_count: 13,
  invalid_count: 1,
  warnings: [
    {
      code: 'unrecognized_column',
      message:
        'Cột “Ghi chú của quán” không khớp với chỉ số nào nên sẽ bị bỏ qua khi nhập.',
    },
    {
      code: 'missing_value',
      message:
        'Ngày 07/03 để trống lượt tiếp cận. Nếu nhập, ngày này sẽ được ghi là “chưa có dữ liệu”, không phải số 0.',
      row: 8,
    },
  ],
  window: WINDOW,
  sample_rows: [
    {
      Ngày: '2026-03-01',
      'Lượt hiển thị': 2_140,
      'Lượt tiếp cận': 1_480,
      'Cảm xúc': 78,
      'Bình luận': 9,
      'Ghi chú của quán': 'ngày mưa',
    },
    {
      Ngày: '2026-03-02',
      'Lượt hiển thị': 3_260,
      'Lượt tiếp cận': 2_210,
      'Cảm xúc': 131,
      'Bình luận': 16,
      'Ghi chú của quán': 'đông khách',
    },
    {
      Ngày: '2026-03-07',
      'Lượt hiển thị': 0,
      'Lượt tiếp cận': null,
      'Cảm xúc': null,
      'Bình luận': null,
      'Ghi chú của quán': null,
    },
  ],
};

/** Workspace mà bộ số liệu này thuộc về — tiện cho UI mock theo workspace. */
export const demoAnalyticsWorkspaceId = WS_FB;
