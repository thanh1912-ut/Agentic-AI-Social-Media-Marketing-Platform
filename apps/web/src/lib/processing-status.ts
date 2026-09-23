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
    description: 'Máy chủ đã trích xuất nội dung; điều này chưa có nghĩa Brand Profile đã được tạo.',
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

const PROFILE_STATUS: Record<string, ProcessingStatusMeta> = {
  pending: {
    label: 'Brand Profile chưa tạo xong',
    tone: 'neutral',
    description: 'Đọc xong tài liệu không đồng nghĩa Brand Profile đã được tạo; hãy theo dõi tác vụ.',
  },
  ready: {
    label: 'Đã tạo/cập nhật Brand Profile',
    tone: 'success',
    description: 'Hồ sơ đã được tạo/cập nhật, nhưng vẫn cần người dùng xem nguồn và xác nhận.',
  },
  not_available: {
    label: 'Không dùng được để tạo Brand Profile',
    tone: 'warning',
    description: 'Máy chủ báo tài liệu này không thể tạo hồ sơ (ví dụ ảnh chưa có OCR).',
  },
  failed: {
    label: 'Tạo Brand Profile thất bại',
    tone: 'danger',
    description: 'Tài liệu có thể đã đọc xong nhưng bước tạo hồ sơ chưa thành công.',
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

export function profileStatusMeta(
  status: ApiDocument['profile_status'] | null | undefined,
): ProcessingStatusMeta {
  return lookupStatus(PROFILE_STATUS, status);
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
      title: 'Nhà cung cấp AI chưa sẵn sàng',
      description: 'Tài liệu có thể đã đọc xong, nhưng Brand Profile chưa được tạo.',
      message: message || 'Máy chủ chưa sẵn sàng với dịch vụ AI cần cho tác vụ này.',
      hint: hint || 'Quản trị viên cần kiểm tra cấu hình dịch vụ AI trên worker trước khi chạy lại tác vụ.',
    };
  }

  if (code === 'provider_model_not_found') {
    return {
      title: 'Mô hình AI không khả dụng',
      description: 'Máy chủ không thể dùng model đã cấu hình để tạo Brand Profile.',
      message: message || 'Provider không nhận diện model đang được cấu hình.',
      hint: hint || 'Quản trị viên cần kiểm tra tên model và cấu hình dịch vụ AI trên server.',
    };
  }

  if (['timeout', 'provider_timeout', 'generation_timeout', 'request_timeout', 'upstream_timeout'].includes(code)) {
    return {
      title: 'Yêu cầu AI đã hết thời gian chờ',
      description: 'Brand Profile chưa được xác nhận là đã tạo xong.',
      message: message || 'Máy chủ không nhận được kết quả AI trong thời gian cho phép.',
      hint: hint || 'Chỉ thử lại nếu máy chủ cho biết tác vụ có thể thử lại.',
    };
  }

  if (['generation_failed', 'brand_profile_generation_failed'].includes(code)) {
    return {
      title: 'Chưa tạo được Brand Profile',
      description: 'Trạng thái đọc tài liệu được theo dõi riêng; lỗi này thuộc bước tạo hồ sơ.',
      message: message || 'Máy chủ không hoàn tất bước tạo hồ sơ thương hiệu.',
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
