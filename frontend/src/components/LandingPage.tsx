import { ArrowRight, AudioLines, Check, Clock3, Cloud, FileText, Globe2, LockKeyhole, Sparkles } from 'lucide-react';

const capabilities = [
  { icon: AudioLines, label: 'Live captions', copy: 'Turn speech into readable, continuously updating captions.' },
  { icon: Globe2, label: 'Bilingual output', copy: 'Keep Vietnamese and English conversations in one shared flow.' },
  { icon: FileText, label: 'Session exports', copy: 'Keep a clean record when the conversation is complete.' },
];

const workflow = [
  ['01', 'Connect', 'Choose a microphone and start a secure live session.'],
  ['02', 'Capture', 'LiveCap streams speech into captions as people speak.'],
  ['03', 'Understand', 'Follow the original and translated conversation side by side.'],
  ['04', 'Keep', 'Export the session when you need a shareable record.'],
];

export default function LandingPage() {
  return (
    <div className="min-h-screen overflow-x-hidden bg-[#f7f8fc] text-[#102247] selection:bg-[#70e0ca] selection:text-[#102247]">
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-56 left-[18%] h-[34rem] w-[34rem] rounded-full bg-[#a9c7ff]/40 blur-3xl" />
        <div className="absolute right-[-12rem] top-[22rem] h-[30rem] w-[30rem] rounded-full bg-[#8ee6d4]/30 blur-3xl" />
      </div>

      <header className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8 lg:px-10">
        <a href="/" className="flex items-center gap-2.5 font-instrument text-xl font-bold tracking-[-0.08em] text-[#102247]" aria-label="LiveCap home">
          <img src="/LiveCap.svg" alt="" className="h-10 w-10 rounded-xl" />
          LIVECAP
        </a>
        <nav className="hidden items-center gap-7 text-sm font-medium text-[#52647f] md:flex" aria-label="Main navigation">
          <a className="transition-colors hover:text-[#102247]" href="#how-it-works">How it works</a>
          <a className="transition-colors hover:text-[#102247]" href="#features">Features</a>
          <a className="transition-colors hover:text-[#102247]" href="#security">Security</a>
          <a className="transition-colors hover:text-[#102247]" href="/privacy">Privacy</a>
        </nav>
        <a href="/app" className="inline-flex items-center gap-2 rounded-full bg-[#102247] px-4 py-2.5 text-sm font-bold text-white shadow-lg shadow-[#102247]/15 transition-transform hover:-translate-y-0.5 hover:bg-[#18376f] sm:px-5">
          Open workspace <ArrowRight className="h-4 w-4" />
        </a>
      </header>

      <main>
        <section className="mx-auto grid max-w-7xl gap-12 px-5 pb-20 pt-14 sm:px-8 sm:pt-20 lg:grid-cols-[1.05fr_.95fr] lg:px-10 lg:pb-32 lg:pt-28">
          <div className="flex max-w-2xl flex-col justify-center">
            <div className="mb-7 inline-flex w-fit items-center gap-2 rounded-full border border-[#9ce5d7] bg-white/70 px-3 py-1.5 text-xs font-bold tracking-wide text-[#087b6c] shadow-sm">
              <span className="h-2 w-2 rounded-full bg-[#16ae96] shadow-[0_0_0_4px_rgba(22,174,150,.14)]" />
              REAL-TIME CONVERSATION SUPPORT
            </div>
            <h1 className="font-instrument text-5xl font-bold leading-[.94] tracking-[-0.07em] text-[#102247] sm:text-6xl lg:text-8xl">
              Real-time captions<br />
              <span className="text-[#0a9c88]">for every conversation</span>
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-8 text-[#52647f] sm:text-xl">
              LiveCap provides real-time Vietnamese-English meeting captions and translation. Capture browser microphone audio and follow live bilingual captions as people speak.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <a href="/app" className="inline-flex items-center gap-3 rounded-full bg-[#0a9c88] px-6 py-4 text-sm font-bold text-white shadow-xl shadow-[#0a9c88]/20 transition-all hover:-translate-y-0.5 hover:bg-[#087b6c]">
                Start a live session
              </a>
              <a href="#how-it-works" className="rounded-full px-4 py-3 text-sm font-bold text-[#435572] transition-colors hover:text-[#0a9c88]">See how it works</a>
            </div>
            <div className="mt-12 flex flex-wrap gap-x-7 gap-y-3 text-sm font-medium text-[#52647f]">
              {['No download needed', 'Microphone controls', 'Export-ready sessions'].map((item) => <span key={item} className="flex items-center gap-2"><Check className="h-4 w-4 text-[#0a9c88]" />{item}</span>)}
            </div>
          </div>

          <div className="relative mx-auto w-full max-w-xl self-center">
            <div className="absolute -inset-5 rounded-[2.5rem] bg-gradient-to-br from-white/70 to-[#8ee6d4]/40 blur-2xl" />
            <div className="relative overflow-hidden rounded-[2rem] border border-white/80 bg-white/75 p-5 shadow-2xl shadow-[#102247]/10 backdrop-blur-xl sm:p-7">
              <div className="flex items-center justify-between border-b border-[#dce5f2] pb-5">
                <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#e2fbf5] text-[#0a9c88]"><AudioLines className="h-5 w-5" /></span><div><p className="text-sm font-bold">Design review</p><p className="text-xs text-[#71819a]">Live transcription</p></div></div>
                <span className="flex items-center gap-1.5 rounded-full bg-[#e4fbf5] px-2.5 py-1 text-[10px] font-bold tracking-wider text-[#087b6c]"><span className="h-1.5 w-1.5 rounded-full bg-[#16ae96] animate-pulse" />LIVE</span>
              </div>
              <div className="space-y-6 py-7">
                <Caption language="VI" text="Chúng ta bắt đầu phần cập nhật kiến trúc nhé." />
                <Caption language="EN" text="Let's begin with the architecture update." emphasis />
                <div className="flex items-end gap-1.5 pt-1" aria-label="Audio activity indicator">{[12, 26, 40, 20, 52, 32, 16, 36, 24, 46, 14, 28].map((height, index) => <span key={index} className="w-1 rounded-full bg-[#0a9c88]/70" style={{ height }} />)}</div>
              </div>
              <div className="flex items-center justify-between rounded-2xl bg-[#f3f6fb] px-4 py-3"><span className="flex items-center gap-2 text-xs font-medium text-[#71819a]"><Clock3 className="h-3.5 w-3.5" />00:12:48 elapsed</span><span className="text-xs font-bold text-[#0a9c88]">Capturing clearly</span></div>
            </div>
          </div>
        </section>

        <section id="features" className="border-y border-[#dce5f2] bg-white/65">
          <div className="mx-auto grid max-w-7xl divide-y divide-[#dce5f2] px-5 sm:grid-cols-3 sm:divide-x sm:divide-y-0 sm:px-8 lg:px-10">
            {capabilities.map(({ icon: Icon, label, copy }) => <article key={label} className="py-8 sm:px-7 sm:py-10 first:sm:pl-0 last:sm:pr-0"><Icon className="mb-6 h-5 w-5 text-[#0a9c88]" /><h2 className="text-lg font-bold tracking-tight">{label}</h2><p className="mt-2 text-sm leading-6 text-[#71819a]">{copy}</p></article>)}
          </div>
        </section>

        <section id="how-it-works" className="mx-auto max-w-7xl px-5 py-20 sm:px-8 lg:px-10 lg:py-28">
          <div className="flex flex-col justify-between gap-8 md:flex-row md:items-end"><div><p className="text-xs font-bold tracking-[.18em] text-[#0a9c88]">SIMPLE BY DESIGN</p><h2 className="mt-3 font-instrument text-4xl font-bold tracking-[-.06em] sm:text-5xl">Ready when the conversation is.</h2></div><p className="max-w-sm text-sm leading-6 text-[#71819a]">A calm, focused workspace that gets out of the way when the discussion starts.</p></div>
          <div className="mt-14 grid gap-4 md:grid-cols-4">{workflow.map(([number, title, copy]) => <article key={number} className="rounded-2xl border border-[#dce5f2] bg-white p-6 transition-transform hover:-translate-y-1 hover:shadow-lg hover:shadow-[#102247]/5"><span className="text-xs font-bold tracking-widest text-[#0a9c88]">{number}</span><h3 className="mt-10 text-xl font-bold tracking-tight">{title}</h3><p className="mt-3 text-sm leading-6 text-[#71819a]">{copy}</p></article>)}</div>
        </section>

        <section id="security" className="mx-auto max-w-7xl px-5 pb-20 sm:px-8 lg:px-10 lg:pb-28"><div className="overflow-hidden rounded-[2rem] bg-[#102247] px-7 py-10 text-white sm:px-12 sm:py-14"><div className="grid gap-10 md:grid-cols-[1fr_auto] md:items-center"><div><div className="mb-6 grid h-11 w-11 place-items-center rounded-xl bg-white/10 text-[#7ee5d0]"><LockKeyhole className="h-5 w-5" /></div><h2 className="font-instrument text-4xl font-bold tracking-[-.06em]">A focused space for sensitive conversations.</h2><p className="mt-4 max-w-xl leading-7 text-[#c4d0e4]">LiveCap keeps controls, status, and captions visible—so you always know what your session is doing.</p></div><a href="/app" className="inline-flex w-fit items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-bold text-[#102247] transition-transform hover:-translate-y-0.5">Enter LiveCap <ArrowRight className="h-4 w-4" /></a></div><div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 border-t border-white/10 pt-6 text-sm text-[#c4d0e4]"><span className="flex items-center gap-2"><LockKeyhole className="h-4 w-4 text-[#7ee5d0]" />Secure browser connection</span><span className="flex items-center gap-2"><Cloud className="h-4 w-4 text-[#7ee5d0]" />Cloud-powered processing</span><span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-[#7ee5d0]" />Built for clarity</span></div></div></section>
      </main>

      <footer className="border-t border-[#dce5f2] px-5 py-7 sm:px-8 lg:px-10"><div className="mx-auto flex max-w-7xl flex-col justify-between gap-3 text-xs font-medium text-[#71819a] sm:flex-row sm:items-center"><span>© {new Date().getFullYear()} LiveCap</span><span>Real-time captions for shared understanding.</span><a href="/privacy" className="transition-colors hover:text-[#102247]">Privacy Policy</a></div></footer>
    </div>
  );
}

function Caption({ language, text, emphasis = false }: { language: string; text: string; emphasis?: boolean }) {
  return <div className={emphasis ? 'border-l-2 border-[#0a9c88] pl-4' : ''}><span className={`text-[10px] font-bold tracking-[.16em] ${emphasis ? 'text-[#0a9c88]' : 'text-[#8795aa]'}`}>{language}</span><p className={`mt-2 text-base leading-7 ${emphasis ? 'font-bold text-[#102247]' : 'text-[#52647f]'}`}>{text}</p></div>;
}
