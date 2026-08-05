import { useEffect, useRef } from 'react';
import type { Segment } from '../types/index';
import { MessageSquare, MicOff, Info, Sparkles } from 'lucide-react';

interface CaptionDisplayProps {
  segments: Segment[];
  currentPartial: Segment | null;
  isCapturing?: boolean;
  isConnecting?: boolean;
  permissionDenied?: boolean;
}

const LISTENING_PLACEHOLDER: Segment = {
  segmentId: 'listening-placeholder',
  speakerLabel: '',
  textVi: '',
  textEn: '',
  spokenLanguage: 'vi',
  isFinal: false,
  timestampStart: 0,
  timestampEnd: 0,
};

export default function CaptionDisplay({
  segments,
  currentPartial,
  isCapturing,
  isConnecting,
  permissionDenied,
}: CaptionDisplayProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const liveRow = currentPartial ?? (isCapturing ? LISTENING_PLACEHOLDER : null);
  const hasContent = segments.length > 0 || Boolean(liveRow);

  // Every caption feed we looked at (Meet, Zoom, Teams) auto-follows the
  // newest line instead of leaving the reader to scroll manually.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [segments.length, liveRow?.textVi, liveRow?.textEn]);

  return (
    <div className="flex h-full flex-col overflow-hidden gap-3">
      <div
        className="flex-1 overflow-y-auto custom-scrollbar"
        ref={scrollRef}
      >
        {hasContent && (
          <div className="overflow-hidden rounded-2xl border border-ink/8 bg-white/55 divide-y divide-ink/8">
            <div className="grid lg:grid-cols-2 lg:divide-x lg:divide-ink/6 bg-ink/[0.02]">
              <div className="px-5 py-2 font-mono text-[8px] font-bold uppercase tracking-[0.3em] text-ink/40">
                Vietnamese
              </div>
              <div className="px-5 py-2 font-mono text-[8px] font-bold uppercase tracking-[0.3em] text-emerald-pro/70">
                English
              </div>
            </div>

            {segments.length > 0 && (
              <div aria-label="Finalized transcript" className="divide-y divide-ink/8">
                {segments.map((segment) => (
                  <TranscriptRow key={segment.segmentId} segment={segment} />
                ))}
              </div>
            )}

            {liveRow && (
              <div aria-label="Live captions" className="bg-[#effbf8]/70">
                <TranscriptRow segment={liveRow} isPartial isCapturing={isCapturing} />
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {!hasContent && !permissionDenied && !isConnecting && (
          <div className="flex flex-1 flex-col items-center justify-center text-center p-10 min-h-[400px]">
            <div className="relative mb-8 grid h-20 w-20 place-items-center rounded-[1.65rem] bg-gradient-to-br from-[#e2fbf5] to-[#dcecff] shadow-[0_16px_32px_rgba(10,156,136,0.12)]">
              <MessageSquare className="h-8 w-8 text-emerald-pro" />
              <span className="absolute -right-1 -top-1 grid h-7 w-7 place-items-center rounded-full border-2 border-white bg-ink text-[#7ee5d0]"><Sparkles className="h-3.5 w-3.5" /></span>
            </div>
            <div className="max-w-md space-y-4">
              <h3 className="font-instrument text-4xl font-bold tracking-[-0.06em] text-ink">Your conversation, clearly.</h3>
              <p className="text-base leading-7 text-ink-muted">
                Start a session and your live captions will appear here.
              </p>
              <div className="mx-auto mt-8 flex h-12 items-end justify-center gap-1.5" aria-hidden="true">
                {[12, 22, 34, 18, 44, 29, 16, 38, 24, 32, 14, 20].map((height, index) => <span key={index} className="w-1.5 rounded-full bg-emerald-pro/55" style={{ height }} />)}
              </div>
              <p className="pt-3 text-sm font-medium text-emerald-pro">Speak naturally. We’ll keep up.</p>
            </div>
          </div>
        )}

        {/* Permission denied */}
        {permissionDenied && (
          <div className="border border-crimson/25 bg-crimson/5 p-12 text-center space-y-5">
            <MicOff className="w-8 h-8 text-crimson mx-auto animate-bounce" />
            <div className="space-y-2">
              <h4 className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-crimson">Hardware Access Error</h4>
              <p className="font-mono text-[10px] text-ink/60 max-w-xs mx-auto leading-relaxed uppercase tracking-wider">
                Browser blocked microphone. Allow access in address bar and refresh.
              </p>
            </div>
          </div>
        )}

        {/* Connecting */}
        {isConnecting && !hasContent && (
          <div className="flex flex-col items-center justify-center py-32 space-y-8">
            <div className="w-24 h-px bg-ink/10 overflow-hidden relative">
              <div className="absolute inset-y-0 w-1/2 bg-crimson animate-[loading_1.5s_infinite_linear]" />
            </div>
            <p className="font-mono text-[9px] font-bold uppercase tracking-[0.5em] text-ink/50 animate-pulse">
              SYNCING_NODE_STREAMS...
            </p>
          </div>
        )}
      </div>

      {/* Footer status */}
      <div className="flex items-center gap-4 py-3 border-t border-ink/8 mt-auto">
        <div className="h-px flex-1 bg-ink/5" />
        <div className="flex items-center gap-2">
          <Info className="w-3 h-3 text-ink/20" />
          <span className="font-mono text-[9px] font-bold uppercase tracking-[0.3em] text-ink/40">
            {isCapturing ? 'GATEWAY: LINKED' : 'GATEWAY: WAITING'}
          </span>
        </div>
        <div className="h-px flex-1 bg-ink/5" />
      </div>
    </div>
  );
}

/**
 * One caption line: a finalized segment or the current in-progress one,
 * sharing the same layout so a line doesn't jump style the moment it
 * finalizes — only the accent (pulsing dot vs. timestamp) and text weight
 * change. Matches the row-per-utterance pattern common to Meet/Zoom/Teams,
 * instead of concatenating every segment into one growing paragraph.
 */
function TranscriptRow({
  segment,
  isPartial = false,
  isCapturing = false,
}: {
  segment: Segment;
  isPartial?: boolean;
  isCapturing?: boolean;
}) {
  const vietnameseText = segment.textVi.trim();
  const englishText = segment.textEn.trim();
  const viFallback = isPartial ? (isCapturing ? 'Đang lắng nghe...' : 'Bắt đầu để ghi âm') : '...';
  const enFallback = isPartial ? (vietnameseText ? 'Translating...' : 'Waiting for speech...') : '...';

  return (
    <section
      aria-label={isPartial ? undefined : 'Transcript line'}
      className="transition-colors duration-300"
    >
      <div className="flex items-center justify-between px-5 pt-2.5 font-mono">
        <span className="text-[9px] font-bold uppercase tracking-[0.25em] text-ink/40">
          {segment.speakerLabel || (isPartial ? 'LIVE' : '')}
        </span>
        {isPartial ? (
          <span className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-[0.25em] text-emerald-pro/70">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-pro animate-pulse" />
            Live
          </span>
        ) : (
          <span className="text-[9px] tabular-nums text-ink/40">
            {formatTimestamp(segment.timestampStart)}
          </span>
        )}
      </div>
      <div className="grid lg:grid-cols-2 lg:divide-x lg:divide-ink/6">
        <div className="min-w-0 px-5 py-2.5">
          <p
            className={`break-words whitespace-normal text-sm font-medium leading-relaxed tracking-tight ${
              vietnameseText ? 'text-ink' : 'text-ink/35'
            }`}
          >
            {vietnameseText || viFallback}
          </p>
        </div>
        <div className="min-w-0 px-5 py-2.5">
          <p
            className={`break-words whitespace-normal text-sm font-medium leading-relaxed tracking-tight ${
              englishText ? 'text-emerald-pro' : 'text-emerald-pro/35'
            }`}
          >
            {englishText || enFallback}
          </p>
        </div>
      </div>
    </section>
  );
}

function formatTimestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
  const totalSeconds = Math.floor(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const remainder = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${remainder.toString().padStart(2, '0')}`;
}
