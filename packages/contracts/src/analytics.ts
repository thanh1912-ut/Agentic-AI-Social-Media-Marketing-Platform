/**
 * DRAFT — Analytics: số liệu hiệu suất, nguồn, cửa sổ đo, độ mới.
 * Endpoints đề xuất: `/api/v1/workspaces/{id}/analytics/*`
 */

import type {
  DateString,
  Freshness,
  Id,
  MeasurementWindow,
  Timestamp,
} from './common';
import type {
  AggregationLevel,
  MetricKey,
  MetricSource,
  MetricState,
} from './enums';

/**
 * Một ô số liệu.
 *
 * QUY TẮC HIỂN THỊ (bắt buộc):
 * - `state = value` + `value = 0`  → hiện `0` (số 0 thật)
 * - `state = no_data`              → hiện `—` kèm "Chưa có dữ liệu"
 * - `state = not_permitted`        → hiện `—` kèm "Không có quyền xem"
 * - `state = not_supported`        → hiện `—` kèm "Kênh không cung cấp"
 * - `state = stale`                → hiện số kèm cảnh báo cũ
 *
 * TUYỆT ĐỐI không render `no_data` / `not_permitted` thành `0`.
 */
export interface MetricCell {
  key: MetricKey;
  /** Nhãn tiếng Việt, vd "Lượt tiếp cận". */
  label: string;
  value: number | null;
  state: MetricState;
  /** Đơn vị: `count`, `percent`, `currency`... */
  unit: 'count' | 'percent' | 'currency' | 'seconds';
  /** Nguồn của riêng ô này — có thể khác nhau giữa các ô. */
  source: MetricSource;
  /** So với kỳ trước. `null` khi không so sánh được. */
  delta?: {
    absolute: number;
    percent: number;
    direction: 'up' | 'down' | 'flat';
    /** Kỳ so sánh. */
    compared_to: MeasurementWindow;
  } | null;
  /** Vì sao ô này không có số — hiển thị khi hover. */
  state_reason?: string;
}

/** Một dòng trong bảng hiệu suất. */
export interface PerformanceRow {
  /** Khoá của đối tượng được tổng hợp (post id, campaign id, pillar, format). */
  id: Id;
  /** Tên hiển thị: tiêu đề bài, tên campaign, tên pillar... */
  label: string;
  /**
   * Trạng thái của dòng. Dòng có `state != value` vẫn phải hiện trong bảng
   * nhưng ghi rõ lý do, không được ẩn im lặng.
   */
  state: MetricState;
  state_reason?: string;
  metrics: MetricCell[];
  /** Với dòng cấp post: link tới bài và bản ghi xuất bản. */
  post_id?: Id;
  publication_id?: Id;
  permalink?: string;
  published_at?: Timestamp;
}

/** Bộ lọc bảng hiệu suất. */
export interface AnalyticsQuery {
  level: AggregationLevel;
  /** Cửa sổ đo. */
  window_start: DateString;
  window_end: DateString;
  campaign_id?: Id;
  pillar?: string;
  format?: string;
  /** Lọc theo nguồn số liệu. */
  source?: MetricSource;
}

/**
 * Metadata của một lần xem số liệu. UI BẮT BUỘC hiển thị: nguồn, cửa sổ đo,
 * lần đồng bộ gần nhất.
 */
export interface AnalyticsMeta {
  /** Nguồn tổng hợp: `api` nếu mọi số đến từ API, `manual` nếu có phần nhập tay,
   * `mixed` nếu cả hai. */
  source: MetricSource | 'mixed';
  /** Nhãn tiếng Việt hiển thị thẳng, vd "Số liệu đồng bộ từ Facebook". */
  source_label: string;
  window: MeasurementWindow;
  /** Nhãn cửa sổ đo, vd "01/03 – 31/03/2026". */
  window_label: string;
  freshness: Freshness;
  /** Có bao nhiêu ô bị thiếu quyền / thiếu dữ liệu — UI cảnh báo tổng thể. */
  missing_count: number;
  not_permitted_count: number;
  /** Dữ liệu demo hay thật. */
  origin: 'live' | 'demo';
}

export interface AnalyticsResponse {
  meta: AnalyticsMeta;
  rows: PerformanceRow[];
  /** Tổng hợp toàn bộ cửa sổ. */
  totals: MetricCell[];
  /** Chuỗi thời gian cho biểu đồ ECharts. */
  timeseries?: Array<{
    date: DateString;
    values: Array<{ key: MetricKey; value: number | null; state: MetricState }>;
  }>;
}

// ---------------------------------------------------------------------------
// Nhập số liệu thủ công
// ---------------------------------------------------------------------------

/**
 * Xem trước khi nhập tệp số liệu. Bước này BẮT BUỘC trước khi ghi vào hệ thống —
 * người dùng phải thấy dữ liệu sẽ vào trước khi xác nhận.
 */
export interface MetricImportPreview {
  job_id?: Id;
  /** Tệp đã tải lên. */
  filename: string;
  /** Cột nhận diện được trong tệp. */
  columns: Array<{
    name: string;
    /** Ánh xạ sang chỉ số chuẩn, `null` nếu không nhận ra. */
    mapped_to: MetricKey | null;
    sample_values: string[];
  }>;
  /** Số dòng đọc được. */
  row_count: number;
  /** Dòng hợp lệ / lỗi. */
  valid_count: number;
  invalid_count: number;
  /** Các vấn đề phát hiện được — người dùng phải xem trước khi xác nhận. */
  warnings: Array<{
    code: string;
    message: string;
    row?: number;
  }>;
  /** Cửa sổ đo mà tệp bao phủ. */
  window?: MeasurementWindow;
  /** Dòng mẫu để hiển thị bảng preview. */
  sample_rows: Array<Record<string, string | number | null>>;
}

export interface MetricImportCommitRequest {
  /** Ánh xạ người dùng đã chỉnh. */
  mapping: Record<string, MetricKey>;
  /** Xác nhận đã xem cảnh báo. */
  acknowledge_warnings: boolean;
  /** Ghi đè số liệu đã có trong cùng cửa sổ. */
  overwrite_existing: boolean;
}

/**
 * Khi tệp chứa số liệu đã tồn tại, backend yêu cầu xác nhận ghi đè.
 * UI không được tự động ghi đè.
 */
export interface MetricImportConflict {
  code: 'overwrite_required';
  message: string;
  existing_window: MeasurementWindow;
  affected_rows: number;
}
