/**
 * Start/stop capture controls, recording timer, and microphone selection.
 */

import type { AudioInputDevice } from '../hooks/useAudioCapture';

interface ControlPanelProps {
  isCapturing: boolean;
  isConnecting: boolean;
  connectionStatusLabel?: string | null;
  permissionDenied: boolean;
  recordingDurationSeconds: number;
  maxSessionSeconds: number;
  remainingSessionSeconds: number;
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
  recordingDurationSeconds,
  maxSessionSeconds,
  remainingSessionSeconds,
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
  const progress =
    maxSessionSeconds > 0
      ? Math.min(100, (recordingDurationSeconds / maxSessionSeconds) * 100)
      : 0;

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-950">Controls</h2>
          <p className="mt-1 text-sm text-zinc-600">
            Start opens the backend stream before microphone capture begins.
          </p>
        </div>
        <LiveBadge isLive={isCapturing} />
      </div>

      <div className="mt-5 rounded-lg border border-zinc-200 bg-zinc-50 p-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
              Timer
            </div>
            <div className="mt-1 font-mono text-3xl font-semibold tabular-nums text-zinc-950">
              {formatDuration(recordingDurationSeconds)}
            </div>
          </div>
          <div className="text-right text-xs text-zinc-500">
            <div>Max {formatDuration(maxSessionSeconds)}</div>
            <div>
              {isCapturing
                ? `${formatDuration(remainingSessionSeconds)} left`
                : 'Ready'}
            </div>
          </div>
        </div>

        <div className="mt-4 h-2 overflow-hidden rounded-full bg-zinc-200">
          <div
            className="h-full rounded-full bg-emerald-500 transition-[width]"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-3">
        <button
          type="button"
          onClick={onStart}
          disabled={isCapturing || isConnecting}
          aria-busy={isConnecting}
          className={[
            'inline-flex min-h-12 items-center justify-center rounded-lg px-4 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2',
            isCapturing || isConnecting
              ? 'cursor-not-allowed bg-zinc-100 text-zinc-400'
              : 'bg-emerald-600 text-white hover:bg-emerald-700',
          ].join(' ')}
        >
          {isConnecting ? connectionStatusLabel ?? 'Starting' : 'Start'}
        </button>

        <button
          type="button"
          onClick={onStop}
          disabled={!isCapturing || isConnecting}
          className={[
            'inline-flex min-h-12 items-center justify-center rounded-lg px-4 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-rose-400 focus:ring-offset-2',
            !isCapturing || isConnecting
              ? 'cursor-not-allowed border border-zinc-200 bg-zinc-50 text-zinc-400'
              : 'bg-rose-600 text-white hover:bg-rose-700',
          ].join(' ')}
        >
          Stop
        </button>
      </div>

      <button
        type="button"
        onClick={onClear}
        disabled={!canClear || isConnecting}
        className={[
          'mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-lg border px-4 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-zinc-300 focus:ring-offset-2',
          !canClear || isConnecting
            ? 'cursor-not-allowed border-zinc-200 bg-zinc-50 text-zinc-400'
            : 'border-zinc-300 bg-white text-zinc-800 hover:bg-zinc-50',
        ].join(' ')}
      >
        Clear transcript
      </button>

      <div className="mt-5 space-y-2">
        <label className="block text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Microphone
        </label>
        <div className="flex gap-2">
          <select
            value={selectedDeviceId}
            onChange={(event) => onSelectedDeviceChange(event.target.value)}
            disabled={deviceControlsDisabled}
            className={[
              'h-11 min-w-0 flex-1 rounded-md border border-zinc-300 bg-white px-3 text-sm text-zinc-900 shadow-sm focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-100',
              deviceControlsDisabled ? 'cursor-not-allowed bg-zinc-100 text-zinc-500' : '',
            ].join(' ')}
          >
            <option value="default">Default microphone</option>
            {audioInputDevices.map((device) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label}
              </option>
            ))}
          </select>

          <button
            type="button"
            onClick={onRefreshAudioInputDevices}
            disabled={deviceControlsDisabled}
            title="Refresh microphone list"
            aria-label="Refresh microphone list"
            className={[
              'inline-flex h-11 w-11 items-center justify-center rounded-md border border-zinc-300 bg-white text-sm font-semibold text-zinc-700 shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-100',
              deviceControlsDisabled
                ? 'cursor-not-allowed bg-zinc-100 text-zinc-400'
                : 'hover:bg-zinc-50 hover:text-zinc-950',
            ].join(' ')}
          >
            R
          </button>
        </div>
      </div>

      <div className="mt-5 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-800">
        Usage note: stop the session when finished. Transcribe and Translate are
        usage-based, and transcript export writes to S3.
      </div>

      {permissionDenied && (
        <p role="alert" aria-live="assertive" className="mt-3 text-sm text-rose-700">
          Microphone access is required to capture audio.
        </p>
      )}
    </div>
  );
}

function LiveBadge({ isLive }: { isLive: boolean }) {
  return (
    <span
      className={[
        'inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-semibold',
        isLive
          ? 'border-rose-200 bg-rose-50 text-rose-700'
          : 'border-zinc-200 bg-zinc-100 text-zinc-600',
      ].join(' ')}
    >
      <span
        className={[
          'h-1.5 w-1.5 rounded-full',
          isLive ? 'bg-rose-500' : 'bg-zinc-400',
        ].join(' ')}
      />
      {isLive ? 'Live' : 'Idle'}
    </span>
  );
}

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds
    .toString()
    .padStart(2, '0')}`;
}
