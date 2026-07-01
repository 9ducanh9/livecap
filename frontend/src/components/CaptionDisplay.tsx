import type { Segment } from '../types/index';
import { useAutoScroll } from '../hooks/useAutoScroll';

interface CaptionDisplayProps {
  segments: Segment[];
  currentPartial: Segment | null;
}

export default function CaptionDisplay({
  segments,
  currentPartial,
}: CaptionDisplayProps) {
  const scrollDependency = `${segments.length}:${currentPartial?.segmentId ?? ''}:${currentPartial?.textVi ?? ''}:${currentPartial?.textEn ?? ''}`;
  const { containerRef, isAtBottom } = useAutoScroll(scrollDependency);

  return (
    <section
      aria-label="Bilingual captions"
      className="flex h-full min-h-[620px] flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 bg-white px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-zinc-950">Live Caption</h2>
          <p className="mt-0.5 text-sm text-zinc-500">
            Finalized lines are appended. The current partial is shown as a live draft.
          </p>
        </div>
        <span className="rounded-full bg-zinc-100 px-3 py-1 font-mono text-xs font-semibold text-zinc-700">
          {segments.length} finalized
        </span>
      </div>

      <div className="grid border-b border-zinc-200 bg-zinc-50 text-xs font-semibold uppercase tracking-wide text-zinc-500 md:grid-cols-2">
        <div className="border-b border-zinc-200 px-4 py-3 md:border-b-0 md:border-r">
          Original
        </div>
        <div className="px-4 py-3">Translated</div>
      </div>

      {!isAtBottom && (segments.length > 0 || currentPartial !== null) && (
        <div
          className="border-b border-emerald-100 bg-emerald-50 px-4 py-2 text-center text-xs font-semibold text-emerald-700"
          aria-live="polite"
          aria-atomic="true"
        >
          New captions below
        </div>
      )}

      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto bg-white"
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        aria-label="Caption log"
      >
        {segments.length === 0 && currentPartial === null ? (
          <EmptyState />
        ) : (
          <>
            {segments.map((segment) => (
              <SegmentRow key={segment.segmentId} segment={segment} />
            ))}
            {currentPartial && (
              <SegmentRow
                key={`partial-${currentPartial.segmentId}`}
                segment={currentPartial}
                isPartial
              />
            )}
          </>
        )}
      </div>
    </section>
  );
}

function SegmentRow({
  segment,
  isPartial = false,
}: {
  segment: Segment;
  isPartial?: boolean;
}) {
  const originalText =
    segment.spokenLanguage === 'vi' ? segment.textVi : segment.textEn;
  const translatedText =
    segment.spokenLanguage === 'vi' ? segment.textEn : segment.textVi;
  const originalLanguage =
    segment.spokenLanguage === 'vi' ? 'Vietnamese' : 'English';
  const translatedLanguage =
    segment.spokenLanguage === 'vi' ? 'English' : 'Vietnamese';

  return (
    <article
      className={`grid border-b border-zinc-100 last:border-b-0 md:grid-cols-2 ${
        isPartial ? 'bg-emerald-50/50' : ''
      }`}
    >
      <CaptionCell
        speakerLabel={segment.speakerLabel}
        timestamp={formatTimestamp(segment.timestampStart)}
        language={originalLanguage}
        text={originalText}
        accent="zinc"
        isPartial={isPartial}
      />
      <CaptionCell
        speakerLabel={segment.speakerLabel}
        timestamp={formatTimestamp(segment.timestampEnd)}
        language={translatedLanguage}
        text={translatedText}
        accent="emerald"
        isPartial={isPartial}
      />
    </article>
  );
}

function CaptionCell({
  speakerLabel,
  timestamp,
  language,
  text,
  accent,
  isPartial,
}: {
  speakerLabel: string;
  timestamp: string;
  language: string;
  text: string;
  accent: 'zinc' | 'emerald';
  isPartial: boolean;
}) {
  const languageClass =
    accent === 'emerald' ? 'text-emerald-700' : 'text-zinc-600';

  return (
    <div className="min-w-0 border-b border-zinc-100 px-4 py-4 md:border-b-0 md:border-r md:last:border-r-0">
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded-full bg-zinc-100 px-2.5 py-1 font-semibold text-zinc-700">
          {speakerLabel}
        </span>
        <span className="font-mono text-zinc-400">{timestamp}</span>
        <span className={`font-semibold ${languageClass}`}>{language}</span>
        {isPartial && (
          <span className="rounded-full bg-emerald-100 px-2 py-1 font-semibold text-emerald-700">
            Live draft
          </span>
        )}
      </div>
      <p className="whitespace-pre-wrap break-words text-base leading-7 text-zinc-950">
        {text || 'No text returned.'}
      </p>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full min-h-[420px] items-center justify-center p-6">
      <div className="max-w-sm text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border border-zinc-200 bg-zinc-50 font-mono text-sm font-semibold text-zinc-500">
          VI/EN
        </div>
        <p className="mt-4 text-sm font-semibold text-zinc-900">
          No finalized captions yet
        </p>
        <p className="mt-1 text-sm text-zinc-500">
          Start a session. Finalized transcript lines will appear here in two
          columns.
        </p>
      </div>
    </div>
  );
}

function formatTimestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
  const totalSeconds = Math.floor(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const remainder = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${remainder
    .toString()
    .padStart(2, '0')}`;
}
