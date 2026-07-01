import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useWebSocket } from './useWebSocket';

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  readonly url: string;
  binaryType: BinaryType = 'blob';
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

  open(): void {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.(new Event('open'));
  }

  close(code = 1000, reason = ''): void {
    if (this.readyState === MockWebSocket.CLOSED) return;
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code, reason } as CloseEvent);
  }

  failBeforeOpen(): void {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code: 1006, reason: '' } as CloseEvent);
  }
}

describe('useWebSocket initial connection', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('resolves connect only after the socket opens', async () => {
    const { result, unmount } = renderHook(() => useWebSocket());

    let connection!: Promise<void>;
    act(() => {
      connection = result.current.connect();
    });

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(result.current.connectionStatus).toBe('connecting');

    await act(async () => {
      MockWebSocket.instances[0].open();
      await connection;
    });

    expect(result.current.connectionStatus).toBe('connected');
    expect(result.current.isConnected).toBe(true);
    unmount();
  });

  it('rejects connect when the socket closes before opening', async () => {
    const { result } = renderHook(() => useWebSocket());

    let connection!: Promise<void>;
    act(() => {
      connection = result.current.connect();
    });
    const rejection = expect(connection).rejects.toThrow(
      'WebSocket closed before opening'
    );

    act(() => {
      MockWebSocket.instances[0].failBeforeOpen();
    });

    await rejection;
    expect(result.current.connectionStatus).toBe('lost');
    expect(result.current.isConnected).toBe(false);
  });

  it('drops audio until the socket is open', async () => {
    const { result, unmount } = renderHook(() => useWebSocket());
    const audioChunk = new ArrayBuffer(64);

    let connection!: Promise<void>;
    act(() => {
      connection = result.current.connect();
      result.current.sendAudioChunk(audioChunk);
    });

    expect(MockWebSocket.instances[0].send).not.toHaveBeenCalled();

    await act(async () => {
      MockWebSocket.instances[0].open();
      await connection;
    });
    act(() => {
      result.current.sendAudioChunk(audioChunk);
    });

    expect(MockWebSocket.instances[0].send).toHaveBeenCalledOnce();
    expect(MockWebSocket.instances[0].send).toHaveBeenCalledWith(audioChunk);
    unmount();
  });

  it('stops reconnecting after three retry attempts', async () => {
    vi.useFakeTimers();
    const onReconnectFailed = vi.fn();
    const { result, unmount } = renderHook(() =>
      useWebSocket({
        reconnectOnUnexpectedClose: true,
        onReconnectFailed,
      })
    );

    let connection!: Promise<void>;
    act(() => {
      connection = result.current.connect();
    });
    await act(async () => {
      MockWebSocket.instances[0].open();
      await connection;
    });

    act(() => {
      MockWebSocket.instances[0].close(1006, 'network lost');
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(MockWebSocket.instances).toHaveLength(2);
    act(() => MockWebSocket.instances[1].failBeforeOpen());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(MockWebSocket.instances).toHaveLength(3);
    act(() => MockWebSocket.instances[2].failBeforeOpen());

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4_000);
    });
    expect(MockWebSocket.instances).toHaveLength(4);
    act(() => MockWebSocket.instances[3].failBeforeOpen());

    expect(onReconnectFailed).toHaveBeenCalledOnce();
    expect(result.current.connectionStatus).toBe('lost');
    unmount();
  });
});
