import { useEffect, useRef, useState } from 'react';
import { Languages, Radio } from 'lucide-react';
import type { RoomFeedState } from '../hooks/useRoomFeed';
import type { Segment } from '../types';
import RoomScreenViewer from './RoomScreenViewer';

type CaptionLanguage = 'both' | 'vi' | 'en';
type CaptionLayout = 'overlay' | 'below';

export default function RoomAudienceContent({
  roomCode,
  feed,
  muted = false,
}: {
  roomCode: string;
  feed: RoomFeedState;
  muted?: boolean;
}) {
  const [language, setLanguage] = useState<CaptionLanguage>('vi');
  const [layout, setLayout] = useState<CaptionLayout>('overlay');
  const [hasVideo, setHasVideo] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const latest = feed.segments[feed.segments.length - 1];
  const showTranscript = layout === 'below' || feed.mediaStatus !== 'live' || !hasVideo;

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [feed.segments.length, layout]);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-xl border border-[#dce5f2] bg-white p-1">
          {([
            { value: 'both', label: 'VI + EN' },
            { value: 'vi', label: 'Tiếng Việt' },
            { value: 'en', label: 'English' },
          ] as const).map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setLanguage(option.value)}
              aria-pressed={language === option.value}
              className={`rounded-lg px-3 py-2 text-xs font-bold transition ${language === option.value ? 'bg-ink text-white' : 'text-ink/55 hover:text-ink'}`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="inline-flex rounded-xl border border-[#dce5f2] bg-white p-1">
          {(['overlay', 'below'] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setLayout(option)}
              aria-pressed={layout === option}
              className={`rounded-lg px-3 py-2 text-xs font-bold ${layout === option ? 'bg-ink text-white' : 'text-ink/55'}`}
            >
              {option === 'overlay' ? 'Subtitles on video' : 'Transcript below'}
            </button>
          ))}
        </div>
      </div>

      <section className="mt-4">
        <RoomScreenViewer
          roomCode={roomCode}
          active={feed.mediaStatus === 'live'}
          muted={muted}
          onVideoStateChange={setHasVideo}
          subtitle={feed.mediaStatus === 'live' && hasVideo && layout === 'overlay' && latest ? {
            id: latest.segmentId,
            textVi: latest.textVi,
            textEn: latest.textEn,
            language,
          } : undefined}
        />
      </section>

      {showTranscript && (
        <section className="mt-5 overflow-hidden rounded-2xl border border-[#dce5f2] bg-white shadow-brutal">
          <div className="flex items-center justify-between border-b border-[#dce5f2] px-5 py-4">
            <span className="flex items-center gap-2 text-xs font-bold text-ink/60">
              <Radio className="h-4 w-4 text-emerald-pro" />
              {feed.status === 'ended' ? 'Finalized transcript' : 'Finalized captions only'}
            </span>
            <span className="font-mono text-[10px] text-ink/40">{feed.segments.length} lines</span>
          </div>
          <div ref={scrollRef} className="h-[min(65vh,680px)] overflow-y-auto custom-scrollbar">
            {feed.segments.length === 0 ? (
              <div className="grid h-full min-h-[360px] place-items-center p-8 text-center">
                <div>
                  <Languages className="mx-auto h-9 w-9 text-emerald-pro/60" />
                  <p className="mt-4 font-bold text-ink">
                    {feed.status === 'ended' ? 'No finalized captions were saved' : 'Waiting for the host to speak'}
                  </p>
                  <p className="mt-2 text-sm text-ink-muted">
                    {feed.status === 'ended'
                      ? 'The meeting ended before a caption was finalized.'
                      : 'Captions appear here after each phrase is finalized.'}
                  </p>
                </div>
              </div>
            ) : (
              <div className="divide-y divide-ink/8">
                {feed.segments.map((segment) => (
                  <ViewerCaption key={segment.segmentId} segment={segment} language={language} isLatest={segment === latest} />
                ))}
              </div>
            )}
          </div>
        </section>
      )}
    </>
  );
}

function ViewerCaption({ segment, language, isLatest }: { segment: Segment; language: CaptionLanguage; isLatest: boolean }) {
  return (
    <article className={`px-5 py-5 transition-colors sm:px-7 ${isLatest ? 'bg-[#effbf8]/70' : ''}`}>
      <div className="text-[10px] font-bold uppercase tracking-[0.16em] text-ink/40">
        {segment.speakerLabel || 'Speaker'}
      </div>
      {language === 'both' ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-2 sm:gap-6">
          <CaptionText label="Vietnamese" text={segment.textVi} />
          <CaptionText label="English" text={segment.textEn} translated />
        </div>
      ) : (
        <div className="mt-3">
          <CaptionText
            label={language === 'vi' ? 'Vietnamese' : 'English'}
            text={language === 'vi' ? segment.textVi : segment.textEn}
            translated={language === 'en'}
            large
          />
        </div>
      )}
    </article>
  );
}

function CaptionText({ label, text, translated = false, large = false }: { label: string; text: string; translated?: boolean; large?: boolean }) {
  return (
    <div className="min-w-0">
      <p className={`text-[9px] font-bold uppercase tracking-[0.18em] ${translated ? 'text-emerald-pro/70' : 'text-ink/40'}`}>{label}</p>
      <p className={`mt-1.5 break-words font-medium leading-relaxed ${large ? 'text-xl sm:text-2xl' : 'text-base sm:text-lg'} ${translated ? 'text-emerald-pro' : 'text-ink'}`}>
        {text || '...'}
      </p>
    </div>
  );
}
