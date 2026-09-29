import type { ApiDocument, ApiJobError } from '@/lib/api/types';

export type ProcessingTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

export interface ProcessingStatusMeta {
  label: string;
  tone: ProcessingTone;
  description: string;
}

const UNKNOWN_STATUS: ProcessingStatusMeta = {
  label: 'Chưa rõ',
  tone: 'neutral',
  description: 'Máy chủ chưa gửi trạng thái này; không thể suy ra từ trạng thái tài liệu.',
};

const EXTRACTION_STATUS: Record<string, ProcessingStatusMeta> = {
  pending: {
    label: 'Đang chờ đọc',
    tone: 'neutral',
    description: 'Nội dung tài liệu chưa được xác nhận là đã đọc xong.',
  },
  extracted: {
    label: 'Đã đọc xong nội dung',
    tone: 'success',
    description: 'Máy chủ đã trích xuất và chuẩn hóa nội dung tài liệu.',
  },
  partial: {
    label: 'Đã đọc được một phần',
    tone: 'warning',
    description: 'Có nội dung đã lưu nhưng máy chủ ghi nhận trang hoặc phần dữ liệu bị thiếu; xem cảnh báo trước khi dùng.',
  },
  metadata_only: {
    label: 'Chỉ lưu metadata',
    tone: 'warning',
    description: 'Chưa trích xuất được văn bản để dùng làm nguồn cho AI.',
  },
  failed: {
    label: 'Đọc tài liệu thất bại',
    tone: 'danger',
    description: 'Máy chủ không đọc được nội dung tài liệu.',
  },
};

const KNOWLEDGE_STATUS: Record<string, ProcessingStatusMeta> = {
  pending: {
    label: 'Đang chuẩn bị knowledge',
    tone: 'neutral',
    description: 'Chưa có xác nhận rằng nội dung đã sẵn sàng để truy xuất.',
  },
  ready: {
    label: 'Sẵn sàng truy xuất',
    tone: 'success',
    description: 'Máy chủ đánh dấu nguồn tri thức đã sẵn sàng cho bước truy xuất.',
  },
  not_available: {
    label: 'Knowledge chưa khả dụng',
    tone: 'warning',
    description: 'Máy chủ chưa đánh dấu nguồn tri thức này là khả dụng; không đồng nghĩa nội dung chưa được đọc.',
  },
  failed: {
    label: 'Chuẩn bị knowledge thất bại',
    tone: 'danger',
    description: 'Nguồn chưa sẵn sàng cho truy xuất; xem lỗi của tác vụ để biết bước tiếp theo.',
  },
};

const RETRIEVAL_MODE: Record<string, ProcessingStatusMeta> = {
  lexical: {
    label: 'Truy xuất từ khóa (lexical)',
    tone: 'info',
    description: 'Đang dùng tìm kiếm theo từ khóa; mode này không dùng embedding/vector semantic.',
  },
  semantic_vector: {
    label: 'Truy xuất semantic/vector',
    tone: 'success',
    description: 'API báo mode vector đang bật; đây không phải health check riêng của provider embedding.',
  },
  not_available: {
    label: 'Truy xuất chưa khả dụng',
    tone: 'warning',
    description: 'API chưa báo mode truy xuất khả dụng; không suy đoán nguyên nhân từ trạng thái này.',
  },
};

function lookupStatus(
  table: Record<string, ProcessingStatusMeta>,
  status: string | null | undefined,
): ProcessingStatusMeta {
  return status ? (table[status] ?? { ...UNKNOWN_STATUS, label: status }) : UNKNOWN_STATUS;
}

export function extractionStatusMeta(
  status: ApiDocument['extraction_status'] | null | undefined,
): ProcessingStatusMeta {
  return lookupStatus(EXTRACTION_STATUS, status);
}

export function knowledgeStatusMeta(
  status: ApiDocument['knowledge_status'] | null | undefined,
): ProcessingStatusMeta {
  return lookupStatus(KNOWLEDGE_STATUS, status);
}

export function retrievalModeMeta(
  mode: ApiDocument['retrieval_mode'] | null | undefined,
): ProcessingStatusMeta {
  return lookupStatus(RETRIEVAL_MODE, mode);
}

export interface JobFailurePresentation {
  title: string;
  description: string | null;
  message: string;
  hint: string | null;
}

const STALE_PROVIDER_HINT = /openai|openai_api_key/i;

export function presentJobFailure(error: ApiJobError | null | undefined): JobFailurePresentation {
  const code = error?.code.toLowerCase() ?? '';
  const rawMessage = error?.message.trim() ?? '';
  const rawHint = error?.hint?.trim() ?? '';
  const message = STALE_PROVIDER_HINT.test(rawMessage) ? '' : rawMessage;
  const hint = STALE_PROVIDER_HINT.test(rawHint) ? '' : rawHint;

  if (['provider_not_configured', 'ai_not_configured'].includes(code)) {
    return {
      title: 'Dịch vụ AI chưa sẵn sàng',
      description: 'Lỗi này không làm mất phần tài liệu đã đọc và lưu thành công.',
      message: message || 'Máy chủ chưa sẵn sàng với dịch vụ AI cần cho tác vụ này.',
      hint: hint || 'Kiểm tra cấu hình dịch vụ AI trên worker rồi thử lại tác vụ AI.',
    };
  }

  if (code === 'provider_model_not_found') {
    return {
      title: 'Mô hình AI không khả dụng',
      description: 'Máy chủ không thể dùng model đã cấu hình cho tác vụ AI này.',
      message: message || 'Provider không nhận diện model đang được cấu hình.',
      hint: hint || 'Quản trị viên cần kiểm tra tên model và cấu hình dịch vụ AI trên server.',
    };
  }

  if (['timeout', 'provider_timeout', 'generation_timeout', 'request_timeout', 'upstream_timeout'].includes(code)) {
    return {
      title: 'Yêu cầu AI đã hết thời gian chờ',
      description: 'Tác vụ AI chưa hoàn tất; dữ liệu tài liệu đã lưu vẫn được giữ nguyên.',
      message: message || 'Máy chủ không nhận được kết quả AI trong thời gian cho phép.',
      hint: hint || 'Chỉ thử lại nếu máy chủ cho biết tác vụ có thể thử lại.',
    };
  }

  if (['generation_failed', 'brand_profile_generation_failed'].includes(code)) {
    return {
      title: 'Tác vụ AI thất bại',
      description: 'Trạng thái đọc và lưu kiến thức của tài liệu được theo dõi riêng.',
      message: message || 'Máy chủ không hoàn tất tác vụ AI.',
      hint: hint || null,
    };
  }

  return {
    title: 'Tác vụ thất bại',
    description: null,
    message: message || 'Máy chủ báo tác vụ thất bại nhưng không gửi kèm mô tả lỗi.',
    hint: hint || null,
  };
}
