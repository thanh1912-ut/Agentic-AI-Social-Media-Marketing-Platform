import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiRequest } from './client';

describe('apiRequest session refresh', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = 'agentic_csrf=; Max-Age=0; Path=/';
    delete window.__AGENTIC_RUNTIME_CONFIG__;
  });

  it('sends the CSRF cookie when refreshing a cookie-authenticated session', async () => {
    window.__AGENTIC_RUNTIME_CONFIG__ = { apiBaseUrl: 'http://localhost:8000' };
    document.cookie = 'agentic_csrf=csrf-token; Path=/';
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response('{"error":"expired"}', { status: 401 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiRequest<{ ok: boolean }>('/workspaces/example/data')).resolves.toEqual({
      ok: true,
    });

    const refreshOptions = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(refreshOptions.method).toBe('POST');
    expect(new Headers(refreshOptions.headers).get('X-CSRF-Token')).toBe('csrf-token');
    expect(refreshOptions.credentials).toBe('include');
  });
});
