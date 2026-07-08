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
import { GlassPanel, StatusBadge, type BadgeStatus } from './ui';
import { Activity, Clock, Layers, AlertTriangle, CheckCircle } from 'lucide-react';

const DEFAULT_MAX_SESSION_SECONDS = 1_800;

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
      isWakeBackendConfigured() ? 'Waking Node' : 'Linking',
    );

    try {
      await wakeBackendIfConfigured();
      startPhase = 'socket';
      setStartStatusLabel('Connecting');
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
    <div className="min-h-screen overflow-x-hidden bg-obsidian text-white font-ui antialiased">
      {/* Background patterns */}
      <div className="fixed inset-0 pointer-events-none opacity-20 z-0">
        <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:64px_64px]" />
      </div>

      <header className="sticky top-0 z-[60] border-b border-white/5 bg-obsidian/60 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-[1600px] items-center justify-between px-5 py-3 lg:px-10">
          <div className="flex items-center gap-4">
            <a href="/" className="text-lg font-bold tracking-tighter text-white flex items-center gap-2">
              <Activity className="w-4 h-4 text-crimson" />
              LIVECAP
            </a>
            <StatusBadge status={statusCopy.tone as BadgeStatus} label={statusCopy.label} />
          </div>

          <div className="flex items-center gap-4 lg:gap-10">
            <HeaderMetric icon={<Clock className="w-3 h-3" />} label="TIME" value={formatDuration(recordingDurationSeconds)} />
            <div className="hidden lg:flex items-center gap-10">
              <HeaderMetric icon={<Clock className="w-3 h-3 text-crimson" />} label="LIMIT" value={formatDuration(remainingSessionSeconds)} />
              <HeaderMetric icon={<Layers className="w-3 h-3" />} label="DATA" value={state.segments.length.toString()} />
            </div>
          </div>
        </div>
      </header>

      <main className="relative z-10 mx-auto grid w-full max-w-[1600px] grid-cols-1 gap-6 p-5 lg:grid-cols-[360px_1fr] lg:p-10 lg:pt-8">
        <aside className="space-y-6">
          <ControlPanel
            isCapturing={isCapturing}
            isConnecting={wsIsConnecting}
            connectionStatusLabel={startStatusLabel}
            permissionDenied={permissionDenied}
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
        </aside>

        <section className="min-h-[60vh] space-y-4">
          {state.error && (
            <AlertBanner
              tone="error"
              title="System Error"
              message={state.error}
              onDismiss={() => dispatch({ type: 'CLEAR_ERROR' })}
            />
          )}

          {isConnectionLost && (
            <AlertBanner
              tone="warning"
              title="Stream Disrupted"
              message="The connection was lost. Please verify your internet and restart the engine."
            />
          )}

          <CaptionDisplay
            segments={state.segments}
            currentPartial={state.currentPartial}
            isCapturing={isCapturing}
            isConnecting={wsIsConnecting}
            permissionDenied={permissionDenied}
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

function HeaderMetric({ label, value, icon }: { label: string; value: string; icon?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <div className="hidden sm:flex flex-col items-end gap-0.5">
        <span className="text-[9px] font-mono font-bold tracking-widest text-white/30 uppercase leading-none">{label}</span>
        <div className="flex items-center gap-1.5 mt-0.5">
          <span className="font-mono text-sm font-bold tabular-nums text-white">
            {value}
          </span>
          {icon}
        </div>
      </div>
      <div className="sm:hidden flex items-center gap-2 border border-white/5 bg-white/5 px-2 py-1">
        <span className="text-[8px] font-mono font-bold text-white/40 uppercase">{label}</span>
        <span className="font-mono text-xs font-bold text-white leading-none">{value}</span>
      </div>
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
    <GlassPanel className="p-6">
      <h2 className="text-xs font-bold uppercase tracking-widest text-white/40">Session Node</h2>
      <dl className="mt-5 space-y-4 text-xs font-mono">
        <InfoRow label="GATEWAY" value={connectionStatus} />
        <InfoRow label="CLUSTER" value={wakeConfigured ? 'AWS_FARGATE_WAKE' : 'DIRECT_STREAM'} />
        <div className="space-y-2">
          <dt className="text-white/30 tracking-widest">TRACE_ID</dt>
          <dd className="break-all text-[10px] text-white/70 uppercase">{sessionId ?? 'NULL_PTR'}</dd>
        </div>
      </dl>
    </GlassPanel>
  );
}

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-white/30 tracking-widest">{label}</dt>
      <dd className="text-white/80 uppercase">{value}</dd>
    </div>
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
  const colors = {
    success: 'border-emerald-pro/30 bg-emerald-pro/10 text-emerald-pro shadow-[0_0_15px_rgba(5,150,105,0.1)]',
    warning: 'border-amber-400/30 bg-amber-400/10 text-amber-400 shadow-[0_0_15px_rgba(251,191,36,0.1)]',
    error: 'border-crimson/30 bg-crimson/10 text-crimson shadow-[0_0_15px_rgba(225,29,72,0.1)]',
  }[tone];

  const Icon = {
    success: CheckCircle,
    warning: AlertTriangle,
    error: AlertTriangle,
  }[tone];

  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      aria-live={tone === 'error' ? 'assertive' : 'polite'}
      className={`flex items-start gap-4 border p-5 text-xs font-mono uppercase tracking-wider backdrop-blur-md ${colors}`}
    >
      <Icon className="w-5 h-5 shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <p className="font-bold tracking-widest">{title}</p>
        <p className="mt-1.5 normal-case opacity-70 leading-relaxed">{message}</p>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="hover:text-white transition-colors border border-current px-2 py-1"
        >
          DISMISS
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
}): { label: string; tone: string } {
  if (isConnectionLost) return { label: 'LOST', tone: 'error' };
  if (isStarting || connectionStatus === 'connecting') {
    return { label: 'WAKING', tone: 'waking' };
  }
  if (connectionStatus === 'reconnecting') {
    return { label: 'LINKING', tone: 'connecting' };
  }
  if (isCapturing) return { label: 'ACTIVE', tone: 'active' };
  if (connectionStatus === 'reconnected') {
    return { label: 'RELINKED', tone: 'success' };
  }
  return { label: 'READY', tone: 'idle' };
}

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds
    .toString()
    .padStart(2, '0')}`;
}
