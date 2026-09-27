import type { AudioInputDevice } from '../hooks/useAudioCapture';
import { Mic, MicOff, RefreshCcw, Info, AlertTriangle, Square } from 'lucide-react';

interface ControlPanelProps {
  isCapturing: boolean;
  roomStatus?: 'live' | 'ended' | null;
  isConnecting: boolean;
  connectionStatusLabel?: string | null;
  permissionDenied: boolean;
  audioInputDevices: AudioInputDevice[];
  selectedDeviceId: string;
  microphoneGain?: number;
  inputLevel?: number;
  canClear: boolean;
  onSelectedDeviceChange: (deviceId: string) => void;
  onMicrophoneGainChange?: (percent: number) => void;
  onRefreshAudioInputDevices: () => void;
  onStart: () => void;
  onStop: () => void;
  onClear: () => void;
}

export default function ControlPanel({
  isCapturing,
  roomStatus = null,
  isConnecting,
  connectionStatusLabel,
  permissionDenied,
  audioInputDevices,
  selectedDeviceId,
  microphoneGain = 100,
  inputLevel = 0,
  canClear,
  onSelectedDeviceChange,
  onMicrophoneGainChange,
  onRefreshAudioInputDevices,
  onStart,
  onStop,
  onClear,
}: ControlPanelProps) {
  const deviceControlsDisabled = isCapturing || isConnecting || roomStatus === 'ended';

  return (
    <div className="border-b border-[#dce5f2]">
      {/* Engine header */}
      <div className="px-6 pt-6 pb-4 flex items-start justify-between">
        <div>
          <p className="text-sm font-bold text-ink">{roomStatus === 'live' ? 'Room microphone' : roomStatus === 'ended' ? 'Room ended' : 'Ready to listen'}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-ink-muted">
            {roomStatus === 'live'
              ? 'Turn on your mic so viewers can hear you and see captions.'
              : roomStatus === 'ended'
                ? 'This saved room cannot receive more audio or captions.'
                : 'Choose an input, then start a live session.'}
          </p>
        </div>
        <div className={`flex items-center gap-1.5 rounded-full text-[10px] font-bold border px-2.5 py-1 ${
          isCapturing
            ? 'border-emerald-pro/30 text-emerald-pro bg-emerald-pro/5'
            : 'border-ink/20 text-ink/50 bg-ink/3'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${isCapturing ? 'bg-emerald-pro animate-pulse' : 'bg-ink/20'}`} />
          {roomStatus === 'ended' ? 'ENDED' : isCapturing ? (roomStatus ? 'MIC ON' : 'LIVE') : roomStatus ? 'MIC OFF' : 'READY'}
        </div>
      </div>

      {/* Buttons */}
      {roomStatus === 'live' ? (
        <div className="px-6 pb-6 space-y-4">
          <button
            type="button"
            onClick={isCapturing ? onStop : onStart}
            disabled={isConnecting}
            aria-pressed={isCapturing}
            className={`flex h-12 w-full items-center justify-center gap-2 rounded-xl text-sm font-bold text-white transition disabled:cursor-not-allowed disabled:opacity-40 ${isCapturing ? 'bg-crimson hover:bg-crimson/85' : 'bg-emerald-pro hover:bg-[#087b6c]'}`}
          >
            {isConnecting ? (connectionStatusLabel ?? 'Connecting microphone...') : isCapturing ? <><MicOff className="h-4 w-4" />Turn microphone off</> : <><Mic className="h-4 w-4" />Turn microphone on</>}
          </button>
          <div>
            <div className="flex items-center justify-between text-xs font-semibold text-ink-muted">
              <label htmlFor="room-mic-volume">Mic volume</label>
              <span>{microphoneGain}%</span>
            </div>
            <input
              id="room-mic-volume"
              type="range"
              min="0"
              max="200"
              step="5"
              value={microphoneGain}
              onChange={(event) => onMicrophoneGainChange?.(Number(event.target.value))}
              className="mt-2 w-full accent-emerald-pro"
              aria-label="Mic volume"
            />
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-ink/10" role="meter" aria-label="Mic input level" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(inputLevel * 100)}>
              <div className="h-full rounded-full bg-emerald-pro transition-[width] duration-100" style={{ width: `${Math.min(100, inputLevel * 240)}%` }} />
            </div>
            <p className="mt-1.5 text-[11px] text-ink/50">The level bar moves when your mic is receiving sound.</p>
          </div>
        </div>
      ) : roomStatus === 'ended' ? (
        <p className="px-6 pb-6 text-xs leading-relaxed text-ink-muted">Dismiss this transcript and create a new room to go live again.</p>
      ) : <div className="px-6 pb-6 space-y-3">
        <button
          onClick={onStart}
          disabled={isCapturing || isConnecting}
          className="w-full h-12 rounded-xl bg-emerald-pro text-white text-sm font-bold border border-emerald-pro hover:-translate-y-0.5 hover:bg-[#087b6c] hover:border-[#087b6c] disabled:opacity-30 disabled:cursor-not-allowed transition-all relative overflow-hidden group shadow-lg shadow-emerald-pro/15"
        >
          {isConnecting ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-px bg-paper/60 animate-[loading_1.2s_infinite_linear]" />
              {connectionStatusLabel ?? 'WAKING...'}
            </span>
          ) : <span className="flex items-center justify-center gap-2"><Mic className="h-4 w-4" />Start session</span>}
          <div className="absolute inset-0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700 bg-gradient-to-r from-transparent via-white/10 to-transparent pointer-events-none" />
        </button>

        <div className="flex items-start gap-2 px-1">
          <Info className="w-3 h-3 text-ink/40 shrink-0 mt-0.5" />
          <p className="text-xs leading-relaxed text-ink-muted" role="status" aria-live="polite">
            {isConnecting && (connectionStatusLabel === 'Starting backend' || connectionStatusLabel === 'Waiting for backend')
              ? 'The backend is waking from idle. This usually takes 30-60 seconds; temporary 503 responses are expected.'
              : 'Starting the session will ask for microphone access.'}
          </p>
        </div>

        <button
          onClick={onStop}
          disabled={!isCapturing || isConnecting}
          className="w-full h-12 rounded-xl border border-crimson/80 bg-white text-crimson text-sm font-bold hover:-translate-y-0.5 hover:bg-crimson hover:text-white disabled:opacity-25 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
        >
          <Square className="h-3.5 w-3.5 fill-current" />Stop session
        </button>
      </div>}

      {/* Audio Source */}
      <div className="px-6 pb-6 border-t border-[#dce5f2] pt-5 space-y-3">
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 text-xs font-bold text-ink-muted">
            <Mic className="w-3 h-3 text-emerald-pro/70" />
            Audio Source
          </label>
          <button
            onClick={onRefreshAudioInputDevices}
            disabled={deviceControlsDisabled}
            className="flex items-center gap-1.5 text-xs font-semibold text-ink-muted hover:text-emerald-pro transition-colors disabled:opacity-30"
          >
            <RefreshCcw className={`w-3 h-3 ${isConnecting ? 'animate-spin' : ''}`} />
            Scan
          </button>
        </div>

        <div className="relative">
          <select
            value={selectedDeviceId}
            onChange={(e) => onSelectedDeviceChange(e.target.value)}
            disabled={deviceControlsDisabled}
            className="w-full h-11 rounded-xl bg-white border border-ink/15 px-4 pr-10 font-mono text-[11px] text-ink/80 focus:border-emerald-pro focus:outline-none disabled:opacity-30 cursor-pointer hover:bg-emerald-pro/3 transition-colors appearance-none"
          >
            <option value="default">Default System Device</option>
            {audioInputDevices.map((d) => (
              <option key={d.deviceId} value={d.deviceId}>{d.label}</option>
            ))}
          </select>
          <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-ink/30">
            <svg className="w-3 h-3 fill-current" viewBox="0 0 20 20">
              <path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" />
            </svg>
          </div>
        </div>
      </div>

      {/* Purge */}
      <div className="px-6 pb-6 border-t border-[#dce5f2]">
        <button
          onClick={onClear}
          disabled={!canClear || isConnecting}
          className="mt-5 w-full h-9 rounded-xl border border-ink/15 font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-ink/40 hover:text-ink/70 hover:border-ink/30 transition-all disabled:opacity-20 disabled:cursor-not-allowed"
        >
          PURGE SESSION CACHE
        </button>
      </div>

      {/* Permission denied */}
      {permissionDenied && (
        <div className="mx-6 mb-6 flex items-center gap-3 border border-crimson/30 bg-crimson/5 p-4">
          <AlertTriangle className="w-4 h-4 text-crimson shrink-0" />
          <p className="font-mono text-[9px] text-crimson uppercase tracking-wider leading-relaxed font-bold">
            Hardware Blocked.<br />Check browser mic access.
          </p>
        </div>
      )}
    </div>
  );
}
