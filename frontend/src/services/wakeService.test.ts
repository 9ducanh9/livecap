import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { wakeBackendIfConfigured } from './wakeService';

describe('wakeBackendIfConfigured', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('skips wake and health requests when no wake endpoint is configured', async () => {
    await wakeBackendIfConfigured({ wakeUrl: '   ' });

    expect(fetch).not.toHaveBeenCalled();
  });

  it('calls wake before polling backend health', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));

    await wakeBackendIfConfigured({
      wakeUrl: 'https://example.test/api/wake',
      apiBaseUrl: 'https://example.test',
      timeoutMs: 1_000,
      pollIntervalMs: 1,
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe('https://example.test/api/wake');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      headers: {
        'x-amz-content-sha256':
          'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
      },
    });
    expect(fetchMock.mock.calls[1][0]).toBe(
      'https://example.test/api/health'
    );
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'GET' });
  });

  it('fails without polling health when the wake endpoint rejects the request', async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(new Response('{}', { status: 429 }));

    await expect(
      wakeBackendIfConfigured({
        wakeUrl: 'https://example.test/api/wake',
        apiBaseUrl: 'https://example.test',
      })
    ).rejects.toThrow('Wake endpoint returned HTTP 429');
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('fails when the backend does not become healthy before timeout', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'));

    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockRejectedValue(new Error('connection refused'));

    const wakeAttempt = wakeBackendIfConfigured({
      wakeUrl: 'https://example.test/api/wake',
      apiBaseUrl: 'https://example.test',
      timeoutMs: 10,
      pollIntervalMs: 5,
    });
    const rejection = expect(wakeAttempt).rejects.toThrow(
      'Backend did not become healthy before timeout: connection refused'
    );

    await vi.advanceTimersByTimeAsync(11);
    await rejection;
  });
});
