import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import type { Segment } from '../types/index';
import { MessageSquare, MicOff, Info, Sparkles } from 'lucide-react';

interface CaptionDisplayProps {
  segments: Segment[];
  currentPartial: Segment | null;
  isCapturing?: boolean;
  isConnecting?: boolean;
  permissionDenied?: boolean;
}

export default function CaptionDisplay({
  segments,
  currentPartial,
  isCapturing,
  isConnecting,
  permissionDenied,
}: CaptionDisplayProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const hasLiveStage = Boolean(isCapturing || currentPartial);

  return (
    <div className="flex h-full flex-col overflow-hidden gap-4">
      {hasLiveStage && (
        <LiveCaptionStage segment={currentPartial} isCapturing={isCapturing} />
      )}

      <div
        className="flex-1 overflow-y-auto space-y-2 custom-scrollbar"
        ref={scrollRef}
      >
        {/* History */}
        {[...segments].reverse().map((seg) => (
          <CaptionRow key={seg.segmentId} segment={seg} />
        ))}

        {/* Empty state */}
        {segments.length === 0 && !currentPartial && !permissionDenied && !isConnecting && (
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
        {isConnecting && segments.length === 0 && !currentPartial && (
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

function LiveCaptionStage({ segment, isCapturing = false }: { segment: Segment | null; isCapturing?: boolean }) {
  const vietnameseText = segment?.textVi ?? '';
  const englishText = segment?.textEn ?? '';

  return (
    <section
      aria-label="Live captions"
      className="relative overflow-hidden rounded-2xl border border-[#bde8de] bg-[#effbf8] text-ink shadow-[0_16px_40px_rgba(16,34,71,0.08)]"
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_20%,rgba(53,190,169,0.20),transparent_35%),radial-gradient(circle_at_88%_0%,rgba(169,199,255,0.3),transparent_32%)]" />
      <div className="relative px-5 py-5 sm:px-7 sm:py-6 space-y-5">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="h-2 w-2 rounded-full bg-emerald-pro shadow-[0_0_14px_rgba(10,156,136,0.5)] animate-pulse" />
            <span className="text-xs font-bold text-ink/60">
              {isCapturing ? 'Live captions' : 'Ready to listen'}
            </span>
          </div>
        </div>

        <div className="grid gap-6 md:grid-cols-2 md:divide-x md:divide-[#bde8de]">
          <LiveCaptionTextLine
            label="VIETNAMESE"
            text={vietnameseText}
            fallback={isCapturing ? 'Đang lắng nghe...' : 'Bắt đầu để ghi âm'}
            tone="primary"
          />
          <div className="md:pl-6">
            <LiveCaptionTextLine
              label="ENGLISH"
              text={englishText}
              fallback={vietnameseText ? 'Translating...' : 'Waiting for speech...'}
              tone="secondary"
            />
          </div>
        </div>
      </div>
    </section>
  );
}

function LiveCaptionTextLine({
  label,
  text,
  fallback,
  tone,
}: {
  label: string;
  text: string;
  fallback: string;
  tone: 'primary' | 'secondary';
}) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const visibleText = text.trim() || fallback;
  const hasText = text.trim().length > 0;

  useEffect(() => {
    const viewport = viewportRef.current;
    const textNode = textRef.current;
    if (!viewport || !textNode) return;

    gsap.killTweensOf(textNode);
    gsap.set(textNode, { x: 0 });

    const overflow = textNode.scrollWidth - viewport.clientWidth;
    if (overflow > 0) {
      const duration = Math.min(Math.max(overflow / 55, 2.5), 8);
      gsap.to(textNode, {
        x: -overflow,
        duration,
        delay: 0.35,
        ease: 'none',
        repeat: -1,
        yoyo: true,
        repeatDelay: 0.9,
      });
    }

    return () => gsap.killTweensOf(textNode);
  }, [visibleText]);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <span
          className={`text-[10px] font-bold uppercase tracking-[0.16em] ${
            tone === 'primary' ? 'text-emerald-pro/80' : 'text-[#416baf]/75'
          }`}
        >
          {label}
        </span>
        <div className={`h-px flex-1 ${tone === 'primary' ? 'bg-emerald-pro/20' : 'bg-[#416baf]/20'}`} />
      </div>
      <div ref={viewportRef} className="overflow-hidden">
        <span
          ref={textRef}
          className={`inline-block min-w-max whitespace-nowrap text-lg font-semibold leading-7 tracking-[-0.02em] sm:text-xl ${
            hasText
              ? tone === 'primary'
                ? 'text-ink'
                : 'bg-gradient-to-r from-emerald-pro via-ink to-[#416baf] bg-clip-text text-transparent'
              : 'text-ink/25'
          }`}
        >
          {visibleText}
        </span>
      </div>
    </div>
  );
}

function CaptionRow({ segment, isPartial = false }: { segment: Segment; isPartial?: boolean }) {
  const rowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (rowRef.current) {
      gsap.from(rowRef.current, { autoAlpha: 0, y: 16, duration: 0.45, ease: 'power3.out' });
    }
  }, []);

  const vietnameseText = segment.textVi;
  const englishText = segment.textEn;

  return (
    <div
      ref={rowRef}
      className={`border transition-all group ${
        isPartial
          ? 'border-crimson/30 bg-crimson/3 border-dashed'
          : 'border-ink/8 hover:border-ink/20 bg-white/50'
      }`}
    >
      {/* Row header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-ink/8 font-mono">
        <div className="flex items-center gap-4">
          <span className="text-[9px] font-bold text-ink/40 uppercase tracking-widest bg-ink/5 px-2 py-0.5">
            {segment.speakerLabel}
          </span>
          {isPartial && (
            <span className="flex items-center gap-2 font-mono text-[9px] font-bold text-crimson uppercase tracking-widest">
              <span className="w-1.5 h-1.5 rounded-full bg-crimson animate-ping" />
              CAPTURE_IN_PROGRESS
            </span>
          )}
        </div>
        <span className="font-mono text-[9px] text-ink/40 tabular-nums">
          {formatTimestamp(segment.timestampStart)}
        </span>
      </div>

      {/* 2-column content */}
      <div className="grid lg:grid-cols-2 divide-x divide-ink/6">
        <div className="px-5 py-4 space-y-2">
          <div className="flex items-center gap-3">
            <span className="font-mono text-[8px] font-bold text-ink/40 uppercase tracking-[0.3em]">
              VIETNAMESE
            </span>
            <div className="h-px flex-1 bg-ink/10" />
          </div>
          <p className="font-mono text-sm leading-relaxed text-ink font-medium tracking-tight">
            {vietnameseText || '...'}
          </p>
        </div>
        <div className="px-5 py-4 space-y-2">
          <div className="flex items-center gap-3">
            <span className="font-mono text-[8px] font-bold text-emerald-pro/70 uppercase tracking-[0.3em]">
              ENGLISH
            </span>
            <div className="h-px flex-1 bg-emerald-pro/15" />
          </div>
          <p className="font-mono text-sm leading-relaxed text-emerald-pro font-medium tracking-tight">
            {englishText || '...'}
          </p>
        </div>
      </div>
    </div>
  );
}

function formatTimestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
  const totalSeconds = Math.floor(seconds);
  const minutes = Math.floor(totalSeconds / 60);
  const remainder = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${remainder.toString().padStart(2, '0')}`;
}
