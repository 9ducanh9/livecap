import { useEffect, useRef, useState } from 'react';
import type { Segment } from '../types';
import { buildRoomWebSocketUrl, segmentFromWire } from '../services/roomService';
import { wakeBackendIfConfigured } from '../services/wakeService';

export type RoomFeedStatus = 'connecting' | 'live' | 'reconnecting' | 'ended' | 'error';

export interface RoomFeedState {
  title: string;
  status: RoomFeedStatus;
  viewerCount: number;
  segments: Segment[];
  error: string | null;
}

const RETRY_DELAYS_MS = [1_000, 2_000, 4_000] as const;

export function useRoomFeed(roomCode: string): RoomFeedState {
  const [state, setState] = useState<RoomFeedState>({
    title: 'LiveCap room',
    status: 'connecting',
    viewerCount: 0,
    segments: [],
    error: null,
  });
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let disposed = false;
    let retryTimer: number | null = null;
    let heartbeatTimer: number | null = null;
    let retryIndex = 0;
    let terminalError = false;

    const connect = () => {
      if (disposed) return;
      setState((current) => ({
        ...current,
        status: retryIndex > 0 ? 'reconnecting' : 'connecting',
        error: null,
      }));
      const socket = new WebSocket(buildRoomWebSocketUrl(roomCode));
      socketRef.current = socket;

      socket.onopen = () => {
        heartbeatTimer = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30_000);
      };

      socket.onmessage = (event) => {
        if (typeof event.data !== 'string') return;
        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(event.data) as Record<string, unknown>;
        } catch {
          return;
        }
        if (payload['type'] === 'room_snapshot') {
          const rawSegments = Array.isArray(payload['segments']) ? payload['segments'] : [];
          const segments = rawSegments.map(segmentFromWire).filter((item): item is Segment => item !== null);
          retryIndex = 0;
          const ended = payload['status'] === 'ended';
          terminalError = ended;
          setState({
            title: typeof payload['title'] === 'string' ? payload['title'] : 'LiveCap room',
            status: ended ? 'ended' : 'live',
            viewerCount: typeof payload['viewer_count'] === 'number' ? payload['viewer_count'] : 0,
            segments,
            error: null,
          });
          if (ended) socket.close(1000, 'archived room loaded');
          return;
        }
        if (payload['type'] === 'room_segment') {
          const segment = segmentFromWire(payload['segment']);
          if (!segment) return;
          setState((current) => current.segments.some((item) => item.segmentId === segment.segmentId)
            ? current
            : { ...current, status: 'live', segments: [...current.segments, segment] });
          return;
        }
        if (payload['type'] === 'room_closed') {
          terminalError = true;
          setState((current) => ({ ...current, status: 'ended' }));
          socket.close(1000, 'room ended');
          return;
        }
        if (payload['type'] === 'room_error') {
          terminalError = true;
          setState((current) => ({
            ...current,
            status: 'error',
            error: typeof payload['message'] === 'string' ? payload['message'] : 'Room is unavailable.',
          }));
        }
      };

      socket.onclose = () => {
        if (heartbeatTimer !== null) {
          window.clearInterval(heartbeatTimer);
          heartbeatTimer = null;
        }
        if (disposed) return;
        if (terminalError) return;
        if (retryIndex >= RETRY_DELAYS_MS.length) {
          setState((current) => ({
            ...current,
            status: current.status === 'ended' ? 'ended' : 'error',
            error: current.status === 'ended' ? null : 'Live captions disconnected. Refresh to try again.',
          }));
          return;
        }
        const delay = RETRY_DELAYS_MS[retryIndex];
        retryIndex += 1;
        retryTimer = window.setTimeout(connect, delay);
      };
    };

    const start = async () => {
      try {
        await wakeBackendIfConfigured();
      } catch (error) {
        if (disposed) return;
        terminalError = true;
        setState((current) => ({
          ...current,
          status: 'error',
          error: error instanceof Error
            ? `Could not start the room service: ${error.message}`
            : 'Could not start the room service.',
        }));
        return;
      }
      connect();
    };

    void start();
    return () => {
      disposed = true;
      if (retryTimer !== null) window.clearTimeout(retryTimer);
      if (heartbeatTimer !== null) window.clearInterval(heartbeatTimer);
      socketRef.current?.close(1000, 'viewer left room');
      socketRef.current = null;
    };
  }, [roomCode]);

  return state;
}
