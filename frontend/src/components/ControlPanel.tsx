/**
 * ControlPanel.tsx
 *
 * Start/stop capture controls and a visual capture-active indicator.
 *
 * Requirements: 1.1, 1.4, 1.5
 */

import type { LanguageMode } from '../types/index';

interface ControlPanelProps {
  /** Whether capture is currently active. */
  isCapturing: boolean;
  /** Whether the WebSocket is in the process of connecting (disable button). */
  isConnecting: boolean;
  /** Whether microphone permission was denied. */
  permissionDenied: boolean;
  languageMode: LanguageMode;
  languageModes: LanguageMode[];
  isLanguageModeDisabled: boolean;
  onLanguageModeChange: (mode: LanguageMode) => void;
  /** Start capture — opens the WebSocket, then begins audio capture. */
  onStart: () => void;
  /** Stop capture — stops audio and signals the backend. */
  onStop: () => void;
}

export default function ControlPanel({
  isCapturing,
  isConnecting,
  permissionDenied,
  languageMode,
  languageModes,
  isLanguageModeDisabled,
  onLanguageModeChange,
  onStart,
  onStop,
}: ControlPanelProps) {
  const isDisabled = isConnecting;

  return (
    <div className="flex flex-col items-center gap-3">
      <label className="flex items-center gap-2 text-sm font-medium text-slate-700">
        <span>Mode</span>
        <select
          value={`${languageMode.source}:${languageMode.target}`}
          disabled={isLanguageModeDisabled}
          onChange={(event) => {
            const selected = languageModes.find(
              (mode) => `${mode.source}:${mode.target}` === event.target.value
            );
            if (selected) onLanguageModeChange(selected);
          }}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500"
        >
          {languageModes.map((mode) => (
            <option
              key={`${mode.source}:${mode.target}`}
              value={`${mode.source}:${mode.target}`}
            >
              {mode.label}
            </option>
          ))}
        </select>
      </label>

      {/* Capture-active indicator + Start/Stop button row */}
      <div className="flex items-center gap-3">
        {/* Animated red dot — visible only while capturing */}
        {isCapturing && (
          <span
            aria-label="Capture active"
            className="relative flex h-3 w-3"
          >
            {/* Ping animation ring */}
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75" />
            {/* Solid dot */}
            <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500" />
          </span>
        )}

        {/* Start / Stop button */}
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
            {/* Stop square icon */}
            <svg aria-hidden="true" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
              <rect x="4" y="4" width="12" height="12" rx="1" />
            </svg>
            Stop
          </button>
        ) : (
          <button
            onClick={onStart}
            disabled={isDisabled}
            aria-label={isConnecting ? 'Connecting…' : 'Start capture'}
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
                {/* Spinner while connecting */}
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
                Connecting…
              </>
            ) : (
              <>
                {/* Microphone icon */}
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

      {/* Microphone permission denied message (Requirement 1.3) */}
      {permissionDenied && (
        <p
          role="alert"
          aria-live="assertive"
          className="text-sm text-red-600 text-center"
        >
          Microphone access is required to capture audio
        </p>
      )}
    </div>
  );
}
