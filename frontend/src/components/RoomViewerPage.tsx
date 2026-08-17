import { FormEvent, useMemo, useRef, useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Languages, Radio, Users, WifiOff } from 'lucide-react';
import { useRoomFeed } from '../hooks/useRoomFeed';
import type { Segment } from '../types';

type CaptionLanguage = 'both' | 'vi' | 'en';

export default function RoomViewerPage() {
  const { roomCode } = useParams();
  if (!roomCode) return <RoomJoinForm />;
  return <JoinedRoom roomCode={roomCode.toUpperCase()} />;
}

function RoomJoinForm() {
  const [code, setCode] = useState('');
  const navigate = useNavigate();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const normalized = code.replace(/[^a-zA-Z0-9]/g, '').toUpperCase().slice(0, 6);
    if (normalized.length === 6) navigate(`/rooms/${normalized}`);
  };

  return (
    <div className="min-h-screen bg-paper px-5 py-10 text-ink">
      <div className="mx-auto max-w-lg">
        <a href="/" className="inline-flex items-center gap-2 text-sm font-semibold text-ink/55 hover:text-ink">
          <ArrowLeft className="h-4 w-4" /> Home
        </a>
        <div className="mt-16 text-center">
          <img src="/LiveCap.svg" alt="" className="mx-auto h-14 w-14 rounded-2xl" />
          <p className="mt-6 text-xs font-bold uppercase tracking-[0.2em] text-emerald-pro">LiveCap Rooms</p>
          <h1 className="mt-3 font-instrument text-4xl font-bold tracking-[-0.05em]">Join live captions</h1>
          <p className="mx-auto mt-4 max-w-md text-sm leading-6 text-ink-muted">
            Enter the six-character code shared by the host. Viewers never share microphone access.
          </p>
        </div>
        <form onSubmit={submit} className="mt-10 rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-brutal">
          <label className="text-xs font-bold uppercase tracking-[0.14em] text-ink/55" htmlFor="room-code">Room code</label>
          <input
            id="room-code"
            autoComplete="off"
            autoCapitalize="characters"
            maxLength={6}
            value={code}
            onChange={(event) => setCode(event.target.value.replace(/[^a-zA-Z0-9]/g, '').toUpperCase())}
            className="mt-3 h-16 w-full rounded-xl border border-[#dce5f2] px-4 text-center font-mono text-2xl font-bold uppercase tracking-[0.28em] outline-none focus:border-emerald-pro"
            placeholder="ABC123"
          />
          <button
            type="submit"
            disabled={code.length !== 6}
            className="mt-4 h-12 w-full rounded-xl bg-ink text-sm font-bold text-white transition hover:bg-emerald-pro disabled:cursor-not-allowed disabled:opacity-35"
          >
            Join room
          </button>
        </form>
      </div>
    </div>
  );
}

function JoinedRoom({ roomCode }: { roomCode: string }) {
  const [language, setLanguage] = useState<CaptionLanguage>('both');
  const feed = useRoomFeed(roomCode);
  const scrollRef = useRef<HTMLDivElement>(null);
  const latest = feed.segments[feed.segments.length - 1];

  useEffect(() => {
    const element = scrollRef.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [feed.segments.length]);

  const status = useMemo(() => {
    if (feed.status === 'live') return { label: 'Live', dot: 'bg-emerald-pro animate-pulse', text: 'text-emerald-pro' };
    if (feed.status === 'ended') return { label: 'Saved transcript', dot: 'bg-ink/25', text: 'text-ink/45' };
    if (feed.status === 'error') return { label: 'Unavailable', dot: 'bg-crimson', text: 'text-crimson' };
    return { label: feed.status === 'reconnecting' ? 'Reconnecting' : 'Connecting', dot: 'bg-yellow-500 animate-pulse', text: 'text-yellow-700' };
  }, [feed.status]);

  return (
    <div className="min-h-screen bg-[#f4f7fb] text-ink">
      <header className="sticky top-0 z-20 border-b border-[#dce5f2] bg-white/95 backdrop-blur-xl">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <img src="/LiveCap.svg" alt="" className="h-10 w-10 rounded-xl" />
            <div className="min-w-0">
              <p className="truncate text-sm font-bold">{feed.title}</p>
              <p className="font-mono text-[10px] tracking-[0.15em] text-ink/45">ROOM {roomCode}</p>
            </div>
          </div>
          <span className={`flex shrink-0 items-center gap-2 text-xs font-bold ${status.text}`}>
            <span className={`h-2 w-2 rounded-full ${status.dot}`} /> {status.label}
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-5 sm:px-6 sm:py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-emerald-pro">Audience captions</p>
            <h1 className="mt-2 font-instrument text-3xl font-bold tracking-[-0.04em] sm:text-4xl">Follow every word.</h1>
            <p className="mt-2 flex items-center gap-2 text-xs text-ink-muted">
              <Users className="h-3.5 w-3.5" /> {feed.viewerCount} viewer{feed.viewerCount === 1 ? '' : 's'} connected
            </p>
          </div>
          <LanguagePicker value={language} onChange={setLanguage} />
        </div>

        {feed.error && (
          <div className="mt-5 flex items-start gap-3 rounded-xl border border-crimson/25 bg-crimson/5 p-4 text-sm text-crimson">
            <WifiOff className="mt-0.5 h-4 w-4 shrink-0" /> {feed.error}
          </div>
        )}

        {feed.status === 'ended' && !feed.error && (
          <div className="mt-5 rounded-xl border border-emerald-pro/20 bg-[#effbf8] p-4 text-sm text-ink">
            This meeting has ended. You are viewing its finalized bilingual transcript.
          </div>
        )}

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
        <p className="mt-4 text-center text-[11px] leading-5 text-ink/45">
          Audio stays with the host. This viewer receives finalized text only.
        </p>
      </main>
    </div>
  );
}

function LanguagePicker({ value, onChange }: { value: CaptionLanguage; onChange: (value: CaptionLanguage) => void }) {
  const options: Array<{ value: CaptionLanguage; label: string }> = [
    { value: 'both', label: 'VI + EN' },
    { value: 'vi', label: 'Tiếng Việt' },
    { value: 'en', label: 'English' },
  ];
  return (
    <div className="inline-flex rounded-xl border border-[#dce5f2] bg-white p-1">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`rounded-lg px-3 py-2 text-xs font-bold transition ${value === option.value ? 'bg-ink text-white' : 'text-ink/55 hover:text-ink'}`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function ViewerCaption({ segment, language, isLatest }: { segment: Segment; language: CaptionLanguage; isLatest: boolean }) {
  return (
    <article className={`px-5 py-5 transition-colors sm:px-7 ${isLatest ? 'bg-[#effbf8]/70' : ''}`}>
      <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.16em] text-ink/40">
        <span>{segment.speakerLabel || 'Speaker'}</span>
        <span className="font-mono normal-case tracking-normal">{formatTimestamp(segment.timestampStart)}</span>
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

function formatTimestamp(seconds: number): string {
  const value = Math.max(0, Math.floor(Number.isFinite(seconds) ? seconds : 0));
  return `${Math.floor(value / 60).toString().padStart(2, '0')}:${(value % 60).toString().padStart(2, '0')}`;
}
