/**
 * App.tsx — Root application component for LiveCap.
 *
 * Composes:
 *   - useAudioCapture  → microphone access, PCM chunks
 *   - useWebSocket     → WSS session lifecycle, message parsing
 *   - CaptionDisplay   → bilingual captions
 *   - ExportPanel      → transcript export
 *   - ControlPanel     → start/stop controls
 *
 * Manages AppState (isCapturing, isConnected, sessionId, segments,
 * currentPartial, error) and renders error / connection-lost messages.
 *
 * Requirements: 1.1, 1.4, 1.5, 2.6, 6.1, 6.2
 */

import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import type { AppState, Segment } from '../types/index';
import { useAudioCapture } from '../hooks/useAudioCapture';
import { useWebSocket } from '../hooks/useWebSocket';
import CaptionDisplay from './CaptionDisplay';
import ExportPanel from './ExportPanel';
import ControlPanel from './ControlPanel';

// ---------------------------------------------------------------------------
// State management — useReducer
// ---------------------------------------------------------------------------

type AppAction =
  | { type: 'SESSION_START'; sessionId: string }
  | { type: 'SESSION_RECONNECT_START'; sessionId: string }
  | { type: 'PARTIAL_SEGMENT'; segment: Segment }
  | { type: 'FINALIZED_SEGMENT'; segment: Segment }
  | { type: 'SESSION_END' }
  | { type: 'SET_ERROR'; error: string }
  | { type: 'CLEAR_ERROR' }
  | { type: 'SET_CAPTURING'; value: boolean }
  | { type: 'SET_CONNECTED'; value: boolean }
  | { type: 'RESET_SESSION' };

const initialState: AppState = {
  isCapturing: false,
  isConnected: false,
  sessionId: null,
  segments: [],
  currentPartial: null,
  error: null,
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SESSION_START':
      return {
        ...state,
        sessionId: action.sessionId,
        isConnected: true,
        segments: [],
        currentPartial: null,
        error: null,
      };

    case 'SESSION_RECONNECT_START':
      return {
        ...state,
        sessionId: action.sessionId,
        isConnected: true,
        currentPartial: null,
        error: null,
      };

    case 'PARTIAL_SEGMENT':
      return { ...state, currentPartial: action.segment };

    case 'FINALIZED_SEGMENT': {
      // Remove the partial if it matches this segment, then append the
      // finalized version to the ordered list.
      const alreadyPresent = state.segments.some(
        (s) => s.segmentId === action.segment.segmentId
      );
      if (alreadyPresent) return state; // idempotent
      return {
        ...state,
        segments: [...state.segments, action.segment],
        currentPartial:
          state.currentPartial?.segmentId === action.segment.segmentId
            ? null
            : state.currentPartial,
      };
    }

    case 'SESSION_END':
      return {
        ...state,
        isConnected: false,
        isCapturing: false,
        currentPartial: null,
      };

    case 'SET_ERROR':
      return { ...state, error: action.error };

    case 'CLEAR_ERROR':
      return { ...state, error: null };

    case 'SET_CAPTURING':
      return { ...state, isCapturing: action.value };

    case 'SET_CONNECTED':
      return { ...state, isConnected: action.value };

    case 'RESET_SESSION':
      return {
        ...initialState,
        // Preserve segments for export after a session ends
        segments: state.segments,
        sessionId: state.sessionId,
      };

    default:
      return state;
  }
}

// ---------------------------------------------------------------------------
// App
// ---------------------------------------------------------------------------

export default function App() {
  const [state, dispatch] = useReducer(appReducer, initialState);
  const [recordingStartedAt, setRecordingStartedAt] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(Date.now());
  const stopCaptureRef = useRef<(() => void) | null>(null);

  // ------------------------------------------------------------------
  // WebSocket hook — message parsing → state updates
  // ------------------------------------------------------------------
  const {
    isConnected,
    isConnectionLost,
    connectionStatus,
    connect,
    disconnect,
    sendAudioChunk,
  } = useWebSocket({
    reconnectOnUnexpectedClose: state.isCapturing,
    onSessionStart(sessionId, isReconnect) {
      dispatch({
        type: isReconnect ? 'SESSION_RECONNECT_START' : 'SESSION_START',
        sessionId,
      });
    },
    onPartialSegment(segment) {
      dispatch({ type: 'PARTIAL_SEGMENT', segment });
    },
    onFinalizedSegment(segment) {
      dispatch({ type: 'FINALIZED_SEGMENT', segment });
    },
    onError(message) {
      dispatch({ type: 'SET_ERROR', error: message });
    },
    onSessionEnd() {
      dispatch({ type: 'SESSION_END' });
    },
    onReconnectFailed() {
      stopCaptureRef.current?.();
      setRecordingStartedAt(null);
      dispatch({ type: 'SET_CAPTURING', value: false });
      dispatch({
        type: 'SET_ERROR',
        error: 'Connection lost. Please restart the session.',
      });
    },
  });

  // ------------------------------------------------------------------
  // Audio capture hook — chunks → WebSocket
  // ------------------------------------------------------------------
  const {
    isCapturing,
    permissionDenied,
    audioInputDevices,
    selectedDeviceId,
    setSelectedDeviceId,
    refreshAudioInputDevices,
    startCapture,
    stopCapture,
  } = useAudioCapture({
    onChunk: sendAudioChunk,
  });

  useEffect(() => {
    stopCaptureRef.current = stopCapture;
  }, [stopCapture]);

  useEffect(() => {
    if (!isCapturing) {
      setRecordingStartedAt(null);
      return undefined;
    }

    setNowMs(Date.now());
    const intervalId = window.setInterval(() => {
      setNowMs(Date.now());
    }, 1_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [isCapturing]);

  // ------------------------------------------------------------------
  // Start: connect WebSocket then begin audio capture
  // ------------------------------------------------------------------
  const handleStart = useCallback(async () => {
    dispatch({ type: 'CLEAR_ERROR' });
    connect();
    try {
      await startCapture();
      setRecordingStartedAt(Date.now());
      dispatch({ type: 'SET_CAPTURING', value: true });
    } catch {
      // Permission denied is exposed via permissionDenied; other errors
      // are surfaced here as a generic error message.
      if (!permissionDenied) {
        dispatch({
          type: 'SET_ERROR',
          error: 'Failed to start audio capture. Please check your microphone.',
        });
      }
      setRecordingStartedAt(null);
      disconnect();
    }
  }, [connect, disconnect, startCapture, permissionDenied]);

  // ------------------------------------------------------------------
  // Stop: halt audio capture then signal the backend
  // ------------------------------------------------------------------
  const handleStop = useCallback(() => {
    stopCapture();
    disconnect();
    setRecordingStartedAt(null);
    dispatch({ type: 'SET_CAPTURING', value: false });
  }, [stopCapture, disconnect]);

  // ------------------------------------------------------------------
  // Derive "isConnecting": WebSocket connecting but audio not yet flowing
  // ------------------------------------------------------------------
  // We treat the window between pressing Start and audio flowing as
  // "connecting" to disable the button and show a spinner.
  // Simpler heuristic: button is disabled only while the WebSocket is
  // transitioning (between handleStart being called and isConnected toggling).
  // We derive this from the hook itself — isConnected is false before open.
  // The ControlPanel receives isConnecting so it can show the spinner.
  const wsIsConnecting =
    !isCapturing && !isConnectionLost && !isConnected && state.sessionId === null &&
    // Avoid showing "connecting" on initial load before the user presses Start:
    // we rely on the component lifecycle — this flag will only be truthy
    // in the brief window after connect() is called and before onopen fires.
    // For simplicity, we let ControlPanel show normal "Start" state on first
    // render and rely on the disabled flag only when explicitly needed.
    false;

  const recordingDurationSeconds =
    recordingStartedAt !== null && isCapturing
      ? Math.max(0, Math.floor((nowMs - recordingStartedAt) / 1_000))
      : 0;

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  /** Banner shown when the WebSocket drops unexpectedly mid-session (Req 2.6). */
  function ConnectionLostBanner() {
    return (
      <div
        role="alert"
        aria-live="assertive"
        className="flex items-center gap-3 rounded-lg border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
      >
        {/* Warning icon */}
        <svg
          aria-hidden="true"
          className="h-5 w-5 flex-shrink-0 text-yellow-500"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
        <p>
          <strong>Connection lost.</strong> Audio capture has stopped. Please restart the session.
        </p>
      </div>
    );
  }

  function ReconnectedBanner() {
    return (
      <div
        role="status"
        aria-live="polite"
        className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800"
      >
        <p>
          <strong>Reconnected.</strong> A new backend session is active; finalized transcript
          segments were preserved.
        </p>
      </div>
    );
  }

  /** Error toast shown for backend errors and failed capture starts. */
  function ErrorBanner({ message }: { message: string }) {
    return (
      <div
        role="alert"
        aria-live="assertive"
        className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
      >
        {/* Error icon */}
        <svg
          aria-hidden="true"
          className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500"
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path
            fillRule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z"
            clipRule="evenodd"
          />
        </svg>
        <div className="flex-1">
          <p className="font-medium">Error</p>
          <p className="mt-0.5 text-red-700">{message}</p>
        </div>
        <button
          onClick={() => dispatch({ type: 'CLEAR_ERROR' })}
          aria-label="Dismiss error"
          className="rounded bg-red-100 px-2.5 py-1 text-xs font-medium text-red-800 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-red-400"
        >
          ✕
        </button>
      </div>
    );
  }

  // Derive whether the session has concluded and has exportable data.
  const hasCompletedSession =
    !isCapturing && !isConnectionLost && state.segments.length > 0;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
      {/* ------------------------------------------------------------------ */}
      {/* Header                                                              */}
      {/* ------------------------------------------------------------------ */}
      <header className="border-b border-slate-200 bg-white px-6 py-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">LiveCap</h1>

        {/* Session ID badge — visible while connected */}
        {state.sessionId && (
          <span
            aria-label={`Session ID: ${state.sessionId}`}
            className="text-xs text-slate-400 font-mono truncate max-w-xs"
          >
            Session: {state.sessionId}
          </span>
        )}
      </header>

      {/* ------------------------------------------------------------------ */}
      {/* Main content area                                                   */}
      {/* ------------------------------------------------------------------ */}
      <main className="flex-1 flex flex-col gap-4 p-6 max-w-5xl mx-auto w-full">

        {/* Status banners */}
        {isConnectionLost && <ConnectionLostBanner />}
        {connectionStatus === 'reconnected' && !isConnectionLost && <ReconnectedBanner />}
        {state.error && <ErrorBanner message={state.error} />}

        {/* Control panel — start/stop + active indicator */}
        <div className="flex justify-center py-2">
          <ControlPanel
            isCapturing={isCapturing}
            isConnecting={wsIsConnecting}
            permissionDenied={permissionDenied}
            recordingDurationSeconds={recordingDurationSeconds}
            audioInputDevices={audioInputDevices}
            selectedDeviceId={selectedDeviceId}
            onSelectedDeviceChange={setSelectedDeviceId}
            onRefreshAudioInputDevices={refreshAudioInputDevices}
            onStart={handleStart}
            onStop={handleStop}
          />
        </div>

        {/* Caption display — two-column bilingual captions */}
        <div className="flex-1 min-h-0" style={{ minHeight: '300px' }}>
          <CaptionDisplay
            segments={state.segments}
            currentPartial={state.currentPartial}
          />
        </div>

        {/* Export panel — only shown when there are segments to export */}
        {(hasCompletedSession || state.segments.length > 0) && (
          <div className="pt-2 border-t border-slate-200">
            <ExportPanel
              sessionId={state.sessionId}
              segments={state.segments}
            />
          </div>
        )}
      </main>
    </div>
  );
}
