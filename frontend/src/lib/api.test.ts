import { afterEach, describe, expect, it, vi } from 'vitest';

describe('API CSRF protection', () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
  });

  it('fetches a CSRF token and sends it with mutation requests', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        headerName: 'X-XSRF-TOKEN',
        parameterName: '_csrf',
        token: 'csrf-value'
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        id: 'thread-1',
        title: 'Revenue',
        language: 'en',
        status: 'ACTIVE',
        createdAt: '2026-07-28T00:00:00Z',
        updatedAt: '2026-07-28T00:00:00Z'
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('./api');

    await api.createThread('Revenue', 'en');

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/auth/csrf', expect.objectContaining({
      credentials: 'include'
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/chat/threads', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ 'X-XSRF-TOKEN': 'csrf-value' })
    }));
  });

  it('does not request a CSRF token for safe reads', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      userId: '1', username: 'ada', displayName: 'Ada', email: 'ada@test', roles: ['ADMIN']
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('./api');

    await api.currentUser();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/me', expect.objectContaining({
      credentials: 'include'
    }));
  });

  it('requests a server-side page of chat threads', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      schemaVersion: '1.0',
      threads: [{ id: 'thread-1', title: 'Revenue', language: 'en', status: 'ACTIVE',
        createdAt: '2026-07-29T00:00:00Z', updatedAt: '2026-07-29T00:00:00Z' }],
      page: 1, size: 5, totalElements: 8, totalPages: 2, first: false, last: true
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('./api');

    const response = await api.threadPage(1, 5);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chat/threads?page=1&size=5',
      expect.objectContaining({ credentials: 'include' })
    );
    expect(response.items).toHaveLength(1);
    expect(response.totalElements).toBe(8);
    expect(response.last).toBe(true);
  });

  it('deletes an execution through Java with CSRF protection', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        headerName: 'X-XSRF-TOKEN',
        parameterName: '_csrf',
        token: 'delete-csrf'
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        schemaVersion: '1.0',
        executionId: 'execution-1',
        status: 'COMPLETED'
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('./api');

    await api.deleteExecution('execution-1');

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/executions/execution-1',
      expect.objectContaining({
        method: 'DELETE',
        credentials: 'include',
        headers: expect.objectContaining({ 'X-XSRF-TOKEN': 'delete-csrf' })
      })
    );
  });

  it('maps the server-side entity column page to generic page items', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      schemaVersion: '1.0',
      columns: [{
        id: 'column-1',
        columnName: 'net_amount',
        businessName: 'Net amount',
        dataType: 'DECIMAL',
      }],
      page: 0,
      size: 20,
      totalElements: 1,
      totalPages: 1,
      first: true,
      last: true
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const { api } = await import('./api');

    const response = await api.entityColumns('entity-1', 0, 20);

    expect(response.items).toHaveLength(1);
    expect(response.items[0].columnName).toBe('net_amount');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/entities/entity-1/schema/columns?page=0&size=20',
      expect.objectContaining({ credentials: 'include' })
    );
  });
});
