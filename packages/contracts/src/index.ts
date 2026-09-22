/**
 * @agentic/contracts — DRAFT
 *
 * Shared request/response contract cho Agentic AI Social Media Marketing Platform.
 *
 * ⚠️ TRẠNG THÁI: DRAFT do M1 (Frontend) đề xuất, CHƯA được M2/M3 thống nhất.
 * Xem `README.md` trong package này để biết danh sách điểm cần review.
 * Khi backend có OpenAPI thật, thay các type ở đây bằng type sinh tự động và
 * giữ nguyên `enums.ts` làm từ vựng chung.
 */

export * from './enums';
export * from './errors';
export * from './common';
export * from './labels';
export * from './auth';
export * from './brand';
export * from './campaign';
export * from './publishing';
export * from './analytics';
export * from './recommendation';
