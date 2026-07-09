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
import { Activity, Clock, Layers, AlertTriangle, CheckCircle, ArrowLeft } from 'lucide-react';

const DEFAULT_MAX_SESSION_SECONDS = 1_800;

function configuredMaxSessionSeconds(): number {
  const raw = import.meta.env.VITE_MAX_SESSION_SECONDS;
  if (typeof raw !== 'string' || raw.trim() === '') return DEFAULT_MAX_SESSION_SECONDS;
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) return DEFAULT_MAX_SESSION_SECONDS;
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
      return { ...state, sessionId: action.sessionId, isConnected: true, segments: [], currentPartial: null, error: null };
    case 'SESSION_RECONNECT_START':
      return { ...state, sessionId: action.sessionId, isConnected: true, currentPartial: null, error: null };
    case 'PARTIAL_SEGMENT':
      return { ...state, currentPartial: action.segment };
    case 'FINALIZED_SEGMENT': {
      const alreadyPresent = state.segments.some((s) => s.segmentId === action.segment.segmentId);
      if (alreadyPresent) return state;
      return { ...state, segments: [...state.segments, action.segment], currentPartial: null };
    }
    case 'SESSION_END':
      return { ...state, isConnected: false, isCapturing: false, currentPartial: null };
    case 'SET_ERROR':
      return { ...state, error: action.error };
    case 'CLEAR_ERROR':
      return { ...state, error: null };
    case 'SET_CAPTURING':
      return { ...state, isCapturing: action.value };
    case 'CLEAR_TRANSCRIPT':
      return { ...state, segments: [], currentPartial: null, error: null };
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

  const { isConnectionLost, connectionStatus, connect, disconnect, sendAudioChunk } = useWebSocket({
    reconnectOnUnexpectedClose: state.isCapturing,
    onSessionStart(sessionId, isReconnect) {
      dispatch({ type: isReconnect ? 'SESSION_RECONNECT_START' : 'SESSION_START', sessionId });
    },
    onPartialSegment(segment) { dispatch({ type: 'PARTIAL_SEGMENT', segment }); },
    onFinalizedSegment(segment) { dispatch({ type: 'FINALIZED_SEGMENT', segment }); },
    onError(message) { dispatch({ type: 'SET_ERROR', error: message }); },
    onSessionEnd() { dispatch({ type: 'SESSION_END' }); },
    onReconnectFailed() {
      stopCaptureRef.current?.();
      setRecordingStartedAt(null);
      dispatch({ type: 'SET_CAPTURING', value: false });
      dispatch({ type: 'SET_ERROR', error: 'Connection lost. Please restart the session.' });
    },
  });

  const { isCapturing, permissionDenied, audioInputDevices, selectedDeviceId, setSelectedDeviceId, refreshAudioInputDevices, startCapture, stopCapture } = useAudioCapture({ onChunk: sendAudioChunk });

  useEffect(() => { stopCaptureRef.current = stopCapture; }, [stopCapture]);

  useEffect(() => {
    if (!isCapturing) { setRecordingStartedAt(null); return undefined; }
    setNowMs(Date.now());
    const id = window.setInterval(() => setNowMs(Date.now()), 1_000);
    return () => window.clearInterval(id);
  }, [isCapturing]);

  const handleStart = useCallback(async () => {
    let startPhase: 'wake' | 'socket' | 'audio' = 'wake';
    dispatch({ type: 'CLEAR_ERROR' });
    setIsStarting(true);
    setStartStatusLabel(isWakeBackendConfigured() ? 'Waking Node' : 'Linking');
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
    stopCapture(); disconnect(); setRecordingStartedAt(null);
    dispatch({ type: 'SET_CAPTURING', value: false });
  }, [disconnect, stopCapture]);

  const handleClear = useCallback(() => { dispatch({ type: 'CLEAR_TRANSCRIPT' }); }, []);

  const wsIsConnecting = isStarting || connectionStatus === 'connecting' || connectionStatus === 'reconnecting';

  const recordingDurationSeconds = recordingStartedAt !== null && isCapturing
    ? Math.max(0, Math.floor((nowMs - recordingStartedAt) / 1_000))
    : 0;

  const remainingSessionSeconds = Math.max(0, maxSessionSeconds - recordingDurationSeconds);

  useEffect(() => {
    if (!isCapturing || recordingDurationSeconds < maxSessionSeconds) return;
    handleStop();
    dispatch({ type: 'SET_ERROR', error: 'Maximum session duration reached. Please start a new session.' });
  }, [handleStop, isCapturing, maxSessionSeconds, recordingDurationSeconds]);

  const statusCopy = getConnectionStatusCopy({ connectionStatus, isCapturing, isConnectionLost, isStarting });

  return (
    <div className="min-h-screen bg-paper text-ink font-ui antialiased overflow-x-hidden grid-bg">

      {/* TOP HEADER */}
      <header className="sticky top-0 z-[60] border-b border-ink/10 bg-paper">
        <div className="mx-auto flex w-full max-w-[1600px] items-center justify-between px-0">
          {/* Left: back + brand */}
          <div className="flex items-center divide-x divide-ink/10">
            <a href="/" className="flex items-center gap-2 px-6 py-4 group hover:bg-ink/5 transition-colors">
              <ArrowLeft className="w-3 h-3 text-ink/50 group-hover:text-ink transition-colors" />
              <span className="font-mono text-[9px] uppercase tracking-widest text-ink/50 group-hover:text-ink/80 transition-colors">Back</span>
            </a>
            <div className="flex items-center gap-3 px-6 py-4">
              <Activity className="w-4 h-4 text-crimson" />
              <span className="text-sm font-bold tracking-[0.15em] uppercase text-ink">LiveCap</span>
              <StatusDot status={statusCopy.tone} label={statusCopy.label} />
            </div>
          </div>

          {/* Right: metrics */}
          <div className="flex items-center divide-x divide-ink/10">
            <HeaderMetric icon={<Clock className="w-3 h-3 text-ink/50" />} label="TIME" value={formatDuration(recordingDurationSeconds)} />
            <HeaderMetric icon={<Clock className="w-3 h-3 text-crimson" />} label="LIMIT" value={formatDuration(remainingSessionSeconds)} accent />
            <HeaderMetric icon={<Layers className="w-3 h-3 text-ink/50" />} label="SEGS" value={state.segments.length.toString()} />
          </div>
        </div>
      </header>

      {/* MAIN LAYOUT */}
      <main className="mx-auto w-full max-w-[1600px] grid grid-cols-1 lg:grid-cols-[320px_1fr] min-h-[calc(100vh-57px)] border-x border-ink/10">

        {/* LEFT SIDEBAR */}
        <aside className="border-r border-ink/10 flex flex-col bg-paper">
          <div className="px-6 py-4 border-b border-ink/10 bg-paper sticky top-[57px] z-10">
            <p className="font-mono text-[9px] font-bold uppercase tracking-[0.35em] text-ink/50">
              // Control_Panel
            </p>
          </div>
          <div className="flex-1 overflow-y-auto custom-scrollbar">
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
          </div>
        </aside>

        {/* MAIN CONTENT */}
        <section className="flex flex-col min-h-[calc(100vh-57px)]">
          <div className="px-6 py-4 border-b border-ink/10 flex items-center justify-between sticky top-[57px] z-10 bg-paper">
            <p className="font-mono text-[9px] font-bold uppercase tracking-[0.35em] text-ink/50">
              // Transcription_Stream
            </p>
            {isCapturing ? (
              <span className="flex items-center gap-2 font-mono text-[9px] font-bold text-crimson uppercase tracking-widest">
                <span className="w-1.5 h-1.5 rounded-full bg-crimson animate-ping" />
                GATEWAY: LINKED
              </span>
            ) : (
              <span className="font-mono text-[9px] font-bold uppercase tracking-widest text-ink/40">GATEWAY: WAITING</span>
            )}
          </div>

          {/* Alerts */}
          <div className="px-6 pt-4 space-y-3">
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
          </div>

          {/* Captions */}
          <div className="flex-1 overflow-hidden px-6 py-4">
            <CaptionDisplay
              segments={state.segments}
              currentPartial={state.currentPartial}
              isCapturing={isCapturing}
              isConnecting={wsIsConnecting}
              permissionDenied={permissionDenied}
            />
          </div>
        </section>
      </main>
    </div>
  );
}

function isBackendWakeError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  return err.message.includes('Backend did not become healthy') || err.message.includes('Wake endpoint returned');
}

function StatusDot({ status, label }: { status: string; label: string }) {
  const config: Record<string, { dot: string; text: string; border: string; bg: string }> = {
    active:     { dot: 'bg-emerald-pro animate-pulse', text: 'text-emerald-pro', border: 'border-emerald-pro/30', bg: 'bg-emerald-pro/5' },
    waking:     { dot: 'bg-yellow-500 animate-pulse', text: 'text-yellow-600', border: 'border-yellow-400/40', bg: 'bg-yellow-50' },
    connecting: { dot: 'bg-yellow-500 animate-pulse', text: 'text-yellow-600', border: 'border-yellow-400/40', bg: 'bg-yellow-50' },
    success:    { dot: 'bg-emerald-pro', text: 'text-emerald-pro', border: 'border-emerald-pro/30', bg: 'bg-emerald-pro/5' },
    error:      { dot: 'bg-crimson', text: 'text-crimson', border: 'border-crimson/30', bg: 'bg-crimson/5' },
    idle:       { dot: 'bg-ink/20', text: 'text-ink/40', border: 'border-ink/15', bg: 'bg-ink/3' },
  };
  const c = config[status] ?? config.idle;
  return (
    <div className={`flex items-center gap-1.5 border ${c.border} ${c.bg} px-2.5 py-1 font-mono text-[9px] font-bold uppercase tracking-widest ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {label}
    </div>
  );
}

function HeaderMetric({ label, value, icon, accent }: { label: string; value: string; icon?: React.ReactNode; accent?: boolean }) {
  return (
    <div className="flex flex-col items-end px-6 py-4">
      <span className={`font-mono text-[8px] font-bold uppercase tracking-[0.3em] leading-none ${accent ? 'text-crimson' : 'text-ink/50'}`}>
        {label}
      </span>
      <div className="flex items-center gap-1.5 mt-1">
        {icon && <span className={accent ? 'text-crimson' : 'text-ink/50'}>{icon}</span>}
        <span className="font-mono text-sm font-bold tabular-nums text-ink">{value}</span>
      </div>
    </div>
  );
}

function SessionSummary({ sessionId, connectionStatus, wakeConfigured }: {
  sessionId: string | null;
  connectionStatus: WebSocketConnectionStatus;
  wakeConfigured: boolean;
}) {
  return (
    <div className="border-t border-ink/10">
      <div className="px-6 py-4 border-b border-ink/10">
        <p className="font-mono text-[9px] font-bold uppercase tracking-[0.35em] text-ink/50">// Session_Node</p>
      </div>
      <dl className="px-6 py-5 space-y-4 font-mono text-[11px]">
        <InfoRow label="GATEWAY" value={connectionStatus} />
        <InfoRow label="CLUSTER" value={wakeConfigured ? 'AWS_FARGATE_WAKE' : 'DIRECT_STREAM'} />
        <div className="space-y-1.5">
          <dt className="text-ink/50 tracking-widest text-[9px] uppercase">TRACE_ID</dt>
          <dd className="break-all text-[10px] text-ink/70 uppercase font-mono leading-relaxed">
            {sessionId ?? 'NULL_PTR'}
          </dd>
        </div>
      </dl>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-ink/50 tracking-widest text-[9px] uppercase font-bold">{label}</dt>
      <dd className="text-ink font-bold uppercase text-[10px]">{value}</dd>
    </div>
  );
}

function AlertBanner({ tone, title, message, onDismiss }: {
  tone: 'success' | 'warning' | 'error';
  title: string;
  message: string;
  onDismiss?: () => void;
}) {
  const config = {
    success: { border: 'border-emerald-pro/30', bg: 'bg-emerald-pro/5', text: 'text-emerald-pro', sub: 'text-ink/70', Icon: CheckCircle },
    warning: { border: 'border-yellow-400/40', bg: 'bg-yellow-50', text: 'text-yellow-700', sub: 'text-ink/70', Icon: AlertTriangle },
    error:   { border: 'border-crimson/30', bg: 'bg-crimson/5', text: 'text-crimson', sub: 'text-ink/70', Icon: AlertTriangle },
  }[tone];

  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      aria-live={tone === 'error' ? 'assertive' : 'polite'}
      className={`flex items-start gap-4 border ${config.border} ${config.bg} p-4`}
    >
      <config.Icon className={`w-4 h-4 shrink-0 mt-0.5 ${config.text}`} />
      <div className="min-w-0 flex-1">
        <p className={`font-mono text-[10px] font-bold uppercase tracking-widest ${config.text}`}>{title}</p>
        <p className={`mt-1.5 font-mono text-[10px] leading-relaxed ${config.sub}`}>{message}</p>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className={`font-mono text-[9px] font-bold uppercase tracking-widest border ${config.border} px-2.5 py-1.5 ${config.text} hover:opacity-70 transition-opacity`}
        >
          DISMISS
        </button>
      )}
    </div>
  );
}

function getConnectionStatusCopy({ connectionStatus, isCapturing, isConnectionLost, isStarting }: {
  connectionStatus: WebSocketConnectionStatus;
  isCapturing: boolean;
  isConnectionLost: boolean;
  isStarting: boolean;
}): { label: string; tone: string } {
  if (isConnectionLost) return { label: 'LOST', tone: 'error' };
  if (isStarting || connectionStatus === 'connecting') return { label: 'WAKING', tone: 'waking' };
  if (connectionStatus === 'reconnecting') return { label: 'LINKING', tone: 'connecting' };
  if (isCapturing) return { label: 'ACTIVE', tone: 'active' };
  if (connectionStatus === 'reconnected') return { label: 'RELINKED', tone: 'success' };
  return { label: 'READY', tone: 'idle' };
}

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}
