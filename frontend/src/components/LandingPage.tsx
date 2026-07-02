import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

const mockupSteps = [
  {
    eyebrow: 'Step 01',
    title: 'Microphone connected',
    body: 'Capture starts only after the backend is awake and the WebSocket is ready.',
    primary: 'Default microphone',
    secondary: '16 kHz PCM stream ready',
  },
  {
    eyebrow: 'Step 02',
    title: 'Vietnamese speech appears',
    body: 'Finalized source captions are appended as meeting participants speak.',
    primary: 'Nghe rõ mọi ý trong cuộc họp.',
    secondary: 'Speaker 1 · 00:14',
  },
  {
    eyebrow: 'Step 03',
    title: 'English translation appears',
    body: 'LiveCap renders the translated line beside the original text.',
    primary: 'Understand every point in the meeting.',
    secondary: 'Speaker 1 · 00:14',
  },
  {
    eyebrow: 'Step 04',
    title: 'Export TXT becomes ready',
    body: 'When the session ends, finalized lines can be exported through the backend.',
    primary: 'Transcript exported',
    secondary: 'Presigned TXT link ready',
  },
] as const;

const architectureNodes = [
  'Microphone',
  'CloudFront',
  'ALB',
  'ECS Fargate',
  'Transcribe',
  'Translate',
  'Live Caption',
] as const;

const transcriptLines = [
  {
    speaker: 'Speaker 1',
    vi: 'Chúng ta bắt đầu với phần cập nhật kiến trúc.',
    en: 'Let us begin with the architecture update.',
  },
  {
    speaker: 'Speaker 2',
    vi: 'Backend sẽ tự bật khi có phiên capture mới.',
    en: 'The backend wakes when a new capture session starts.',
  },
  {
    speaker: 'Speaker 1',
    vi: 'Transcript chỉ lưu 14 ngày để kiểm soát chi phí.',
    en: 'Transcripts are kept for 14 days to control cost.',
  },
] as const;

export default function LandingPage() {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (rootRef.current === null) return undefined;

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduceMotion) return undefined;

    const ctx = gsap.context(() => {
      gsap.from('.hero-copy', {
        y: 32,
        scale: 0.985,
        duration: 1.1,
        ease: 'power3.out',
      });

      gsap.to('.hero-orb', {
        y: -120,
        scale: 1.16,
        opacity: 0.9,
        scrollTrigger: {
          trigger: '.hero-section',
          start: 'top top',
          end: 'bottom top',
          scrub: true,
        },
      });

      const mockupStepsEls = gsap.utils.toArray<HTMLElement>('.mockup-step');
      gsap.set(mockupStepsEls.slice(1), {
        autoAlpha: 0,
        y: 28,
        scale: 0.98,
        filter: 'blur(12px)',
      });

      const mockupTimeline = gsap.timeline({
        scrollTrigger: {
          trigger: '.mockup-section',
          start: 'top top',
          end: '+=3200',
          scrub: true,
          pin: true,
        },
      });

      mockupStepsEls.forEach((step, index) => {
        if (index === 0) return;

        mockupTimeline
          .to(
            mockupStepsEls[index - 1],
            {
              autoAlpha: 0,
              y: -28,
              scale: 0.98,
              filter: 'blur(12px)',
              duration: 0.45,
            },
            index,
          )
          .to(
            step,
            {
              autoAlpha: 1,
              y: 0,
              scale: 1,
              filter: 'blur(0px)',
              duration: 0.45,
            },
            index,
          );
      });

      gsap.from('.transcript-line', {
        y: 28,
        opacity: 0,
        filter: 'blur(10px)',
        stagger: 0.16,
        duration: 0.8,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: '.transcript-section',
          start: 'top 70%',
        },
      });

      const nodes = gsap.utils.toArray<HTMLElement>('.architecture-node');
      const architectureTimeline = gsap.timeline({
        scrollTrigger: {
          trigger: '.architecture-section',
          start: 'top center',
          end: 'bottom center',
          scrub: true,
        },
      });

      nodes.forEach((node) => {
        architectureTimeline.to(node, {
          opacity: 1,
          scale: 1.04,
          borderColor: 'rgba(16, 185, 129, 0.72)',
          backgroundColor: 'rgba(16, 185, 129, 0.14)',
          duration: 0.28,
        });
      });
    }, rootRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={rootRef} className="bg-[#050506] text-white">
      <HeroSection />
      <PinnedMockupSection />
      <TranscriptAnimationSection />
      <ArchitectureSection />
      <FinalCtaSection />
    </div>
  );
}

function HeroSection() {
  return (
    <section className="hero-section relative flex min-h-screen overflow-hidden px-5 py-6 sm:px-8">
      <div className="hero-orb pointer-events-none absolute left-1/2 top-1/2 h-[620px] w-[620px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,rgba(16,185,129,0.28),rgba(20,184,166,0.08)_42%,transparent_70%)] blur-2xl" />
      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.045)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.045)_1px,transparent_1px)] bg-[size:80px_80px] opacity-25" />

      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-col">
        <nav className="flex items-center justify-between rounded-full border border-white/10 bg-white/[0.04] px-4 py-3 backdrop-blur-xl">
          <a href="/" className="text-sm font-semibold tracking-tight">
            LiveCap
          </a>
          <a
            href="/app"
            className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-black transition hover:bg-emerald-100"
          >
            Open app
          </a>
        </nav>

        <div className="hero-copy flex flex-1 flex-col items-center justify-center py-20 text-center will-change-transform">
          <p className="mb-5 rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm text-white/72">
            Realtime bilingual captions for Vietnamese and English meetings
          </p>
          <h1 className="max-w-5xl text-5xl font-semibold tracking-[-0.04em] text-white sm:text-7xl lg:text-8xl">
            Understand every meeting. In real time.
          </h1>
          <p className="mt-7 max-w-2xl text-lg leading-8 text-white/64">
            LiveCap captures microphone audio, streams it to a protected backend,
            and returns clean captions in two languages while the meeting is still
            happening.
          </p>
          <div className="mt-10 flex flex-col gap-3 sm:flex-row">
            <a
              href="/app"
              className="rounded-full bg-emerald-400 px-6 py-3 text-sm font-semibold text-black transition hover:bg-emerald-300"
            >
              Start captioning
            </a>
            <a
              href="#architecture"
              className="rounded-full border border-white/12 px-6 py-3 text-sm font-semibold text-white/82 transition hover:bg-white/[0.06]"
            >
              View architecture
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}

function PinnedMockupSection() {
  return (
    <section className="mockup-section relative min-h-screen px-5 py-16 sm:px-8">
      <div className="mx-auto grid h-full min-h-[760px] w-full max-w-7xl gap-10 lg:grid-cols-[0.82fr_1.18fr] lg:items-center">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-emerald-300">
            Product flow
          </p>
          <h2 className="mt-4 max-w-xl text-4xl font-semibold tracking-[-0.03em] sm:text-6xl">
            The meeting turns into readable bilingual context.
          </h2>
          <p className="mt-5 max-w-lg text-lg leading-8 text-white/60">
            Scroll through the capture flow. The app waits for the backend,
            opens a WebSocket, appends finalized transcript lines, and prepares a
            TXT export when the session is complete.
          </p>
        </div>

        <div className="relative min-h-[560px] rounded-[2rem] border border-white/12 bg-white/[0.06] p-3 shadow-2xl shadow-emerald-950/30 backdrop-blur-2xl">
          <div className="h-full rounded-[1.5rem] border border-white/10 bg-[#0b0d10] p-5">
            <div className="mb-5 flex items-center justify-between border-b border-white/10 pb-4">
              <div>
                <p className="text-sm font-semibold">LiveCap Session</p>
                <p className="mt-1 text-xs text-white/45">WebSocket stream ready</p>
              </div>
              <span className="rounded-full bg-emerald-400/15 px-3 py-1 text-xs font-semibold text-emerald-300">
                Recording
              </span>
            </div>

            <div className="relative min-h-[450px] overflow-hidden rounded-2xl bg-black/24">
              {mockupSteps.map((step) => (
                <MockupStep key={step.title} {...step} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function MockupStep({
  eyebrow,
  title,
  body,
  primary,
  secondary,
}: {
  eyebrow: string;
  title: string;
  body: string;
  primary: string;
  secondary: string;
}) {
  return (
    <div className="mockup-step absolute inset-0 flex flex-col justify-between p-6">
      <div>
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-emerald-300">
          {eyebrow}
        </p>
        <h3 className="mt-4 text-3xl font-semibold tracking-[-0.03em] text-white">
          {title}
        </h3>
        <p className="mt-4 max-w-md text-sm leading-6 text-white/60">{body}</p>
      </div>

      <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-5">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-white/40">
          Live output
        </p>
        <p className="mt-4 text-2xl font-semibold tracking-[-0.02em] text-white">
          {primary}
        </p>
        <p className="mt-3 font-mono text-sm text-emerald-300">{secondary}</p>
      </div>
    </div>
  );
}

function TranscriptAnimationSection() {
  return (
    <section className="transcript-section px-5 py-28 sm:px-8">
      <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.24em] text-emerald-300">
            Captions
          </p>
          <h2 className="mt-4 text-4xl font-semibold tracking-[-0.03em] sm:text-5xl">
            Finalized transcript lines appear without distracting motion.
          </h2>
        </div>

        <div className="space-y-4">
          {transcriptLines.map((line) => (
            <div
              key={line.vi}
              className="transcript-line rounded-2xl border border-white/10 bg-white/[0.06] p-5 backdrop-blur-xl"
            >
              <div className="mb-4 flex items-center justify-between text-xs text-white/45">
                <span>{line.speaker}</span>
                <span>Finalized</span>
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <p className="leading-7 text-white">{line.vi}</p>
                <p className="leading-7 text-emerald-200">{line.en}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ArchitectureSection() {
  return (
    <section id="architecture" className="architecture-section px-5 py-28 sm:px-8">
      <div className="mx-auto max-w-7xl">
        <p className="text-sm font-semibold uppercase tracking-[0.24em] text-emerald-300">
          Architecture
        </p>
        <h2 className="mt-4 max-w-3xl text-4xl font-semibold tracking-[-0.03em] sm:text-5xl">
          A simple realtime path from browser audio to live captions.
        </h2>

        <div className="mt-12 grid gap-3 md:grid-cols-7">
          {architectureNodes.map((node, index) => (
            <div key={node} className="flex items-center gap-3 md:block">
              <div className="architecture-node rounded-2xl border border-white/10 bg-white/[0.04] p-4 opacity-55 transition-colors">
                <div className="font-mono text-xs text-white/40">
                  {String(index + 1).padStart(2, '0')}
                </div>
                <div className="mt-3 text-sm font-semibold text-white">{node}</div>
              </div>
              {index < architectureNodes.length - 1 && (
                <div className="h-px flex-1 bg-white/14 md:mx-auto md:my-4 md:h-px md:w-full" />
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function FinalCtaSection() {
  return (
    <section className="px-5 py-28 sm:px-8">
      <div className="mx-auto max-w-4xl rounded-[2rem] border border-white/10 bg-white/[0.06] p-8 text-center sm:p-14">
        <h2 className="text-4xl font-semibold tracking-[-0.03em] sm:text-6xl">
          Ready for a live session?
        </h2>
        <p className="mx-auto mt-5 max-w-2xl text-lg leading-8 text-white/60">
          Open the dashboard, wake the backend when configured, and start a
          realtime bilingual capture session.
        </p>
        <a
          href="/app"
          className="mt-8 inline-flex rounded-full bg-white px-7 py-3 text-sm font-semibold text-black transition hover:bg-emerald-100"
        >
          Launch LiveCap
        </a>
      </div>
    </section>
  );
}
