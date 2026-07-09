import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import type { Segment } from '../types/index';
import { MessageSquare, ShieldAlert, Cpu, MicOff, Info } from 'lucide-react';

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
            <div className="relative mb-10">
              <div className="relative border border-ink/8 p-10">
                <MessageSquare className="w-10 h-10 text-ink/15" />
              </div>
            </div>
            <div className="max-w-sm space-y-4">
              <h3 className="text-lg font-bold uppercase tracking-tighter text-ink/60">Transcription Stage</h3>
              <p className="text-xs font-light leading-relaxed text-ink/50">
                Connect to the gateway to begin capturing bilingual audio.<br />
                Data is processed by a private ECS Fargate task.
              </p>
              <div className="grid grid-cols-2 gap-3 mt-8 text-left">
                <EmptyStateFeature icon={<Cpu className="w-4 h-4" />} label="Compute" desc="ECS Fargate" />
                <EmptyStateFeature icon={<ShieldAlert className="w-4 h-4" />} label="Protection" desc="TLS / S3 Encryption" />
              </div>
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
  const originalText = segment
    ? segment.spokenLanguage === 'vi'
      ? segment.textVi
      : segment.textEn
    : '';
  const translatedText = segment
    ? segment.spokenLanguage === 'vi'
      ? segment.textEn
      : segment.textVi
    : '';
  const originalLang = segment?.spokenLanguage === 'en' ? 'EN' : 'VI';
  const translatedLang = segment?.spokenLanguage === 'en' ? 'VI' : 'EN';

  return (
    <section
      aria-label="Live captions"
      className="relative overflow-hidden border border-ink/10 bg-ink text-white shadow-[0_20px_80px_rgba(1,31,91,0.16)]"
    >
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_20%,rgba(34,211,238,0.20),transparent_30%),radial-gradient(circle_at_88%_0%,rgba(168,85,247,0.18),transparent_28%)]" />
      <div className="relative px-5 py-5 sm:px-7 sm:py-6 space-y-5">
        <div className="flex items-center justify-between gap-4 font-mono">
          <div className="flex items-center gap-3">
            <span className="h-2 w-2 rounded-full bg-cyan-300 shadow-[0_0_18px_rgba(103,232,249,0.85)] animate-pulse" />
            <span className="text-[9px] font-bold uppercase tracking-[0.35em] text-white/55">
              {isCapturing ? 'Live transcription' : 'Ready to listen'}
            </span>
          </div>
          <span className="text-[9px] font-bold uppercase tracking-[0.28em] text-white/35">
            Partial updates stream here
          </span>
        </div>

        <LiveCaptionTextLine
          label={`ORIGINAL // ${originalLang}`}
          text={originalText}
          fallback={isCapturing ? 'Listening...' : 'Start capture to begin'}
          tone="primary"
        />
        <LiveCaptionTextLine
          label={`TRANSLATION // ${translatedLang}`}
          text={translatedText}
          fallback={originalText ? 'Translating...' : 'Waiting for speech...'}
          tone="secondary"
        />
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
      gsap.to(textNode, {
        x: -overflow,
        duration: Math.min(Math.max(overflow / 80, 0.45), 2.4),
        ease: 'power2.out',
      });
    }
  }, [visibleText]);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <span
          className={`font-mono text-[9px] font-bold uppercase tracking-[0.35em] ${
            tone === 'primary' ? 'text-cyan-200/70' : 'text-fuchsia-200/70'
          }`}
        >
          {label}
        </span>
        <div className={`h-px flex-1 ${tone === 'primary' ? 'bg-cyan-200/15' : 'bg-fuchsia-200/15'}`} />
      </div>
      <div ref={viewportRef} className="overflow-hidden">
        <span
          ref={textRef}
          className={`block whitespace-nowrap text-3xl font-bold leading-tight tracking-tight sm:text-5xl ${
            hasText
              ? tone === 'primary'
                ? 'text-white'
                : 'bg-gradient-to-r from-cyan-200 via-white to-fuchsia-200 bg-clip-text text-transparent'
              : 'text-white/25'
          }`}
        >
          {visibleText}
        </span>
      </div>
    </div>
  );
}

function EmptyStateFeature({ icon, label, desc }: { icon: React.ReactNode; label: string; desc: string }) {
  return (
    <div className="p-5 border border-ink/12 hover:border-ink/25 transition-colors space-y-2 bg-white/60">
      <div className="text-crimson/60">{icon}</div>
      <div className="font-mono text-[9px] font-bold text-ink/60 uppercase tracking-widest">{label}</div>
      <div className="font-mono text-[9px] text-ink/40 uppercase tracking-wider">{desc}</div>
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

  const originalText = segment.spokenLanguage === 'vi' ? segment.textVi : segment.textEn;
  const translatedText = segment.spokenLanguage === 'vi' ? segment.textEn : segment.textVi;
  const originalLang = segment.spokenLanguage === 'vi' ? 'VI' : 'EN';
  const translatedLang = segment.spokenLanguage === 'vi' ? 'EN' : 'VI';

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
              ORIGIN // {originalLang}
            </span>
            <div className="h-px flex-1 bg-ink/10" />
          </div>
          <p className="font-mono text-sm leading-relaxed text-ink font-medium tracking-tight">
            {originalText || 'NO_DATA'}
          </p>
        </div>
        <div className="px-5 py-4 space-y-2">
          <div className="flex items-center gap-3">
            <span className="font-mono text-[8px] font-bold text-emerald-pro/70 uppercase tracking-[0.3em]">
              RESULT // {translatedLang}
            </span>
            <div className="h-px flex-1 bg-emerald-pro/15" />
          </div>
          <p className="font-mono text-sm leading-relaxed text-emerald-pro font-medium tracking-tight">
            {translatedText || '...'}
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
