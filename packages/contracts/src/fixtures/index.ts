/**
 * DEMO FIXTURE — Điểm vào duy nhất cho toàn bộ dữ liệu demo của frontend.
 *
 * Cách dùng trong app:
 * ```ts
 * import { demoPosts, demoAnalytics, DEMO_NOW } from '@agentic/contracts/fixtures';
 * ```
 *
 * NGUYÊN TẮC:
 * - Toàn bộ dữ liệu ở đây là DỮ LIỆU DEMO. Nơi nào type cho phép `origin` thì
 *   luôn là `'demo'`; UI phải hiện nhãn “Dữ liệu demo” (xem `DEMO_DATA_NOTICE`
 *   trong `labels.ts`) — không được để người dùng tưởng là số liệu thật.
 * - Dữ liệu là TĨNH và XÁC ĐỊNH: mọi mốc thời gian suy ra từ `DEMO_NOW`
 *   (2026-03-15T09:00:00Z), không dùng `Date.now()` / `Math.random()`.
 * - Mọi giá trị đều khớp với type trong `packages/contracts/src/*.ts`. Fixture
 *   KHÔNG được tự thêm trường mà contract không có.
 */

export * from './ids';
export * from './workspace';
export * from './documents';
export * from './brand';
export * from './jobs';
export * from './campaigns';
export * from './approvals';
export * from './publishing';
export * from './analytics';
export * from './recommendations';
