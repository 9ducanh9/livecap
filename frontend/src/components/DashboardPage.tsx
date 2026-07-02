import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import type { AppState, Segment } from '../types/index';
import { useAudioCapture } from '../hooks/useAudioCapture';
import { useWebSocket, type WebSocketConnectionStatus } from '../hooks/useWebSocket';
import CaptionDisplay from './CaptionDisplay';
import ExportPanel from './ExportPanel';
import ControlPanel from './ControlPanel';
import {
  isWakeBackendConfigured,
  wakeBackendIfConfigured,
} from '../services/wakeService';

const DEFAULT_MAX_SESSION_SECONDS = 1_800;
const SESSION_TIMEOUT_WARNING_SECONDS = 60;

function configuredMaxSessionSeconds(): number {
  const raw = import.meta.env.VITE_MAX_SESSION_SECONDS;
  if (typeof raw !== 'string' || raw.trim() === '') {
    return DEFAULT_MAX_SESSION_SECONDS;
  }

  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return DEFAULT_MAX_SESSION_SECONDS;
  }

  return Math.floor(parsed);
}

type AppAction =
  | { type: 'SESSION_START'; sessionId: string }
  | { type: 'SESSION_RECONNECT_START'; sessionId: string }
  | { type: 'PARTIAL_SEGMENT'; segment: Segment }
  | { type: 'FINALIZED_SEGMENT'; segment: Segment }
  | { type: 'SESSION_END' }
  | { type: 'SET_ERROR'; error: string }
  | { type: 'CLEAR_ERROR' }
  | { type: 'SET_CAPTURING'; value: boolean }
  | { type: 'CLEAR_TRANSCRIPT' };

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
      const alreadyPresent = state.segments.some(
        (segment) => segment.segmentId === action.segment.segmentId,
      );
      if (alreadyPresent) return state;

      return {
        ...state,
        segments: [...state.segments, action.segment],
        currentPartial: null,
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

    case 'CLEAR_TRANSCRIPT':
      return {
        ...state,
        segments: [],
        currentPartial: null,
        error: null,
      };
  }
}

export default function DashboardPage() {
  const [state, dispatch] = useReducer(appReducer, initialState);
  const [recordingStartedAt, setRecordingStartedAt] = useState<number | null>(null);
  const [nowMs, setNowMs] = useState(Date.now());
  const [isStarting, setIsStarting] = useState(false);
  const [startStatusLabel, setStartStatusLabel] = useState<string | null>(null);
  const stopCaptureRef = useRef<(() => void) | null>(null);
  const maxSessionSeconds = configuredMaxSessionSeconds();

  const {
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

  const handleStart = useCallback(async () => {
    let startPhase: 'wake' | 'socket' | 'audio' = 'wake';

    dispatch({ type: 'CLEAR_ERROR' });
    setIsStarting(true);
    setStartStatusLabel(
      isWakeBackendConfigured() ? 'Starting backend' : 'Connecting',
    );

    try {
      await wakeBackendIfConfigured();
      startPhase = 'socket';
      setStartStatusLabel('Opening stream');
      await connect();
      startPhase = 'audio';
      await startCapture();
      setRecordingStartedAt(Date.now());
      dispatch({ type: 'SET_CAPTURING', value: true });
    } catch (err) {
      if (!permissionDenied) {
        dispatch({
          type: 'SET_ERROR',
          error: isBackendWakeError(err)
            ? 'Backend is still starting. Please try again shortly.'
            : startPhase === 'socket'
              ? 'Unable to connect to the backend stream. Please try again.'
              : 'Failed to start audio capture. Please check your microphone.',
        });
      }
      setRecordingStartedAt(null);
      disconnect();
    } finally {
      setIsStarting(false);
      setStartStatusLabel(null);
    }
  }, [connect, disconnect, permissionDenied, startCapture]);

  const handleStop = useCallback(() => {
    stopCapture();
    disconnect();
    setRecordingStartedAt(null);
    dispatch({ type: 'SET_CAPTURING', value: false });
  }, [disconnect, stopCapture]);

  const handleClear = useCallback(() => {
    dispatch({ type: 'CLEAR_TRANSCRIPT' });
  }, []);

  const wsIsConnecting =
    isStarting ||
    connectionStatus === 'connecting' ||
    connectionStatus === 'reconnecting';

  const recordingDurationSeconds =
    recordingStartedAt !== null && isCapturing
      ? Math.max(0, Math.floor((nowMs - recordingStartedAt) / 1_000))
      : 0;

  const remainingSessionSeconds = Math.max(
    0,
    maxSessionSeconds - recordingDurationSeconds,
  );

  useEffect(() => {
    if (!isCapturing || recordingDurationSeconds < maxSessionSeconds) return;
    handleStop();
    dispatch({
      type: 'SET_ERROR',
      error: 'Maximum session duration reached. Please start a new session.',
    });
  }, [handleStop, isCapturing, maxSessionSeconds, recordingDurationSeconds]);

  const statusCopy = getConnectionStatusCopy({
    connectionStatus,
    isCapturing,
    isConnectionLost,
    isStarting,
  });

  return (
    <div className="min-h-screen overflow-x-hidden bg-zinc-50 text-zinc-950">
      <header className="sticky top-0 z-30 border-b border-zinc-200 bg-white/92 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-5 py-4 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <div className="flex min-w-0 items-center gap-4">
            <a href="/" className="text-xl font-semibold tracking-tight text-zinc-950">
              LiveCap
            </a>
            <StatusPill status={statusCopy.tone} label={statusCopy.label} />
          </div>

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <HeaderMetric label="Timer" value={formatDuration(recordingDurationSeconds)} />
            <HeaderMetric label="Remaining" value={formatDuration(remainingSessionSeconds)} />
            <HeaderMetric label="Finalized" value={state.segments.length.toString()} />
          </div>
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-7xl grid-cols-[minmax(0,1fr)] gap-5 px-5 py-5 lg:grid-cols-[380px_minmax(0,1fr)] lg:px-8">
        <section className="min-w-0 space-y-4">
          <ControlPanel
            isCapturing={isCapturing}
            isConnecting={wsIsConnecting}
            connectionStatusLabel={startStatusLabel}
            permissionDenied={permissionDenied}
            recordingDurationSeconds={recordingDurationSeconds}
            maxSessionSeconds={maxSessionSeconds}
            remainingSessionSeconds={remainingSessionSeconds}
            audioInputDevices={audioInputDevices}
            selectedDeviceId={selectedDeviceId}
            canClear={state.segments.length > 0 || state.currentPartial !== null}
            onSelectedDeviceChange={setSelectedDeviceId}
            onRefreshAudioInputDevices={refreshAudioInputDevices}
            onStart={handleStart}
            onStop={handleStop}
            onClear={handleClear}
          />

          <SessionSummary
            sessionId={state.sessionId}
            connectionStatus={connectionStatus}
            wakeConfigured={isWakeBackendConfigured()}
          />

          <ExportPanel
            sessionId={state.sessionId}
            segments={state.segments}
          />
        </section>

        <section className="min-h-[620px] min-w-0 space-y-4">
          {isConnectionLost && (
            <AlertBanner
              tone="warning"
              title="Connection lost"
              message="Audio capture stopped. Restart the session when the backend is ready."
            />
          )}

          {connectionStatus === 'reconnected' && !isConnectionLost && (
            <AlertBanner
              tone="success"
              title="Reconnected"
              message="A new backend session is active. Existing finalized transcript lines were preserved."
            />
          )}

          {isCapturing &&
            remainingSessionSeconds <= SESSION_TIMEOUT_WARNING_SECONDS && (
              <AlertBanner
                tone="warning"
                title="Session limit"
                message={`Capture will stop automatically in ${remainingSessionSeconds} seconds.`}
              />
            )}

          {state.error && (
            <AlertBanner
              tone="error"
              title="Error"
              message={state.error}
              onDismiss={() => dispatch({ type: 'CLEAR_ERROR' })}
            />
          )}

          <CaptionDisplay
            segments={state.segments}
            currentPartial={state.currentPartial}
          />
        </section>
      </main>
    </div>
  );
}

function isBackendWakeError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return (
    err.message.includes('Backend did not become healthy') ||
    err.message.includes('Wake endpoint returned')
  );
}

function HeaderMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1.5">
      <span className="text-xs text-zinc-500">{label}</span>
      <span className="ml-2 font-mono text-xs font-semibold text-zinc-950">
        {value}
      </span>
    </div>
  );
}

function SessionSummary({
  sessionId,
  connectionStatus,
  wakeConfigured,
}: {
  sessionId: string | null;
  connectionStatus: WebSocketConnectionStatus;
  wakeConfigured: boolean;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-zinc-950">Session</h2>
      <dl className="mt-4 space-y-3 text-sm">
        <InfoRow label="Status" value={connectionStatus} />
        <InfoRow label="Wake" value={wakeConfigured ? 'Configured' : 'Direct'} />
        <InfoRow
          label="Session ID"
          value={sessionId ?? 'Not started'}
          valueClassName="font-mono text-xs"
        />
      </dl>
    </div>
  );
}

function InfoRow({
  label,
  value,
  valueClassName = '',
}: {
  label: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="grid grid-cols-[92px_minmax(0,1fr)] gap-3">
      <dt className="text-zinc-500">{label}</dt>
      <dd className={`min-w-0 truncate text-zinc-900 ${valueClassName}`}>
        {value}
      </dd>
    </div>
  );
}

function StatusPill({
  status,
  label,
}: {
  status: 'idle' | 'active' | 'warning' | 'error';
  label: string;
}) {
  const classes = {
    idle: 'border-zinc-200 bg-zinc-100 text-zinc-700',
    active: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    warning: 'border-amber-200 bg-amber-50 text-amber-800',
    error: 'border-rose-200 bg-rose-50 text-rose-700',
  }[status];

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold ${classes}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}

function AlertBanner({
  tone,
  title,
  message,
  onDismiss,
}: {
  tone: 'success' | 'warning' | 'error';
  title: string;
  message: string;
  onDismiss?: () => void;
}) {
  const classes = {
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    warning: 'border-amber-200 bg-amber-50 text-amber-800',
    error: 'border-rose-200 bg-rose-50 text-rose-800',
  }[tone];

  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      aria-live={tone === 'error' ? 'assertive' : 'polite'}
      className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${classes}`}
    >
      <span className="mt-1 h-2 w-2 flex-none rounded-full bg-current" />
      <div className="min-w-0 flex-1">
        <p className="font-semibold">{title}</p>
        <p className="mt-0.5">{message}</p>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="rounded-md px-2 py-1 text-xs font-semibold hover:bg-white/70 focus:outline-none focus:ring-2 focus:ring-current"
        >
          Dismiss
        </button>
      )}
    </div>
  );
}

function getConnectionStatusCopy({
  connectionStatus,
  isCapturing,
  isConnectionLost,
  isStarting,
}: {
  connectionStatus: WebSocketConnectionStatus;
  isCapturing: boolean;
  isConnectionLost: boolean;
  isStarting: boolean;
}): { label: string; tone: 'idle' | 'active' | 'warning' | 'error' } {
  if (isConnectionLost) return { label: 'Lost', tone: 'error' };
  if (isStarting || connectionStatus === 'connecting') {
    return { label: 'Starting', tone: 'warning' };
  }
  if (connectionStatus === 'reconnecting') {
    return { label: 'Reconnecting', tone: 'warning' };
  }
  if (isCapturing) return { label: 'Recording', tone: 'active' };
  if (connectionStatus === 'reconnected') {
    return { label: 'Reconnected', tone: 'active' };
  }
  return { label: 'Ready', tone: 'idle' };
}

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds
    .toString()
    .padStart(2, '0')}`;
}
