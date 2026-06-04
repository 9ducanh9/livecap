// Two-column bilingual caption display component.
// Left column: Vietnamese text. Right column: English text.
// Partial segments are replaced in-place; finalized segments are appended
// in the order received.
//
// Requirements: 4.3, 6.1, 6.2, 6.3, 6.4

import type { Segment } from '../types/index';
import { useAutoScroll } from '../hooks/useAutoScroll';

interface CaptionDisplayProps {
  /** Ordered list of finalized segments (append-only from the WebSocket layer). */
  segments: Segment[];
  /** The current in-flight partial segment, or null when there is none. */
  currentPartial: Segment | null;
}

// ---------------------------------------------------------------------------
// SegmentRow — renders one caption row with speaker label + both language columns
// ---------------------------------------------------------------------------

interface SegmentRowProps {
  segment: Segment;
  isPartial?: boolean;
}

function SegmentRow({ segment, isPartial = false }: SegmentRowProps) {
  return (
    <div
      className={`grid grid-cols-2 gap-4 px-4 py-3 border-b border-slate-100 last:border-b-0 ${
        isPartial ? 'opacity-70' : ''
      }`}
      // Announce updates to screen readers when a partial segment changes
      aria-live={isPartial ? 'polite' : undefined}
      aria-atomic={isPartial ? 'true' : undefined}
    >
      {/* Left column — Vietnamese */}
      <div className="flex flex-col gap-1">
        <span className="text-xs font-semibold text-indigo-600 select-none">
          {segment.speakerLabel}
          {isPartial && (
            <span className="ml-1 text-slate-400 font-normal" aria-label="transcribing">
              …
            </span>
          )}
        </span>
        <p
          lang="vi"
          className={`text-sm leading-relaxed text-slate-800 ${
            !segment.textVi ? 'text-slate-400 italic' : ''
          }`}
        >
          {segment.textVi || '\u00A0' /* non-breaking space keeps row height */}
        </p>
      </div>

      {/* Right column — English */}
      <div className="flex flex-col gap-1">
        {/* Invisible speaker label placeholder so English column aligns with
            the Vietnamese speaker label on the same row */}
        <span className="text-xs font-semibold text-transparent select-none" aria-hidden="true">
          {segment.speakerLabel}
        </span>
        <p
          lang="en"
          className={`text-sm leading-relaxed text-slate-800 ${
            !segment.textEn ? 'text-slate-400 italic' : ''
          }`}
        >
          {segment.textEn || '\u00A0'}
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Column headers
// ---------------------------------------------------------------------------

function ColumnHeaders() {
  return (
    <div className="grid grid-cols-2 gap-4 px-4 py-2 bg-slate-100 border-b border-slate-200 sticky top-0 z-10">
      <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
        Vietnamese
      </div>
      <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
        English
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CaptionDisplay
// ---------------------------------------------------------------------------

export default function CaptionDisplay({ segments, currentPartial }: CaptionDisplayProps) {
  // Auto-scroll: pass segments.length so the hook re-runs whenever a new
  // segment is appended. The hook only scrolls when the user is at the bottom.
  const { containerRef, isAtBottom } = useAutoScroll(segments.length);

  // Determine whether the partial segment is already represented in the
  // finalized list (i.e. it was just finalized and should not be shown again).
  const partialIsAlreadyFinalized =
    currentPartial !== null &&
    segments.some((s) => s.segmentId === currentPartial.segmentId);

  const showPartial = currentPartial !== null && !partialIsAlreadyFinalized;

  const isEmpty = segments.length === 0 && !showPartial;

  return (
    <section
      aria-label="Bilingual captions"
      className="flex flex-col h-full bg-white rounded-lg border border-slate-200 overflow-hidden"
    >
      <ColumnHeaders />

      {/* "New captions" indicator — shown when the user has scrolled up and new
          segments have arrived. Clicking it is not wired here; callers can add
          an onClick to the containerRef to scroll to bottom if desired. */}
      {!isAtBottom && segments.length > 0 && (
        <div
          className="flex justify-center py-1 bg-indigo-50 border-b border-indigo-100"
          aria-live="polite"
          aria-atomic="true"
        >
          <span className="text-xs text-indigo-600 select-none">↓ New captions</span>
        </div>
      )}

      {/* Scrollable caption list */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-label="Caption log"
      >
        {isEmpty ? (
          <div className="flex items-center justify-center h-32 text-slate-400 text-sm select-none">
            Captions will appear here once the session starts.
          </div>
        ) : (
          <>
            {/* Finalized segments — rendered in the order they were received */}
            {segments.map((segment) => (
              <SegmentRow key={segment.segmentId} segment={segment} isPartial={false} />
            ))}

            {/* Current partial segment — shown below the finalized list and
                replaced in-place as updates arrive for the same Segment_ID */}
            {showPartial && (
              <SegmentRow
                key={`partial-${currentPartial!.segmentId}`}
                segment={currentPartial!}
                isPartial={true}
              />
            )}
          </>
        )}
      </div>
    </section>
  );
}
