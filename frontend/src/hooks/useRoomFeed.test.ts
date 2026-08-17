import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useRoomFeed } from './useRoomFeed';

const wake = vi.hoisted(() => vi.fn());

vi.mock('../services/wakeService', () => ({
  wakeBackendIfConfigured: wake,
}));

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readonly url: string;
  readyState = MockWebSocket.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  send = vi.fn();

  constructor(url: string | URL) {
    this.url = String(url);
    MockWebSocket.instances.push(this);
  }

  close(code = 1000, reason = ''): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }

  emit(payload: object): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent);
  }
}

describe('useRoomFeed', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    wake.mockReset();
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('wakes the backend before opening the viewer WebSocket', async () => {
    let releaseWake!: () => void;
    wake.mockReturnValue(new Promise<void>((resolve) => { releaseWake = resolve; }));
    const { unmount } = renderHook(() => useRoomFeed('TABKNF'));

    expect(wake).toHaveBeenCalledOnce();
    expect(MockWebSocket.instances).toHaveLength(0);

    await act(async () => {
      releaseWake();
      await Promise.resolve();
    });

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain('/ws/rooms/TABKNF');
    unmount();
  });

  it('loads an archived snapshot and stops reconnecting', async () => {
    wake.mockResolvedValue(undefined);
    const { result, unmount } = renderHook(() => useRoomFeed('TABKNF'));

    await act(async () => { await Promise.resolve(); });
    const socket = MockWebSocket.instances[0];
    act(() => {
      socket.emit({
        type: 'room_snapshot',
        title: 'Saved meeting',
        status: 'ended',
        viewer_count: 0,
        segments: [],
      });
    });

    expect(result.current.status).toBe('ended');
    expect(socket.readyState).toBe(MockWebSocket.CLOSED);
    expect(MockWebSocket.instances).toHaveLength(1);
    unmount();
  });
});
