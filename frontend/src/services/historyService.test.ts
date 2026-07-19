import { describe, expect, it, vi } from 'vitest';

vi.mock('./authService', () => ({
  authenticatedFetch: vi.fn(),
}));

import { authenticatedFetch } from './authService';
import { getHistoryDownloadUrl, getTranscriptHistory, HistoryError } from './historyService';

describe('historyService error classification', () => {
  it('returns items on success', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [{ history_id: 'h1', session_id: 's1', created_at: '2026-01-01T00:00:00Z', segment_count: 3 }] }), { status: 200 })
    );

    const items = await getTranscriptHistory();

    expect(items).toHaveLength(1);
    expect(items[0].history_id).toBe('h1');
  });

  it('raises an "auth" HistoryError on 401', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(new Response('{}', { status: 401 }));

    await expect(getTranscriptHistory()).rejects.toMatchObject({ kind: 'auth' } satisfies Partial<HistoryError>);
  });

  it('raises an "auth" HistoryError on 403', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(new Response('{}', { status: 403 }));

    await expect(getTranscriptHistory()).rejects.toMatchObject({ kind: 'auth' } satisfies Partial<HistoryError>);
  });

  it('raises a "network" HistoryError on other non-2xx responses', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(new Response('{}', { status: 500 }));

    await expect(getTranscriptHistory()).rejects.toMatchObject({ kind: 'network' } satisfies Partial<HistoryError>);
  });

  it('raises a "network" HistoryError when the fetch itself throws', async () => {
    vi.mocked(authenticatedFetch).mockRejectedValueOnce(new Error('offline'));

    await expect(getTranscriptHistory()).rejects.toMatchObject({ kind: 'network' } satisfies Partial<HistoryError>);
  });

  it('classifies download-url errors the same way', async () => {
    vi.mocked(authenticatedFetch).mockResolvedValueOnce(new Response('{}', { status: 401 }));

    await expect(getHistoryDownloadUrl('h1')).rejects.toMatchObject({ kind: 'auth' } satisfies Partial<HistoryError>);
  });
});
