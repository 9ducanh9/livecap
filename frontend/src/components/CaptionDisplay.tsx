import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import type { Segment } from '../types/index';
import { GlassPanel } from './ui';
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

  return (
    <div className="flex h-full flex-col gap-6 overflow-hidden">
      <div className="flex-1 overflow-y-auto pr-3 space-y-6 flex flex-col-reverse custom-scrollbar" ref={scrollRef}>
        {/* Active Stream */}
        {(isCapturing || currentPartial) && (
          <div className="space-y-6">
            {currentPartial && (
              <CaptionRow key={`partial-${currentPartial.segmentId}`} segment={currentPartial} isPartial />
            )}
            {/* Newest finalized segments */}
            {[...segments].reverse().slice(0, 1).map((segment) => (
              <CaptionRow key={segment.segmentId} segment={segment} />
            ))}
          </div>
        )}

        {/* Previous History */}
        {[...segments].reverse().slice(1).map((segment) => (
          <CaptionRow key={segment.segmentId} segment={segment} />
        ))}

        {/* Empty / Initial State */}
        {segments.length === 0 && !currentPartial && (
          <div className="flex flex-1 flex-col items-center justify-center text-center p-10 min-h-[500px]">
            <div className="relative mb-10">
              <div className="absolute inset-0 bg-crimson/20 blur-[80px] rounded-full scale-150 animate-pulse" />
              <div className="relative border border-white/10 bg-white/5 p-10 backdrop-blur-xl">
                <MessageSquare className="w-12 h-12 text-white/30" />
              </div>
            </div>

            <div className="max-w-md space-y-5">
              <h3 className="text-2xl font-bold uppercase tracking-tighter text-white/90">Transcription Stage</h3>
              <p className="text-sm font-light leading-relaxed text-white/50 px-6">
                Connect to the gateway to begin capturing bilingual audio. Data is processed by a private ECS Fargate task.
              </p>

              <div className="grid grid-cols-2 gap-4 mt-12 text-left">
                <EmptyStateFeature icon={<Cpu className="w-4 h-4" />} label="Compute" desc="ECS Fargate" />
                <EmptyStateFeature icon={<ShieldAlert className="w-4 h-4" />} label="Protection" desc="TLS / S3 encryption" />
              </div>
            </div>
          </div>
        )}

        {/* Permission Denied Overlay */}
        {permissionDenied && (
          <div className="border border-crimson/20 bg-crimson/5 p-12 text-center space-y-6">
            <MicOff className="w-10 h-10 text-crimson mx-auto animate-bounce" />
            <div className="space-y-2">
              <h4 className="text-base font-bold uppercase tracking-[0.2em] text-crimson">Hardware Access Error</h4>
              <p className="text-xs text-white/60 max-w-sm mx-auto leading-relaxed">
                Browser blocked microphone capture. Please allow access in the address bar settings and refresh the engine.
              </p>
            </div>
            <div className="h-px w-20 bg-crimson/20 mx-auto" />
          </div>
        )}

        {/* Loading / Connecting State */}
        {isConnecting && segments.length === 0 && !currentPartial && (
          <div className="flex flex-col items-center justify-center py-32 space-y-8">
            <div className="w-16 h-1 bg-white/5 overflow-hidden">
              <div className="w-1/2 h-full bg-crimson animate-[loading_1.5s_infinite_linear]" />
            </div>
            <p className="text-[10px] font-mono font-bold uppercase tracking-[0.5em] text-white/50 animate-pulse">
              SYNCING_NODE_STREAMS...
            </p>
          </div>
        )}
      </div>

      {/* Footer / Anchor */}
      <div className="flex items-center gap-6 py-4 border-t border-white/5 bg-obsidian/40 backdrop-blur-sm px-4">
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-white/10 to-transparent" />
        <div className="flex items-center gap-3">
          <Info className="w-3.5 h-3.5 text-white/30" />
          <span className="text-[9px] font-mono font-bold uppercase tracking-[0.3em] text-white/40">
            {isCapturing ? 'GATEWAY: LINKED' : 'GATEWAY: WAITING'}
          </span>
        </div>
        <div className="h-px flex-1 bg-gradient-to-r from-transparent via-white/10 to-transparent" />
      </div>
    </div>
  );
}

function EmptyStateFeature({ icon, label, desc }: { icon: React.ReactNode, label: string, desc: string }) {
  return (
    <div className="space-y-2 p-5 border border-white/5 bg-white/[0.03] hover:bg-white/[0.05] transition-colors">
      <div className="text-crimson/60">{icon}</div>
      <div className="text-[10px] font-bold text-white/70 uppercase tracking-widest">{label}</div>
      <div className="text-[9px] text-white/40 uppercase tracking-wider font-medium">{desc}</div>
    </div>
  );
}

function CaptionRow({ segment, isPartial = false }: { segment: Segment; isPartial?: boolean }) {
  const rowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (rowRef.current) {
      gsap.from(rowRef.current, {
        autoAlpha: 0,
        y: 30,
        duration: 0.6,
        ease: 'power4.out',
      });
    }
  }, []);

  const originalText = segment.spokenLanguage === 'vi' ? segment.textVi : segment.textEn;
  const translatedText = segment.spokenLanguage === 'vi' ? segment.textEn : segment.textVi;
  const originalLang = segment.spokenLanguage === 'vi' ? 'VI' : 'EN';
  const translatedLang = segment.spokenLanguage === 'vi' ? 'EN' : 'VI';

  return (
    <div ref={rowRef}>
      <GlassPanel className={`p-8 transition-all duration-500 hover:border-white/20 group ${isPartial ? 'opacity-90 border-dashed border-crimson/40 bg-crimson/[0.02] shadow-[inset_0_0_30px_rgba(225,29,72,0.03)]' : 'bg-white/[0.02]'}`}>
        <div className="mb-6 flex items-center justify-between font-mono text-[10px] font-bold uppercase tracking-[0.25em] text-white/30 group-hover:text-white/50 transition-colors">
          <div className="flex items-center gap-4">
            <span className="bg-white/5 px-2 py-0.5">{segment.speakerLabel}</span>
            {isPartial && (
              <span className="flex items-center gap-2 text-crimson">
                <span className="w-2 h-2 rounded-full bg-crimson animate-ping" />
                CAPTURE_IN_PROGRESS
              </span>
            )}
          </div>
          <span className="tabular-nums opacity-60">{formatTimestamp(segment.timestampStart)}</span>
        </div>
        <div className="grid gap-10 lg:grid-cols-2 lg:gap-16">
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <span className="text-[9px] font-mono font-bold text-white/20 uppercase tracking-[0.3em]">ORIGIN // {originalLang}</span>
              <div className="h-px flex-1 bg-white/5" />
            </div>
            <p className="text-lg leading-relaxed text-white font-mono tracking-tight font-medium selection:bg-crimson">
              {originalText || 'NO_DATA'}
            </p>
          </div>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <span className="text-[9px] font-mono font-bold text-emerald-pro/40 uppercase tracking-[0.3em]">RESULT // {translatedLang}</span>
              <div className="h-px flex-1 bg-emerald-pro/5" />
            </div>
            <p className="text-lg leading-relaxed text-emerald-pro font-mono tracking-tight font-medium selection:bg-emerald-pro selection:text-white">
              {translatedText || '...'}
            </p>
          </div>
        </div>
      </GlassPanel>
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
