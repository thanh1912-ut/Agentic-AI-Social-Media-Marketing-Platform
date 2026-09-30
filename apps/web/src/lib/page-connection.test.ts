import { describe, expect, it } from 'vitest';

import { pageConnectionDisabledReason, pageConnectionReady } from './page-connection';

describe('Page connection gate', () => {
  it('only unlocks company actions for an active, identified Page', () => {
    expect(pageConnectionReady({ page_id: '123', page_connection_state: 'active' })).toBe(true);
    expect(pageConnectionReady({ page_id: null, page_connection_state: 'active' })).toBe(false);
    expect(pageConnectionReady({ page_id: '123', page_connection_state: 'needs_reconnect' })).toBe(false);
    expect(pageConnectionReady(undefined)).toBe(false);
  });

  it('explains reconnect separately from first-time Page activation', () => {
    expect(pageConnectionDisabledReason({ page_id: '123', page_connection_state: 'needs_reconnect' })).toContain('kết nối lại');
    expect(pageConnectionDisabledReason({ page_id: null, page_connection_state: 'connection_required' })).toContain('kết nối và xác minh');
    expect(pageConnectionDisabledReason({ page_id: '123', page_connection_state: 'active' })).toBeUndefined();
  });
});
