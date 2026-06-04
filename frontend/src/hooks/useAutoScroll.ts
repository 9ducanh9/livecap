// Auto-scroll hook: keeps the newest caption visible unless the user has
// scrolled up more than 50px from the bottom of the container.
//
// Requirements: 6.5, 6.6, 6.7

import { useEffect, useRef, useState } from 'react';

/** Pixel threshold below which the user is considered "at the bottom". */
const BOTTOM_THRESHOLD_PX = 50;

/**
 * Tracks whether the user is near the bottom of a scrollable container and
 * auto-scrolls to the newest content when new items are appended.
 *
 * - When the user is within 50px of the bottom and `deps` changes, the
 *   container is scrolled to the bottom automatically (Req 6.5, 6.6).
 * - When the user has scrolled up more than 50px, auto-scroll is suppressed
 *   so the user can review earlier captions without interruption (Req 6.7).
 *
 * @param deps - A value whose change indicates new content has been appended
 *               (e.g. `segments.length`). When this value changes and the
 *               user is within 50px of the bottom, the container scrolls to
 *               the bottom automatically.
 *
 * @returns containerRef - Attach to the scrollable container element.
 * @returns isAtBottom   - Whether the user is within 50px of the bottom.
 *                         Use this to optionally show a "new captions" indicator.
 *
 * @example
 * const { containerRef, isAtBottom } = useAutoScroll(segments.length);
 * // <div ref={containerRef} className="overflow-y-auto">...</div>
 */
export function useAutoScroll(deps: unknown): {
  containerRef: React.RefObject<HTMLDivElement>;
  isAtBottom: boolean;
} {
  const containerRef = useRef<HTMLDivElement>(null);
  // Start assuming the user is at the bottom (empty/fresh list).
  const [isAtBottom, setIsAtBottom] = useState(true);

  // Track "at bottom" on every scroll event.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    function handleScroll() {
      if (!el) return;
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
      setIsAtBottom(distanceFromBottom <= BOTTOM_THRESHOLD_PX);
    }

    el.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      el.removeEventListener('scroll', handleScroll);
    };
  }, []); // Only run once — the scroll listener persists for the element's lifetime.

  // When deps changes (new content appended), auto-scroll only when the user
  // is already at the bottom (Req 6.6). When scrolled up, do nothing (Req 6.7).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Re-read the distance synchronously so we see the post-render scrollHeight.
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = distanceFromBottom <= BOTTOM_THRESHOLD_PX;

    if (atBottom) {
      // Scroll to the very bottom to reveal the newest caption (Req 6.5, 6.6).
      el.scrollTop = el.scrollHeight;
      setIsAtBottom(true);
    }
    // If not at bottom, leave scroll position and isAtBottom state untouched (Req 6.7).
  }, [deps]); // Re-run whenever deps changes.

  return { containerRef, isAtBottom };
}
