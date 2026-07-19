import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { AlertTriangle, Download, History, LoaderCircle, LogOut, RefreshCw } from 'lucide-react';
import {
  getHistoryDownloadUrl,
  getTranscriptHistory,
  HistoryError,
  type TranscriptHistoryItem,
} from '../services/historyService';
import { beginSignIn, signOut } from '../services/authService';

type Status = 'idle' | 'loading' | 'error-auth' | 'error-network';

/** Illustrations generated in Canva (LiveCap emerald/ink palette). Drop the
 * exported PNGs at these paths under frontend/public/illustrations/ — the
 * panel degrades gracefully to an icon if a file is missing. */
const EMPTY_ILLUSTRATION = '/illustrations/history-empty.png';
const SESSION_EXPIRED_ILLUSTRATION = '/illustrations/history-session-expired.png';

export default function TranscriptHistoryPanel() {
  const [items, setItems] = useState<TranscriptHistoryItem[]>([]);
  const [status, setStatus] = useState<Status>('idle');

  const load = useCallback(async () => {
    setStatus('loading');
    try {
      setItems(await getTranscriptHistory());
      setStatus('idle');
    } catch (error) {
      setStatus(error instanceof HistoryError && error.kind === 'auth' ? 'error-auth' : 'error-network');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const download = useCallback(async (historyId: string) => {
    try {
      const url = await getHistoryDownloadUrl(historyId);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'livecap-transcript.txt';
      anchor.rel = 'noopener noreferrer';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } catch (error) {
      setStatus(error instanceof HistoryError && error.kind === 'auth' ? 'error-auth' : 'error-network');
    }
  }, []);

  return (
    <aside className="border-t border-[#dce5f2] px-6 py-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-emerald-pro" />
          <p className="text-sm font-bold text-ink">Transcript history</p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          aria-label="Refresh transcript history"
          className="text-ink-muted hover:text-emerald-pro"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${status === 'loading' ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="mt-4">
        {status === 'loading' && (
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            <LoaderCircle className="h-3 w-3 animate-spin" /> Loading history
          </div>
        )}

        {status === 'error-auth' && (
          <EmptyState
            illustration={SESSION_EXPIRED_ILLUSTRATION}
            fallbackIcon={<AlertTriangle className="h-6 w-6 text-crimson" />}
            title="Your session has expired"
            subtitle="Sign in again to see your saved transcripts."
            actionLabel="Sign in again"
            onAction={() => void beginSignIn()}
          />
        )}

        {status === 'error-network' && (
          <EmptyState
            illustration={undefined}
            fallbackIcon={<AlertTriangle className="h-6 w-6 text-crimson" />}
            title="Couldn't load your history"
            subtitle="Check your connection and try again."
            actionLabel="Try again"
            onAction={() => void load()}
          />
        )}

        {status === 'idle' && items.length === 0 && (
          <EmptyState
            illustration={EMPTY_ILLUSTRATION}
            fallbackIcon={<History className="h-6 w-6 text-emerald-pro" />}
            title="No transcripts yet"
            subtitle="Exported transcripts will appear here for 14 days."
          />
        )}

        {status === 'idle' && items.length > 0 && (
          <div className="space-y-2">
            {items.map((item) => (
              <div
                key={item.history_id}
                className="flex items-center justify-between gap-2 rounded-lg border border-[#dce5f2] p-3"
              >
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-ink">{new Date(item.created_at).toLocaleString()}</p>
                  <p className="mt-0.5 text-[11px] text-ink-muted">{item.segment_count} captions</p>
                </div>
                <button
                  type="button"
                  onClick={() => void download(item.history_id)}
                  className="shrink-0 text-emerald-pro hover:opacity-70"
                  aria-label="Download transcript"
                >
                  <Download className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={signOut}
        className="mt-4 flex items-center gap-2 text-xs font-semibold text-ink-muted hover:text-crimson"
      >
        <LogOut className="h-3.5 w-3.5" /> Sign out
      </button>
    </aside>
  );
}

interface EmptyStateProps {
  illustration: string | undefined;
  fallbackIcon: ReactNode;
  title: string;
  subtitle: string;
  actionLabel?: string;
  onAction?: () => void;
}

/** Centered graphic + copy for empty/error states, with an optional retry
 * or sign-in CTA. Falls back to a plain icon if the illustration is missing
 * (e.g. before the Canva-exported PNG has been dropped into public/). */
function EmptyState({ illustration, fallbackIcon, title, subtitle, actionLabel, onAction }: EmptyStateProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = illustration && !imageFailed;

  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-[#dce5f2] px-4 py-6 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-emerald-pro/5">
        {showImage ? (
          <img
            src={illustration}
            alt=""
            className="h-14 w-14 object-contain"
            onError={() => setImageFailed(true)}
          />
        ) : (
          fallbackIcon
        )}
      </div>
      <p className="mt-3 text-xs font-bold text-ink">{title}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">{subtitle}</p>
      {actionLabel && onAction && (
        <button
          type="button"
          onClick={onAction}
          className="mt-3 rounded-lg border border-emerald-pro/30 px-3 py-1.5 text-[11px] font-bold text-emerald-pro hover:bg-emerald-pro/5"
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
