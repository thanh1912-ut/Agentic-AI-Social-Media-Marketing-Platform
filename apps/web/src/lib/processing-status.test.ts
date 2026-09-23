import { describe, expect, it } from 'vitest';

import {
  extractionStatusMeta,
  knowledgeStatusMeta,
  presentJobFailure,
  profileStatusMeta,
  retrievalModeMeta,
} from './processing-status';

describe('trạng thái pipeline tài liệu', () => {
  it('không coi đọc xong tài liệu là Brand Profile đã sẵn sàng', () => {
    expect(extractionStatusMeta('extracted').label).toBe('Đã đọc xong nội dung');
    expect(profileStatusMeta('pending').label).toBe('Brand Profile chưa tạo xong');
    expect(profileStatusMeta('ready').label).toBe('Đã tạo/cập nhật Brand Profile');
  });

  it('nêu riêng trạng thái knowledge chưa khả dụng và trạng thái không rõ', () => {
    expect(knowledgeStatusMeta('not_available').label).toBe('Knowledge chưa khả dụng');
    expect(knowledgeStatusMeta(undefined).description).toContain('không thể suy ra');
  });

  it('phân biệt lexical, vector và mode truy xuất chưa khả dụng', () => {
    expect(retrievalModeMeta('lexical').label).toBe('Truy xuất từ khóa (lexical)');
    expect(retrievalModeMeta('semantic_vector').label).toBe('Truy xuất semantic/vector');
    expect(retrievalModeMeta('not_available').label).toBe('Truy xuất chưa khả dụng');
    expect(retrievalModeMeta('semantic_vector').description).toContain('không phải health check');
  });
});

describe('lỗi tạo Brand Profile từ JobErrorOut', () => {
  it.each([
    ['provider_not_configured', 'Nhà cung cấp AI chưa sẵn sàng'],
    ['ai_not_configured', 'Nhà cung cấp AI chưa sẵn sàng'],
    ['provider_model_not_found', 'Mô hình AI không khả dụng'],
    ['provider_timeout', 'Yêu cầu AI đã hết thời gian chờ'],
    ['timeout', 'Yêu cầu AI đã hết thời gian chờ'],
    ['generation_failed', 'Chưa tạo được Brand Profile'],
    ['brand_profile_generation_failed', 'Chưa tạo được Brand Profile'],
  ])('dịch mã lỗi %s thành thông báo provider-neutral', (code, title) => {
    expect(presentJobFailure({ code, message: 'Generic backend failure', retryable: false }).title).toBe(title);
  });

  it('không hiển thị hint cấu hình provider cũ nhắc OpenAI key', () => {
    const presentation = presentJobFailure({
      code: 'ai_not_configured',
      message: 'Chưa cấu hình dịch vụ AI cho worker.',
      hint: 'Quản trị viên cần cấu hình OPENAI_API_KEY ở server rồi chạy lại tài liệu.',
      retryable: false,
    });

    expect(presentation.message).toBe('Chưa cấu hình dịch vụ AI cho worker.');
    expect(presentation.hint).toContain('dịch vụ AI');
    expect(`${presentation.message} ${presentation.hint}`).not.toMatch(/openai/i);
  });

  it('giữ thông báo và retry hint chung do API trả về', () => {
    const presentation = presentJobFailure({
      code: 'provider_timeout',
      message: 'Model provider request timed out.',
      hint: 'Thử lại sau khi dịch vụ ổn định.',
      retryable: true,
    });

    expect(presentation.message).toBe('Model provider request timed out.');
    expect(presentation.hint).toBe('Thử lại sau khi dịch vụ ổn định.');
  });
});
