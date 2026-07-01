/**
 * Transcript export panel.
 */

import { useCallback, useMemo, useState } from 'react';
import type { Segment } from '../types';
import { exportTranscript, ExportError } from '../services/exportService';

interface ExportPanelProps {
  sessionId: string | null;
  segments: Segment[];
}

type ExportStatus =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'success'; downloadUrl: string; expiresAt: string }
  | { kind: 'error'; message: string };

export default function ExportPanel({ sessionId, segments }: ExportPanelProps) {
  const [status, setStatus] = useState<ExportStatus>({ kind: 'idle' });
  const finalizedSegments = useMemo(
    () => segments.filter((segment) => segment.isFinal),
    [segments],
  );

  const triggerExport = useCallback(async () => {
    if (!sessionId || finalizedSegments.length === 0) return;

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
  }, [finalizedSegments.length, segments, sessionId]);

  const isDisabled =
    !sessionId || finalizedSegments.length === 0 || status.kind === 'loading';

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-950">Export TXT</h2>
          <p className="mt-1 text-sm text-zinc-600">
            Create a presigned download link for finalized transcript lines.
          </p>
        </div>
        <span className="rounded-full bg-zinc-100 px-2.5 py-1 font-mono text-xs font-semibold text-zinc-700">
          {finalizedSegments.length}
        </span>
      </div>

      <button
        type="button"
        onClick={triggerExport}
        disabled={isDisabled}
        aria-busy={status.kind === 'loading'}
        className={[
          'mt-4 inline-flex min-h-11 w-full items-center justify-center rounded-lg px-4 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-400 focus:ring-offset-2',
          isDisabled
            ? 'cursor-not-allowed bg-zinc-100 text-zinc-400'
            : 'bg-zinc-950 text-white hover:bg-zinc-800',
        ].join(' ')}
      >
        {status.kind === 'loading' ? 'Exporting...' : 'Export TXT'}
      </button>

      {status.kind === 'success' && (
        <div
          role="status"
          aria-live="polite"
          className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
        >
          <p className="font-semibold">Export ready</p>
          <a
            href={status.downloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-2 block break-all font-mono text-xs text-emerald-900 underline"
          >
            {status.downloadUrl}
          </a>
          <p className="mt-2 text-xs text-emerald-700">
            Expires: {formatExpiry(status.expiresAt)}
          </p>
        </div>
      )}

      {status.kind === 'error' && (
        <div
          role="alert"
          aria-live="assertive"
          className="mt-4 rounded-md border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-semibold">Export failed</p>
              <p className="mt-1 break-words">{status.message}</p>
            </div>
            <button
              type="button"
              onClick={() => setStatus({ kind: 'idle' })}
              className="rounded px-2 py-1 text-xs font-semibold hover:bg-white/70 focus:outline-none focus:ring-2 focus:ring-rose-400"
            >
              Dismiss
            </button>
          </div>
          <button
            type="button"
            onClick={triggerExport}
            className="mt-3 rounded-md bg-rose-100 px-3 py-1.5 text-xs font-semibold text-rose-900 hover:bg-rose-200 focus:outline-none focus:ring-2 focus:ring-rose-400"
          >
            Retry
          </button>
        </div>
      )}
    </div>
  );
}

function formatExpiry(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
