import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { CampaignResearchOrigin } from './CampaignResearchOrigin';
afterEach(cleanup);
it('shows pinned source counts and an internal report link without exposing excerpt text', () => {
  render(<CampaignResearchOrigin workspaceId="w-a" brief={{ market_research_context: {
    report_id: '312fe0fd-6a2a-4d17-b6a2-2b4e6ce4dde2', comment_analysis_refs: [{ batch_id: 'batch-a' }], evidence: [], web_snapshot_ids: [],
  } }} />);
  expect(screen.getByText(/1 lô bình luận đã kiểm tra/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Xem báo cáo đã chọn' })).toHaveAttribute('href', '/w/w-a/research?tab=reports#research-report-312fe0fd-6a2a-4d17-b6a2-2b4e6ce4dde2');
});
it('shows erasure and never displays the old source link or counts', () => {
  render(<CampaignResearchOrigin workspaceId="w-a" brief={{ market_research_context_invalidated: { reason: 'comment_data_erased' } }} />);
  expect(screen.getByText('Nguồn hướng viết không còn khả dụng')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Xem báo cáo đã chọn' })).not.toBeInTheDocument();
});
