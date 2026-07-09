import { useCallback, useMemo, useState } from 'react';
import type { Segment } from '../types';
import { exportTranscript, ExportError } from '../services/exportService';
import { Download, AlertCircle, CheckCircle2 } from 'lucide-react';

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
  const finalizedSegments = useMemo(() => segments.filter((s) => s.isFinal), [segments]);

  const triggerExport = useCallback(async () => {
    if (!sessionId || finalizedSegments.length === 0) return;
    setStatus({ kind: 'loading' });
    try {
      const result = await exportTranscript(sessionId, segments);
      triggerTranscriptDownload(result.download_url);
      setStatus({ kind: 'success', downloadUrl: result.download_url, expiresAt: result.expires_at });
    } catch (err) {
      const message = err instanceof ExportError ? err.message : 'An unexpected error occurred during export.';
      setStatus({ kind: 'error', message });
    }
  }, [finalizedSegments.length, segments, sessionId]);

  const isDisabled = !sessionId || finalizedSegments.length === 0 || status.kind === 'loading';

  return (
    <div className="border-t border-ink/10">
      {/* Header */}
      <div className="px-6 py-4 border-b border-ink/10 flex items-center justify-between">
        <p className="font-mono text-[9px] font-bold uppercase tracking-[0.35em] text-ink/60">// Data_Export</p>
        <div className="font-mono text-[10px] font-bold text-emerald-pro border border-emerald-pro/25 bg-emerald-pro/5 px-2 py-0.5">
          {finalizedSegments.length}
        </div>
      </div>

      <div className="px-6 py-5 space-y-4">
        <p className="font-mono text-[10px] leading-relaxed text-ink/60 uppercase tracking-wider">
          Download finalized lines as a TXT transcript.
        </p>

        <button
          onClick={triggerExport}
          disabled={isDisabled}
          className="w-full h-11 border border-ink/20 font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-ink/60 hover:border-emerald-pro/50 hover:text-emerald-pro hover:bg-emerald-pro/3 transition-all disabled:opacity-30 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          {status.kind === 'loading' ? (
            <>
              <span className="w-3 h-px bg-ink/30 animate-[loading_1.2s_infinite_linear]" />
              EXPORTING...
            </>
          ) : (
            <>
              <Download className="w-3.5 h-3.5" />
              EXPORT TXT SESSION
            </>
          )}
        </button>

        {status.kind === 'success' && (
          <div className="border border-emerald-pro/25 bg-emerald-pro/5 p-4 font-mono space-y-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-3 h-3 text-emerald-pro" />
              <p className="text-[9px] font-bold text-emerald-pro uppercase tracking-widest">Download Started</p>
            </div>
            <p className="text-[9px] text-ink/40 leading-relaxed">
              If the browser blocks the automatic download, use the fallback link below.
            </p>
            <a
              href={status.downloadUrl}
              className="inline-flex h-8 items-center border border-emerald-pro/25 px-3 text-[9px] font-bold uppercase tracking-widest text-emerald-pro hover:bg-emerald-pro/5 transition-colors"
            >
              Download TXT
            </a>
            <p className="text-[9px] text-ink/25 uppercase tracking-widest">
              EXPIRES: {formatExpiry(status.expiresAt)}
            </p>
          </div>
        )}

        {status.kind === 'error' && (
          <div className="border border-crimson/25 bg-crimson/5 p-4 font-mono space-y-3">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-3 h-3 text-crimson" />
              <p className="text-[9px] font-bold text-crimson uppercase tracking-widest">Export Failed</p>
            </div>
            <p className="text-[9px] text-ink/40 leading-relaxed">{status.message}</p>
            <button
              onClick={triggerExport}
              className="w-full h-8 border border-crimson/25 font-mono text-[9px] font-bold text-crimson uppercase tracking-widest hover:bg-crimson/5 transition-colors"
            >
              RETRY EXPORT
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function formatExpiry(iso: string): string {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function triggerTranscriptDownload(downloadUrl: string): void {
  const anchor = document.createElement('a');
  anchor.href = downloadUrl;
  anchor.download = 'livecap-transcript.txt';
  anchor.rel = 'noopener noreferrer';
  anchor.style.display = 'none';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}
