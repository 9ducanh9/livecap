/**
 * ExportPanel.tsx
 *
 * Triggers transcript export, displays the returned Download_Link, and shows
 * an error toast with retry on export failure.
 *
 * Requirements: 7.1, 7.2, 7.3, 8.5, 9.2
 */

import { useState, useCallback } from 'react';
import type { Segment } from '../types';
import { exportTranscript, ExportError } from '../services/exportService';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ExportPanelProps {
  /** The Session_ID returned by the backend. Required to call the export API. */
  sessionId: string | null;
  /** All segments in the current session; non-final ones are filtered out internally. */
  segments: Segment[];
}

type ExportStatus =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'success'; downloadUrl: string; expiresAt: string }
  | { kind: 'error'; message: string };

// ---------------------------------------------------------------------------
// Toast helper (inline, no external library dependency)
// ---------------------------------------------------------------------------

interface ErrorToastProps {
  message: string;
  onRetry: () => void;
  onDismiss: () => void;
}

function ErrorToast({ message, onRetry, onDismiss }: ErrorToastProps) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800 shadow-sm"
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

      <div className="flex-1 text-sm">
        <p className="font-medium">Export failed</p>
        <p className="mt-0.5 text-red-700">{message}</p>
      </div>

      <div className="flex gap-2">
        <button
          onClick={onRetry}
          className="rounded bg-red-100 px-2.5 py-1 text-xs font-medium text-red-800 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-red-400"
        >
          Retry
        </button>
        <button
          onClick={onDismiss}
          aria-label="Dismiss error"
          className="rounded bg-red-100 px-2.5 py-1 text-xs font-medium text-red-800 hover:bg-red-200 focus:outline-none focus:ring-2 focus:ring-red-400"
        >
          ✕
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ExportPanel
// ---------------------------------------------------------------------------

export default function ExportPanel({ sessionId, segments }: ExportPanelProps) {
  const [status, setStatus] = useState<ExportStatus>({ kind: 'idle' });

  const triggerExport = useCallback(async () => {
    if (!sessionId) return;

    setStatus({ kind: 'loading' });

    try {
      const result = await exportTranscript(sessionId, segments);
      setStatus({
        kind: 'success',
        downloadUrl: result.download_url,
        expiresAt: result.expires_at,
      });
    } catch (err) {
      const message =
        err instanceof ExportError
          ? err.message
          : 'An unexpected error occurred during export.';
      setStatus({ kind: 'error', message });
    }
  }, [sessionId, segments]);

  const handleRetry = useCallback(() => {
    triggerExport();
  }, [triggerExport]);

  const handleDismiss = useCallback(() => {
    setStatus({ kind: 'idle' });
  }, []);

  const isDisabled = !sessionId || status.kind === 'loading';

  // Format the expiry date for display.
  function formatExpiry(iso: string): string {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  return (
    <div className="space-y-3">
      {/* Export button */}
      <button
        onClick={triggerExport}
        disabled={isDisabled}
        aria-busy={status.kind === 'loading'}
        className={[
          'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2',
          isDisabled
            ? 'cursor-not-allowed bg-slate-100 text-slate-400'
            : 'bg-indigo-600 text-white hover:bg-indigo-700 focus:ring-indigo-500',
        ].join(' ')}
      >
        {status.kind === 'loading' ? (
          <>
            {/* Spinner */}
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
            Exporting…
          </>
        ) : (
          <>
            {/* Download icon */}
            <svg
              aria-hidden="true"
              className="h-4 w-4"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z"
                clipRule="evenodd"
              />
            </svg>
            Export Transcript
          </>
        )}
      </button>

      {/* Success: download link */}
      {status.kind === 'success' && (
        <div
          role="status"
          aria-live="polite"
          className="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-800"
        >
          <p className="font-medium">Transcript exported successfully.</p>
          <p className="mt-1">
            <a
              href={status.downloadUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="break-all font-mono text-indigo-700 underline hover:text-indigo-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {status.downloadUrl}
            </a>
          </p>
          <p className="mt-1 text-green-600 text-xs">
            Link expires: {formatExpiry(status.expiresAt)}
          </p>
        </div>
      )}

      {/* Error toast with retry */}
      {status.kind === 'error' && (
        <ErrorToast
          message={status.message}
          onRetry={handleRetry}
          onDismiss={handleDismiss}
        />
      )}
    </div>
  );
}
