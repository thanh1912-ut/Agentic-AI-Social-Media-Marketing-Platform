/**
 * DRAFT — Recommendation có bằng chứng, và luồng "Apply".
 * Endpoints đề xuất: `/api/v1/workspaces/{id}/recommendations`
 */

import type { Id, MeasurementWindow, Timestamp } from './common';
import type {
  EvidenceStrength,
  MetricKey,
  RecommendationAction,
  RecommendationFeedback,
  RecommendationStatus,
} from './enums';

/**
 * Một mảnh bằng chứng đứng sau recommendation.
 * UI phải cho người dùng xem được bằng chứng — không đưa khuyến nghị "không nguồn".
 */
export interface RecommendationEvidence {
  id: Id;
  /** Nhãn tiếng Việt, vd "Bài dạng carousel có tỉ lệ tương tác cao hơn 42%". */
  label: string;
  /** Chỉ số liên quan. */
  metric?: MetricKey;
  /** Giá trị quan sát được. */
  observed?: number;
  /** Mức nền để so sánh. */
  baseline?: number;
  /** Số mẫu đứng sau — bằng chứng yếu phải nói rõ. */
  sample_size?: number;
  window?: MeasurementWindow;
  strength: EvidenceStrength;
  /** Vì sao bằng chứng này yếu / mạnh. */
  strength_reason: string;
  /** Đi tới đâu để xem chi tiết trên dashboard. */
  drilldown_href?: string;
}

/**
 * Một khuyến nghị. Cấu trúc bắt buộc: evidence → hypothesis → action.
 */
export interface Recommendation {
  id: Id;
  workspace_id: Id;
  campaign_id?: Id;
  status: RecommendationStatus;
  title: string;
  /** Kết luận từ bằng chứng. */
  hypothesis: string;
  /** Việc cụ thể nên làm. */
  action: RecommendationAction;
  /** Mô tả hành động bằng lời người dùng đọc được. */
  action_label: string;
  /** Đề xuất sẽ thay đổi cái gì nếu được áp dụng. */
  expected_effect: string;
  /** Độ tin cậy tổng hợp. */
  confidence: EvidenceStrength;
  evidence: RecommendationEvidence[];
  /** Dữ liệu này đến từ đâu — demo hay thật. */
  origin: 'live' | 'demo';
  /** Người dùng đã phản hồi chưa. */
  feedback?: {
    value: RecommendationFeedback;
    note?: string;
    at: Timestamp;
    by: Id;
  };
  created_at: Timestamp;
  /** Hết hạn sau bao lâu thì không còn phù hợp. */
  expires_at?: Timestamp;
}

export interface RecommendationFeedbackRequest {
  value: RecommendationFeedback;
  note?: string;
}

/**
 * `POST /recommendations/{id}/apply`
 *
 * QUAN TRỌNG: apply KHÔNG tự ý đổi campaign đang chạy. Nó tạo ra một bản nháp
 * (`BriefRevisionDraft` hoặc `content_brief`) để người dùng xem lại rồi mới quyết định.
 */
export interface ApplyRecommendationRequest {
  /** Áp dụng toàn bộ hay chỉ một phần bằng chứng. */
  evidence_ids?: Id[];
  /** Ghi chú của người dùng khi áp dụng. */
  note?: string;
}

export interface ApplyRecommendationResponse {
  recommendation: Recommendation;
  /** Bản nháp được tạo — UI điều hướng người dùng tới đây để xem lại. */
  created_draft: {
    kind: RecommendationAction;
    id: Id;
    href: string;
    label: string;
  };
  /** Cảnh báo nếu có, vd "Campaign đang chạy sẽ không đổi cho tới khi bạn xác nhận." */
  notice?: string;
}
