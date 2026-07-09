import type { AudioInputDevice } from '../hooks/useAudioCapture';
import { Mic, RefreshCcw, Info, AlertTriangle } from 'lucide-react';

interface ControlPanelProps {
  isCapturing: boolean;
  isConnecting: boolean;
  connectionStatusLabel?: string | null;
  permissionDenied: boolean;
  audioInputDevices: AudioInputDevice[];
  selectedDeviceId: string;
  canClear: boolean;
  onSelectedDeviceChange: (deviceId: string) => void;
  onRefreshAudioInputDevices: () => void;
  onStart: () => void;
  onStop: () => void;
  onClear: () => void;
}

export default function ControlPanel({
  isCapturing,
  isConnecting,
  connectionStatusLabel,
  permissionDenied,
  audioInputDevices,
  selectedDeviceId,
  canClear,
  onSelectedDeviceChange,
  onRefreshAudioInputDevices,
  onStart,
  onStop,
  onClear,
}: ControlPanelProps) {
  const deviceControlsDisabled = isCapturing || isConnecting;

  return (
    <div className="border-b border-ink/10">
      {/* Engine header */}
      <div className="px-6 pt-6 pb-4 flex items-start justify-between">
        <div>
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.35em] text-ink/60">// Processing_Engine</p>
          <p className="mt-2 text-[11px] leading-relaxed text-ink/60 font-light">
            Connect to ECS Fargate backend to start captioning.
          </p>
        </div>
        <div className={`flex items-center gap-1.5 font-mono text-[9px] font-bold uppercase tracking-widest border px-2 py-1 ${
          isCapturing
            ? 'border-emerald-pro/30 text-emerald-pro bg-emerald-pro/5'
            : 'border-ink/20 text-ink/50 bg-ink/3'
        }`}>
          <span className={`w-1.5 h-1.5 rounded-full ${isCapturing ? 'bg-emerald-pro animate-pulse' : 'bg-ink/20'}`} />
          {isCapturing ? 'LIVE' : 'READY'}
        </div>
      </div>

      {/* Buttons */}
      <div className="px-6 pb-6 space-y-3">
        <button
          onClick={onStart}
          disabled={isCapturing || isConnecting}
          className="w-full h-14 bg-ink text-paper font-mono text-[11px] font-bold uppercase tracking-[0.25em] border border-ink hover:bg-crimson hover:border-crimson disabled:opacity-30 disabled:cursor-not-allowed transition-all relative overflow-hidden group"
        >
          {isConnecting ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-px bg-paper/60 animate-[loading_1.2s_infinite_linear]" />
              {connectionStatusLabel ?? 'WAKING...'}
            </span>
          ) : 'START STREAM'}
          <div className="absolute inset-0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700 bg-gradient-to-r from-transparent via-white/10 to-transparent pointer-events-none" />
        </button>

        <div className="flex items-start gap-2 px-1">
          <Info className="w-3 h-3 text-ink/40 shrink-0 mt-0.5" />
          <p className="text-[9px] leading-relaxed text-ink/50 uppercase tracking-wider font-mono">
            Start to grant microphone access.{' '}
            <span className="text-crimson font-bold">Transcription is usage-based.</span>
          </p>
        </div>

        <button
          onClick={onStop}
          disabled={!isCapturing || isConnecting}
          className="w-full h-11 border border-ink/15 text-ink/40 font-mono text-[10px] font-bold uppercase tracking-[0.2em] hover:border-crimson/50 hover:text-crimson transition-all disabled:opacity-20 disabled:cursor-not-allowed"
        >
          STOP PROCESSING
        </button>
      </div>

      {/* Audio Source */}
      <div className="px-6 pb-6 border-t border-ink/10 pt-5 space-y-3">
        <div className="flex items-center justify-between">
          <label className="flex items-center gap-2 font-mono text-[9px] font-bold uppercase tracking-widest text-ink/60">
            <Mic className="w-3 h-3 text-crimson/70" />
            Audio Source
          </label>
          <button
            onClick={onRefreshAudioInputDevices}
            disabled={deviceControlsDisabled}
            className="flex items-center gap-1.5 font-mono text-[9px] font-bold uppercase tracking-widest text-ink/40 hover:text-ink/80 transition-colors disabled:opacity-30"
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
            className="w-full h-11 bg-white border border-ink/20 px-4 pr-10 font-mono text-[11px] text-ink/80 focus:border-ink/50 focus:outline-none disabled:opacity-30 cursor-pointer hover:bg-ink/3 transition-colors appearance-none"
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
      <div className="px-6 pb-6 border-t border-ink/5">
        <button
          onClick={onClear}
          disabled={!canClear || isConnecting}
          className="mt-5 w-full h-9 border border-ink/15 font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-ink/40 hover:text-ink/70 hover:border-ink/30 transition-all disabled:opacity-20 disabled:cursor-not-allowed"
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
