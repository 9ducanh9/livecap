import type { AudioInputDevice } from '../hooks/useAudioCapture';
import { GlassPanel, ProButton, StatusBadge } from './ui';
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
    <GlassPanel className="p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-[0.2em] text-white/50">Processing Engine</h2>
          <p className="mt-2 text-[11px] leading-relaxed text-white/40 font-light">
            Connect to the ECS Fargate backend to start real-time captioning.
          </p>
        </div>
        <StatusBadge status={isCapturing ? 'active' : 'idle'} label={isCapturing ? 'LIVE' : 'READY'} />
      </div>

      <div className="mt-8 grid grid-cols-1 gap-4">
        <div className="space-y-4">
          <ProButton
            onClick={onStart}
            disabled={isCapturing || isConnecting}
            loading={isConnecting}
            variant="primary"
            className="w-full h-16 text-sm font-bold tracking-widest"
          >
            {isConnecting ? (connectionStatusLabel ?? 'WAKING...') : 'START STREAM'}
          </ProButton>

          <div className="flex items-start gap-2.5 px-1">
            <Info className="w-3.5 h-3.5 text-white/30 shrink-0 mt-0.5" />
            <p className="text-[9px] leading-relaxed text-white/30 uppercase tracking-[0.1em] font-medium">
              Start to grant microphone access. <br />
              <span className="text-crimson/80 font-bold">Transcription is usage-based.</span>
            </p>
          </div>
        </div>

        <ProButton
          onClick={onStop}
          disabled={!isCapturing || isConnecting}
          variant="outline"
          className="h-12 border-white/10 hover:border-crimson hover:text-crimson transition-all"
        >
          STOP PROCESSING
        </ProButton>
      </div>

      <div className="mt-10 space-y-4">
        <div className="flex items-center justify-between border-b border-white/5 pb-2">
          <label className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-white/40">
            <Mic className="w-3 h-3 text-crimson" />
            Audio Source
          </label>
          <button
            onClick={onRefreshAudioInputDevices}
            disabled={deviceControlsDisabled}
            className="group flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-widest text-white/30 hover:text-white transition-colors disabled:opacity-20"
            aria-label="Refresh audio devices"
          >
            <RefreshCcw className={`w-3 h-3 ${isConnecting ? 'animate-spin' : 'group-hover:rotate-180 transition-transform duration-500'}`} />
            Scan
          </button>
        </div>

        <div className="relative group">
          <select
            value={selectedDeviceId}
            onChange={(event) => onSelectedDeviceChange(event.target.value)}
            disabled={deviceControlsDisabled}
            className="w-full h-12 bg-white/5 border border-white/10 px-4 pr-10 font-mono text-[11px] text-white/80 focus:border-crimson/50 focus:outline-none disabled:opacity-30 cursor-pointer hover:bg-white/[0.08] transition-colors appearance-none outline-none"
          >
            <option value="default" className="bg-obsidian">Default System Device</option>
            {audioInputDevices.map((device) => (
              <option key={device.deviceId} value={device.deviceId} className="bg-obsidian">
                {device.label}
              </option>
            ))}
          </select>
          <div className="absolute right-4 top-1/2 -translate-y-1/2 pointer-events-none text-white/20 group-hover:text-white/40 transition-colors">
            <svg className="w-3 h-3 fill-current" viewBox="0 0 20 20"><path d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" /></svg>
          </div>
        </div>
      </div>

      <ProButton
        onClick={onClear}
        disabled={!canClear || isConnecting}
        variant="ghost"
        className="mt-10 w-full h-10 border border-white/5 text-[9px] font-bold text-white/20 hover:text-white hover:border-white/20 tracking-[0.2em]"
      >
        PURGE SESSION CACHE
      </ProButton>

      {permissionDenied && (
        <div className="mt-6 flex items-center gap-3 border border-crimson/30 bg-crimson/10 p-4">
          <AlertTriangle className="w-5 h-5 text-crimson shrink-0" />
          <p className="text-[10px] font-mono text-crimson uppercase tracking-wider leading-relaxed font-black">
            Hardware Blocked. <br /> Check browser mic access.
          </p>
        </div>
      )}
    </GlassPanel>
  );
}
