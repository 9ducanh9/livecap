/**
 * useWebSocket - WebSocket client hook for the /ws/transcribe streaming channel.
 *
 * Responsibilities:
 *  - Open a WebSocket connection to /ws/transcribe when capture starts.
 *  - Send binary audio chunks while the socket is open.
 *  - Send stop and heartbeat control messages.
 *  - Retry unexpected recording-time disconnects up to a small fixed limit.
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
  SourceLanguageCode,
  TargetLanguageCode,
} from '../types/index';
import { getAccessToken, isAuthConfigured } from '../services/authService';

const DEBUG = import.meta.env.VITE_AUDIO_DEBUG === 'true';
const HEARTBEAT_INTERVAL_MS = 30_000;
const RETRY_DELAYS_MS = [1_000, 2_000, 4_000] as const;
export type WebSocketConnectionStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'reconnected'
  | 'lost';

export interface UseWebSocketOptions {
  sourceLanguage?: SourceLanguageCode;
  targetLanguage?: TargetLanguageCode;
  reconnectOnUnexpectedClose?: boolean;
  onSessionStart?: (sessionId: string, isReconnect: boolean) => void;
  onPartialSegment?: (segment: Segment) => void;
  onFinalizedSegment?: (segment: Segment) => void;
  onError?: (message: string, code: string) => void;
  onSessionEnd?: (sessionId: string | null) => void;
  onReconnectFailed?: () => void;
}

export interface UseWebSocketReturn {
  isConnected: boolean;
  isConnectionLost: boolean;
  connectionStatus: WebSocketConnectionStatus;
  connect: () => Promise<void>;
  disconnect: () => void;
  sendAudioChunk: (chunk: ArrayBuffer) => void;
}

interface PendingConnection {
  promise: Promise<void>;
  resolve: () => void;
  reject: (error: Error) => void;
}

function buildWsUrl(
  sourceLanguage?: SourceLanguageCode,
  targetLanguage?: TargetLanguageCode,
  resumeSessionId?: string | null
): string {
  const configuredUrl = import.meta.env.VITE_WS_URL;
  const baseUrl =
    typeof configuredUrl === 'string' && configuredUrl.trim() !== ''
      ? configuredUrl.trim()
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${
          window.location.host
        }/ws/transcribe`;

  const url = new URL(baseUrl);
  if (sourceLanguage && targetLanguage) {
    url.searchParams.set('source', sourceLanguage);
    url.searchParams.set('target', targetLanguage);
  }
  // On reconnect, ask the backend to resume the same logical session id (B5).
  if (resumeSessionId) {
    url.searchParams.set('session_id', resumeSessionId);
  }
  return url.toString();
}

function parseServerMessage(raw: unknown): ServerMessage | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const obj = raw as Record<string, unknown>;
  if (typeof obj['type'] !== 'string') return null;

  switch (obj['type']) {
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

    case 'pong':
      return { type: 'pong' };

    default:
      return null;
  }
}

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

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const optionsRef = useRef(options);
  useEffect(() => {
    optionsRef.current = options;
  });

  const wsRef = useRef<WebSocket | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const intentionalCloseRef = useRef(false);
  const retryAttemptRef = useRef(0);
  const reconnectingRef = useRef(false);
  const retryTimerRef = useRef<number | null>(null);
  const heartbeatTimerRef = useRef<number | null>(null);
  const pendingConnectionRef = useRef<PendingConnection | null>(null);

  const [isConnected, setIsConnected] = useState(false);
  const [isConnectionLost, setIsConnectionLost] = useState(false);
  const [connectionStatus, setConnectionStatus] =
    useState<WebSocketConnectionStatus>('idle');

  const clearHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current !== null) {
      window.clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  const clearRetryTimer = useCallback(() => {
    if (retryTimerRef.current !== null) {
      window.clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  }, []);

  const resolvePendingConnection = useCallback(() => {
    pendingConnectionRef.current?.resolve();
    pendingConnectionRef.current = null;
  }, []);

  const rejectPendingConnection = useCallback((error: Error) => {
    pendingConnectionRef.current?.reject(error);
    pendingConnectionRef.current = null;
  }, []);

  const startHeartbeat = useCallback((ws: WebSocket) => {
    clearHeartbeat();
    heartbeatTimerRef.current = window.setInterval(() => {
      if (ws.readyState !== WebSocket.OPEN) return;
      try {
        ws.send(JSON.stringify({ type: 'ping' }));
      } catch (err) {
        console.error('[useWebSocket] Failed to send ping:', err);
      }
    }, HEARTBEAT_INTERVAL_MS);
  }, [clearHeartbeat]);

  const openSocket = useCallback((isRetry: boolean) => {
    clearRetryTimer();
    setConnectionStatus(isRetry ? 'reconnecting' : 'connecting');

    let ws: WebSocket;
    try {
      const url = buildWsUrl(
        optionsRef.current.sourceLanguage,
        optionsRef.current.targetLanguage,
        isRetry ? sessionIdRef.current : null
      );
      const token = getAccessToken();
      // JWT travels in Sec-WebSocket-Protocol instead of the URL, avoiding
      // accidental token capture in browser history and request logs.
      ws = isAuthConfigured()
        ? new WebSocket(url, ['livecap.v1', token ?? 'missing-token'])
        : new WebSocket(url);
    } catch (err) {
      console.error('[useWebSocket] Failed to construct WebSocket:', err);
      setConnectionStatus('lost');
      setIsConnectionLost(true);
      if (isRetry) {
        optionsRef.current.onReconnectFailed?.();
      } else {
        rejectPendingConnection(
          err instanceof Error ? err : new Error('Failed to open WebSocket')
        );
      }
      return;
    }

    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;
    reconnectingRef.current = isRetry;

    ws.onopen = () => {
      setIsConnected(true);
      setIsConnectionLost(false);
      setConnectionStatus(isRetry ? 'reconnected' : 'connected');
      retryAttemptRef.current = 0;
      startHeartbeat(ws);
      if (!isRetry) {
        resolvePendingConnection();
      }
    };

    ws.onmessage = (event: MessageEvent) => {
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
          cb.onSessionStart?.(msg.session_id, reconnectingRef.current);
          reconnectingRef.current = false;
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

        case 'pong':
          debugLog('heartbeat-pong', {});
          break;
      }
    };

    ws.onerror = (event: Event) => {
      console.error('[useWebSocket] WebSocket error:', event);
    };

    ws.onclose = (event: CloseEvent) => {
      clearHeartbeat();
      setIsConnected(false);
      wsRef.current = null;

      if (intentionalCloseRef.current) {
        rejectPendingConnection(new Error('WebSocket connection was cancelled'));
        optionsRef.current.onSessionEnd?.(sessionIdRef.current);
        setConnectionStatus('idle');
        return;
      }

      const shouldRetry = optionsRef.current.reconnectOnUnexpectedClose === true;
      if (!shouldRetry) {
        console.warn(
          `[useWebSocket] Connection lost unexpectedly (code=${event.code}, reason="${event.reason}").`
        );
        setConnectionStatus('lost');
        setIsConnectionLost(true);
        rejectPendingConnection(
          new Error(
            event.reason || `WebSocket closed before opening (code ${event.code})`
          )
        );
        return;
      }

      if (retryAttemptRef.current >= RETRYABLE_RETRY_COUNT) {
        setConnectionStatus('lost');
        setIsConnectionLost(true);
        optionsRef.current.onReconnectFailed?.();
        return;
      }

      const delayMs = RETRY_DELAYS_MS[retryAttemptRef.current];
      retryAttemptRef.current += 1;
      setConnectionStatus('reconnecting');
      retryTimerRef.current = window.setTimeout(() => {
        openSocket(true);
      }, delayMs);
    };
  }, [
    clearHeartbeat,
    clearRetryTimer,
    rejectPendingConnection,
    resolvePendingConnection,
    startHeartbeat,
  ]);

  const connect = useCallback((): Promise<void> => {
    if (
      wsRef.current !== null &&
      wsRef.current.readyState === WebSocket.OPEN
    ) {
      return Promise.resolve();
    }

    if (
      wsRef.current !== null &&
      wsRef.current.readyState === WebSocket.CONNECTING &&
      pendingConnectionRef.current !== null
    ) {
      return pendingConnectionRef.current.promise;
    }

    intentionalCloseRef.current = false;
    reconnectingRef.current = false;
    retryAttemptRef.current = 0;
    sessionIdRef.current = null;
    setIsConnectionLost(false);

    let resolveConnection!: () => void;
    let rejectConnection!: (error: Error) => void;
    const connectionPromise = new Promise<void>((resolve, reject) => {
      resolveConnection = resolve;
      rejectConnection = reject;
    });
    pendingConnectionRef.current = {
      promise: connectionPromise,
      resolve: resolveConnection,
      reject: rejectConnection,
    };

    openSocket(false);
    return connectionPromise;
  }, [openSocket]);

  const disconnect = useCallback(() => {
    clearRetryTimer();
    clearHeartbeat();
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
      ws.close(1000, 'User stopped capture');
    }
  }, [clearHeartbeat, clearRetryTimer]);

  const sendAudioChunk = useCallback((chunk: ArrayBuffer) => {
    const ws = wsRef.current;
    if (ws === null || ws.readyState !== WebSocket.OPEN) {
      return;
    }
    try {
      ws.send(chunk);
      debugLog('websocket-send-audio', {
        websocketSendByteLength: chunk.byteLength,
      });
    } catch (err) {
      console.error('[useWebSocket] Failed to send audio chunk:', err);
    }
  }, []);

  useEffect(() => {
    return () => {
      clearRetryTimer();
      clearHeartbeat();
      const ws = wsRef.current;
      if (ws !== null) {
        intentionalCloseRef.current = true;
        ws.close(1001, 'Component unmounted');
      }
      pendingConnectionRef.current = null;
    };
  }, [clearHeartbeat, clearRetryTimer]);

  return {
    isConnected,
    isConnectionLost,
    connectionStatus,
    connect,
    disconnect,
    sendAudioChunk,
  };
}

export type { AppState };

const RETRYABLE_RETRY_COUNT = RETRY_DELAYS_MS.length;

function debugLog(message: string, data: Record<string, number>): void {
  if (!DEBUG) return;
  console.debug(`[useWebSocket] ${message}`, data);
}
