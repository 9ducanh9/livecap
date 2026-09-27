import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  beginBackendWakeAfterSignIn,
  waitForBackendWakeAfterSignIn,
  wakeBackendIfConfigured,
} from './wakeService';

describe('wakeBackendIfConfigured', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
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

  it('reuses the sign-in wake instead of issuing another wake for the workspace action', async () => {
    vi.stubEnv('VITE_WAKE_BACKEND_URL', 'https://example.test/api/wake');
    vi.stubEnv('VITE_API_BASE_URL', 'https://example.test');
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));

    const signInWake = beginBackendWakeAfterSignIn();
    const workspaceWait = waitForBackendWakeAfterSignIn();
    await Promise.all([signInWake, workspaceWait]);

    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' });
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'GET' });
    expect(fetchMock.mock.calls[2][1]).toMatchObject({ method: 'GET' });
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1);
  });

  it('issues a recovery wake if the backend scaled down after the sign-in wake', async () => {
    vi.stubEnv('VITE_WAKE_BACKEND_URL', 'https://example.test/api/wake');
    vi.stubEnv('VITE_API_BASE_URL', 'https://example.test');
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 503 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));

    await beginBackendWakeAfterSignIn();
    await waitForBackendWakeAfterSignIn();

    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2);
    expect(fetchMock.mock.calls[fetchMock.mock.calls.length - 1]?.[1]).toMatchObject({ method: 'GET' });
  });

  it('starts a fresh wake for a later successful sign-in in the same tab', async () => {
    vi.stubEnv('VITE_WAKE_BACKEND_URL', 'https://example.test/api/wake');
    vi.stubEnv('VITE_API_BASE_URL', 'https://example.test');
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }))
      .mockResolvedValueOnce(new Response('{}', { status: 200 }));

    await beginBackendWakeAfterSignIn();
    await beginBackendWakeAfterSignIn();

    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(2);
  });
});
