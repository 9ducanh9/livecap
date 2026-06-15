/**
 * ControlPanel.tsx
 *
 * Start/stop capture controls, recording timer, and microphone input selection.
 */

import type { AudioInputDevice } from '../hooks/useAudioCapture';

interface ControlPanelProps {
  /** Whether capture is currently active. */
  isCapturing: boolean;
  /** Whether the WebSocket is in the process of connecting. */
  isConnecting: boolean;
  /** Optional label shown while startup is in progress. */
  connectionStatusLabel?: string | null;
  /** Whether microphone permission was denied. */
  permissionDenied: boolean;
  /** Current recording length in seconds. */
  recordingDurationSeconds: number;
  /** Maximum recording length in seconds. */
  maxSessionSeconds: number;
  /** Remaining recording time in seconds. */
  remainingSessionSeconds: number;
  /** Browser microphone input devices. */
  audioInputDevices: AudioInputDevice[];
  /** Selected microphone deviceId. */
  selectedDeviceId: string;
  /** Select the microphone for the next capture session. */
  onSelectedDeviceChange: (deviceId: string) => void;
  /** Refresh available microphone devices. */
  onRefreshAudioInputDevices: () => void;
  /** Start capture. */
  onStart: () => void;
  /** Stop capture. */
  onStop: () => void;
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
  onSelectedDeviceChange,
  onRefreshAudioInputDevices,
  onStart,
  onStop,
}: ControlPanelProps) {
  const isDisabled = isConnecting;
  const deviceControlsDisabled = isCapturing || isConnecting;

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex flex-wrap items-center justify-center gap-3">
        {isCapturing && (
          <span aria-label="Capture active" className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-red-500" />
          </span>
        )}

        {isCapturing && (
          <span className="font-mono text-sm font-medium tabular-nums text-slate-600">
            REC {formatDuration(recordingDurationSeconds)}
          </span>
        )}

        {isCapturing ? (
          <button
            onClick={onStop}
            disabled={isDisabled}
            aria-label="Stop capture"
            className={[
              'inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2',
              isDisabled
                ? 'cursor-not-allowed bg-slate-100 text-slate-400'
                : 'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500',
            ].join(' ')}
          >
            <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <rect x="4" y="4" width="12" height="12" rx="1" />
            </svg>
            Stop
          </button>
        ) : (
          <button
            onClick={onStart}
            disabled={isDisabled}
            aria-label={isConnecting ? connectionStatusLabel ?? 'Connecting...' : 'Start capture'}
            aria-busy={isConnecting}
            className={[
              'inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2',
              isDisabled
                ? 'cursor-not-allowed bg-slate-100 text-slate-400'
                : 'bg-indigo-600 text-white hover:bg-indigo-700 focus:ring-indigo-500',
            ].join(' ')}
          >
            {isConnecting ? (
              <>
                <svg
                  aria-hidden="true"
                  className="h-4 w-4 animate-spin"
                  viewBox="0 0 24 24"
                  fill="none"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                  />
                </svg>
                {connectionStatusLabel ?? 'Connecting...'}
              </>
            ) : (
              <>
                <svg
                  aria-hidden="true"
                  className="h-4 w-4"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8a1 1 0 10-2 0A5 5 0 015 8a1 1 0 00-2 0 7.001 7.001 0 006 6.93V17H6a1 1 0 100 2h8a1 1 0 100-2h-3v-2.07z"
                    clipRule="evenodd"
                  />
                </svg>
                Start
              </>
            )}
          </button>
        )}
      </div>

      <div className="flex w-full max-w-md flex-col gap-2 sm:flex-row sm:items-end">
        <label className="flex flex-1 flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Microphone
          <select
            value={selectedDeviceId}
            onChange={(event) => onSelectedDeviceChange(event.target.value)}
            disabled={deviceControlsDisabled}
            className={[
              'h-10 min-w-0 rounded-md border border-slate-300 bg-white px-3 text-sm font-normal normal-case tracking-normal text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200',
              deviceControlsDisabled ? 'cursor-not-allowed bg-slate-100 text-slate-500' : '',
            ].join(' ')}
          >
            <option value="default">Default microphone</option>
            {audioInputDevices.map((device) => (
              <option key={device.deviceId} value={device.deviceId}>
                {device.label}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          onClick={onRefreshAudioInputDevices}
          disabled={deviceControlsDisabled}
          aria-label="Refresh microphone list"
          title="Refresh microphone list"
          className={[
            'inline-flex h-10 items-center justify-center rounded-md border border-slate-300 bg-white px-3 text-slate-600 shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-200',
            deviceControlsDisabled
              ? 'cursor-not-allowed bg-slate-100 text-slate-400'
              : 'hover:bg-slate-50 hover:text-slate-900',
          ].join(' ')}
        >
          <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M4.5 7.5A5.5 5.5 0 0114 3.72V2.5a.75.75 0 011.5 0v3a.75.75 0 01-.75.75h-3a.75.75 0 010-1.5h1.41A4 4 0 106 8.5a.75.75 0 01-1.5 0v-1zm11 4A5.5 5.5 0 016 15.28v1.22a.75.75 0 01-1.5 0v-3a.75.75 0 01.75-.75h3a.75.75 0 010 1.5H6.84A4 4 0 0014 11.5a.75.75 0 011.5 0z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      </div>

      <p className="max-w-md text-center text-xs text-slate-500">
        Lưu ý: bấm Stop khi ghi âm xong để tránh phát sinh phí AWS Transcribe,
        Translate và S3 nếu có export transcript.
      </p>

      <p className="max-w-md text-center text-xs text-slate-500">
        Max session: {formatDuration(maxSessionSeconds)}
        {isCapturing ? ` - Remaining: ${formatDuration(remainingSessionSeconds)}` : ''}
      </p>

      {permissionDenied && (
        <p role="alert" aria-live="assertive" className="text-center text-sm text-red-600">
          Microphone access is required to capture audio
        </p>
      )}
    </div>
  );
}

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}
