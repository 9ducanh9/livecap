import { useCallback, useMemo, useState } from 'react';
import type { Segment } from '../types';
import { exportTranscript, ExportError } from '../services/exportService';
import { GlassPanel, ProButton } from './ui';
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
    <GlassPanel className="p-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-xs font-bold uppercase tracking-widest text-white/40">Data Export</h2>
          <p className="mt-2 text-xs leading-relaxed text-white/60">
            Generate presigned S3 link for finalized lines.
          </p>
        </div>
        <div className="font-mono text-xs text-emerald-pro bg-emerald-pro/5 border border-emerald-pro/20 px-2 py-1">
          {finalizedSegments.length}
        </div>
      </div>

      <ProButton
        onClick={triggerExport}
        disabled={isDisabled}
        loading={status.kind === 'loading'}
        variant="secondary"
        className="mt-6 w-full h-12 flex gap-2"
      >
        <Download className="w-4 h-4" />
        Export TXT Session
      </ProButton>

      {status.kind === 'success' && (
        <div className="mt-6 border border-emerald-pro/20 bg-emerald-pro/5 p-4 font-mono">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-3 h-3 text-emerald-pro" />
            <p className="text-[10px] font-bold text-emerald-pro uppercase tracking-widest">Export Ready</p>
          </div>
          <a
            href={status.downloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-3 block break-all text-[10px] text-white underline opacity-60 hover:opacity-100"
          >
            {status.downloadUrl}
          </a>
          <p className="mt-3 text-[9px] text-white/40 uppercase">
            EXPIRES: {formatExpiry(status.expiresAt)}
          </p>
        </div>
      )}

      {status.kind === 'error' && (
        <div className="mt-6 border border-crimson/20 bg-crimson/5 p-4 font-mono">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <AlertCircle className="w-3 h-3 text-crimson" />
                <p className="text-[10px] font-bold text-crimson uppercase tracking-widest">Export Failed</p>
              </div>
              <p className="mt-2 text-[10px] text-white/70 leading-relaxed">{status.message}</p>
            </div>
          </div>
          <ProButton
            variant="ghost"
            onClick={triggerExport}
            className="mt-4 w-full h-9 border border-crimson/30 text-crimson text-[9px]"
          >
            Retry Export
          </ProButton>
        </div>
      )}
    </GlassPanel>
  );
}

function formatExpiry(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
