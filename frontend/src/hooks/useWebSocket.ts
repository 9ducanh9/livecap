/**
 * useWebSocket — WebSocket client hook for the /ws/transcribe streaming channel.
 *
 * Responsibilities (Requirements 2.1, 2.4, 2.6, 2.7, 3.2, 3.3, 3.7):
 *  - Open a WSS connection to /ws/transcribe when the user starts capturing.
 *  - Send binary audio chunks (ArrayBuffer) while the session is active.
 *  - Send the JSON stop signal { type: "stop" } when the user stops.
 *  - Parse all server messages (session_start, partial_segment, finalized_segment,
 *    error, session_end) and dispatch them to the caller via callbacks.
 *  - Ignore malformed/unrecognised messages with a console.warn (never throw).
 *  - On unexpected interruption: expose isConnectionLost = true, stop transmitting,
 *    and do NOT automatically reconnect (manual restart required).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  AppState,
  ErrorMessage,
  FinalizedSegmentMessage,
  PartialSegmentMessage,
  Segment,
  ServerMessage,
  SessionEndMessage,
  SessionStartMessage,
} from '../types/index';

const DEBUG = import.meta.env.VITE_AUDIO_DEBUG === 'true';

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

export interface UseWebSocketOptions {
  /** Called once the backend assigns a session ID. */
  onSessionStart?: (sessionId: string) => void;
  /** Called whenever a partial segment is received. */
  onPartialSegment?: (segment: Segment) => void;
  /** Called whenever a finalized segment is received. */
  onFinalizedSegment?: (segment: Segment) => void;
  /** Called when the backend sends an error message. */
  onError?: (message: string, code: string) => void;
  /** Called when the backend sends session_end or the connection closes cleanly. */
  onSessionEnd?: (sessionId: string | null) => void;
}

export interface UseWebSocketReturn {
  /** True while the WebSocket is open and ready. */
  isConnected: boolean;
  /** True after an unexpected disconnection (not triggered by the user stopping). */
  isConnectionLost: boolean;
  /** Open the connection. Idempotent if already open. */
  connect: () => void;
  /** Send the stop signal and close the connection gracefully. */
  disconnect: () => void;
  /** Send a binary audio chunk. No-op when the socket is not open. */
  sendAudioChunk: (chunk: ArrayBuffer) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Derive the WebSocket URL from the current page origin.
 *  http(s)://host[:port] → ws(s)://host[:port]/ws/transcribe */
function buildWsUrl(): string {
  const configuredUrl = import.meta.env.VITE_WS_URL;
  if (typeof configuredUrl === 'string' && configuredUrl.trim() !== '') {
    return configuredUrl.trim();
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/transcribe`;
}

/** Map a raw server JSON payload to the typed ServerMessage union.
 *  Returns null if the payload is not a recognised message shape. */
function parseServerMessage(raw: unknown): ServerMessage | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const obj = raw as Record<string, unknown>;
  if (typeof obj['type'] !== 'string') return null;

  const type = obj['type'] as string;

  switch (type) {
    case 'session_start': {
      if (typeof obj['session_id'] !== 'string') return null;
      return { type: 'session_start', session_id: obj['session_id'] } as SessionStartMessage;
    }

    case 'partial_segment': {
      if (
        typeof obj['segment_id'] !== 'string' ||
        typeof obj['speaker_label'] !== 'string' ||
        typeof obj['text_vi'] !== 'string' ||
        typeof obj['text_en'] !== 'string' ||
        (obj['spoken_language'] !== 'vi' && obj['spoken_language'] !== 'en') ||
        obj['is_final'] !== false
      ) {
        return null;
      }
      return {
        type: 'partial_segment',
        segment_id: obj['segment_id'] as string,
        speaker_label: obj['speaker_label'] as string,
        text_vi: obj['text_vi'] as string,
        text_en: obj['text_en'] as string,
        spoken_language: obj['spoken_language'] as 'vi' | 'en',
        is_final: false,
      } as PartialSegmentMessage;
    }

    case 'finalized_segment': {
      if (
        typeof obj['segment_id'] !== 'string' ||
        typeof obj['speaker_label'] !== 'string' ||
        typeof obj['text_vi'] !== 'string' ||
        typeof obj['text_en'] !== 'string' ||
        (obj['spoken_language'] !== 'vi' && obj['spoken_language'] !== 'en') ||
        obj['is_final'] !== true ||
        typeof obj['timestamp_start'] !== 'number' ||
        typeof obj['timestamp_end'] !== 'number'
      ) {
        return null;
      }
      return {
        type: 'finalized_segment',
        segment_id: obj['segment_id'] as string,
        speaker_label: obj['speaker_label'] as string,
        text_vi: obj['text_vi'] as string,
        text_en: obj['text_en'] as string,
        spoken_language: obj['spoken_language'] as 'vi' | 'en',
        is_final: true,
        timestamp_start: obj['timestamp_start'] as number,
        timestamp_end: obj['timestamp_end'] as number,
      } as FinalizedSegmentMessage;
    }

    case 'error': {
      if (typeof obj['message'] !== 'string' || typeof obj['code'] !== 'string') {
        return null;
      }
      return {
        type: 'error',
        message: obj['message'] as string,
        code: obj['code'] as string,
      } as ErrorMessage;
    }

    case 'session_end': {
      if (typeof obj['session_id'] !== 'string') return null;
      return {
        type: 'session_end',
        session_id: obj['session_id'] as string,
      } as SessionEndMessage;
    }

    default:
      return null;
  }
}

/** Convert a ServerMessage to the frontend Segment shape. */
function toSegment(
  msg: PartialSegmentMessage | FinalizedSegmentMessage
): Segment {
  if (msg.type === 'partial_segment') {
    return {
      segmentId: msg.segment_id,
      speakerLabel: msg.speaker_label,
      textVi: msg.text_vi,
      textEn: msg.text_en,
      spokenLanguage: msg.spoken_language,
      isFinal: false,
      // Partial segments do not carry timestamps; use 0 as a placeholder.
      timestampStart: 0,
      timestampEnd: 0,
    };
  }
  return {
    segmentId: msg.segment_id,
    speakerLabel: msg.speaker_label,
    textVi: msg.text_vi,
    textEn: msg.text_en,
    spokenLanguage: msg.spoken_language,
    isFinal: true,
    timestampStart: msg.timestamp_start,
    timestampEnd: msg.timestamp_end,
  };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const optionsRef = useRef(options);
  // Keep the ref up to date with the latest callbacks without resetting the
  // effect (avoids stale closure issues when callers pass inline functions).
  useEffect(() => {
    optionsRef.current = options;
  });

  const wsRef = useRef<WebSocket | null>(null);
  // Track the current session ID for session_end reporting.
  const sessionIdRef = useRef<string | null>(null);
  // Flag that separates an intentional user-stop from an interruption.
  const intentionalCloseRef = useRef(false);

  const [isConnected, setIsConnected] = useState(false);
  const [isConnectionLost, setIsConnectionLost] = useState(false);

  // ------------------------------------------------------------------
  // connect — open the WebSocket
  // ------------------------------------------------------------------
  const connect = useCallback(() => {
    // Already open or connecting — do nothing.
    if (
      wsRef.current !== null &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    // Clear stale state from a previous (lost) connection before opening a
    // fresh one so the caller always gets a clean slate.
    setIsConnectionLost(false);
    intentionalCloseRef.current = false;
    sessionIdRef.current = null;

    let ws: WebSocket;
    try {
      ws = new WebSocket(buildWsUrl());
    } catch (err) {
      console.error('[useWebSocket] Failed to construct WebSocket:', err);
      setIsConnectionLost(true);
      return;
    }

    // Use binary frames for audio chunks (ArrayBuffer → binary message).
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    // ----------------------------------------------------------------
    // Event handlers
    // ----------------------------------------------------------------

    ws.onopen = () => {
      setIsConnected(true);
      setIsConnectionLost(false);
    };

    ws.onmessage = (event: MessageEvent) => {
      // Only JSON text frames are expected from the server.
      if (typeof event.data !== 'string') {
        console.warn('[useWebSocket] Received unexpected binary frame from server; ignoring.');
        return;
      }

      let parsed: unknown;
      try {
        parsed = JSON.parse(event.data);
      } catch {
        console.warn('[useWebSocket] Received non-JSON message; ignoring:', event.data);
        return;
      }

      const msg = parseServerMessage(parsed);
      if (msg === null) {
        console.warn('[useWebSocket] Received unrecognised/malformed message; ignoring:', parsed);
        return;
      }

      const cb = optionsRef.current;

      switch (msg.type) {
        case 'session_start':
          sessionIdRef.current = msg.session_id;
          cb.onSessionStart?.(msg.session_id);
          break;

        case 'partial_segment':
          cb.onPartialSegment?.(toSegment(msg));
          break;

        case 'finalized_segment':
          cb.onFinalizedSegment?.(toSegment(msg));
          break;

        case 'error':
          cb.onError?.(msg.message, msg.code);
          break;

        case 'session_end':
          sessionIdRef.current = msg.session_id;
          cb.onSessionEnd?.(msg.session_id);
          break;
      }
    };

    ws.onerror = (event: Event) => {
      console.error('[useWebSocket] WebSocket error:', event);
      // onclose fires immediately after onerror; the interruption logic lives there.
    };

    ws.onclose = (event: CloseEvent) => {
      setIsConnected(false);

      if (intentionalCloseRef.current) {
        // User-initiated stop — normal teardown; call onSessionEnd if we
        // did not already receive a session_end message from the server.
        // (The server normally sends session_end before closing, but defend
        // against it not arriving.)
        optionsRef.current.onSessionEnd?.(sessionIdRef.current);
      } else {
        // Unexpected interruption — expose connection-lost state.
        // Per Requirement 2.6 / 2.7: stop transmitting and require manual restart.
        console.warn(
          `[useWebSocket] Connection lost unexpectedly (code=${event.code}, reason="${event.reason}").`
        );
        setIsConnectionLost(true);
      }

      wsRef.current = null;
    };
  }, []);

  // ------------------------------------------------------------------
  // disconnect — send stop signal then close gracefully
  // ------------------------------------------------------------------
  const disconnect = useCallback(() => {
    const ws = wsRef.current;
    if (ws === null) return;

    intentionalCloseRef.current = true;

    if (ws.readyState === WebSocket.OPEN) {
      try {
        ws.send(JSON.stringify({ type: 'stop' }));
      } catch (err) {
        console.error('[useWebSocket] Failed to send stop message:', err);
      }
      ws.close(1000, 'User stopped capture');
    } else {
      // CONNECTING — cannot send yet; just close it.
      ws.close(1000, 'User stopped capture');
    }
  }, []);

  // ------------------------------------------------------------------
  // sendAudioChunk — transmit a binary PCM frame
  // ------------------------------------------------------------------
  const sendAudioChunk = useCallback((chunk: ArrayBuffer) => {
    const ws = wsRef.current;
    if (ws === null || ws.readyState !== WebSocket.OPEN) {
      // Silently drop: the caller may briefly produce chunks after the
      // connection closes; logging would be too noisy.
      return;
    }
    try {
      ws.send(chunk);
      debugLog('websocket-send-audio', { byteLength: chunk.byteLength });
    } catch (err) {
      console.error('[useWebSocket] Failed to send audio chunk:', err);
    }
  }, []);

  // ------------------------------------------------------------------
  // Cleanup on unmount — close without marking as intentional so that
  // any in-progress session is terminated cleanly.
  // ------------------------------------------------------------------
  useEffect(() => {
    return () => {
      const ws = wsRef.current;
      if (ws !== null) {
        intentionalCloseRef.current = true;
        ws.close(1001, 'Component unmounted');
      }
    };
  }, []);

  return {
    isConnected,
    isConnectionLost,
    connect,
    disconnect,
    sendAudioChunk,
  };
}

// ---------------------------------------------------------------------------
// Re-export AppState for convenience — consumers can import it from here.
// ---------------------------------------------------------------------------
export type { AppState };

function debugLog(message: string, data: Record<string, number>): void {
  if (!DEBUG) return;
  console.debug(`[useWebSocket] ${message}`, data);
}
