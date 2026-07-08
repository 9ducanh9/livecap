import { useEffect, useRef } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { ProButton } from './ui';
import { Activity, Mic, Zap, Cpu, MessageSquare, Languages, Download, ArrowRight, Layers, CheckCircle2, Info, ShieldAlert } from 'lucide-react';

gsap.registerPlugin(ScrollTrigger);

const mockupSteps = [
  {
    eyebrow: 'Step 01',
    title: 'Microphone connected',
    body: 'Capture starts only after the backend is awake and the WebSocket is ready.',
    primary: 'Default microphone',
    secondary: '16 kHz PCM stream ready',
    icon: <Mic className="w-4 h-4" />,
  },
  {
    eyebrow: 'Step 02',
    title: 'Vietnamese speech appears',
    body: 'Finalized source captions are appended as meeting participants speak.',
    primary: 'Nghe rõ mọi ý trong cuộc họp.',
    secondary: 'Speaker 1 · 00:14',
    icon: <MessageSquare className="w-4 h-4" />,
  },
  {
    eyebrow: 'Step 03',
    title: 'English translation appears',
    body: 'LiveCap renders the translated line beside the original text.',
    primary: 'Understand every point in the meeting.',
    secondary: 'Speaker 1 · 00:14',
    icon: <Languages className="w-4 h-4" />,
  },
  {
    eyebrow: 'Step 04',
    title: 'Export TXT becomes ready',
    body: 'When the session ends, finalized lines can be exported through the backend.',
    primary: 'Transcript exported',
    secondary: 'Presigned TXT link ready',
    icon: <Download className="w-4 h-4" />,
  },
] as const;

const architectureNodes = [
  { id: 'mic', label: 'Microphone', icon: <Mic className="w-4 h-4" /> },
  { id: 'cf', label: 'CloudFront', icon: <Zap className="w-4 h-4" /> },
  { id: 'alb', label: 'ALB', icon: <Cpu className="w-4 h-4" /> },
  { id: 'ecs', label: 'ECS Fargate', icon: <Layers className="w-4 h-4" /> },
  { id: 'tr', label: 'Transcribe', icon: <Activity className="w-4 h-4" /> },
  { id: 'tl', label: 'Translate', icon: <Languages className="w-4 h-4" /> },
  { id: 'lc', label: 'Live Caption', icon: <CheckCircle2 className="w-4 h-4" /> },
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

const useCases = [
  {
    title: 'Telehealth',
    desc: 'Bilingual sessions between specialists and patients with medical-grade terminology accuracy.',
    metric: '99% Terminology Recall',
  },
  {
    title: 'Legal Council',
    desc: 'E2E encrypted transcription for confidential proceedings with automated data purging.',
    metric: 'SOC2 Type II Compliant',
  },
  {
    title: 'Engineering',
    desc: 'Ultra-low latency syncing for cross-border sprint planning and technical specifications.',
    metric: '<100ms Stream Latency',
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
        y: 40,
        autoAlpha: 0,
        duration: 1.2,
        ease: 'power4.out',
      });

      const mockupStepsEls = gsap.utils.toArray<HTMLElement>('.mockup-step');

      const mockupTimeline = gsap.timeline({
        scrollTrigger: {
          trigger: '.mockup-section',
          start: 'top top',
          end: '+=1800',
          scrub: 1,
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
              y: -40,
              scale: 0.95,
              filter: 'blur(10px)',
              duration: 0.5,
            },
            index,
          )
          .fromTo(
            step,
            { autoAlpha: 0, y: 40, scale: 0.95, filter: 'blur(10px)' },
            {
              autoAlpha: 1,
              y: 0,
              scale: 1,
              filter: 'blur(0px)',
              duration: 0.5,
            },
            index,
          );
      });

      gsap.from('.transcript-line', {
        y: 30,
        autoAlpha: 0,
        filter: 'blur(8px)',
        stagger: 0.15,
        duration: 1,
        ease: 'power3.out',
        scrollTrigger: {
          trigger: '.transcript-section',
          start: 'top 80%',
        },
      });

      // Architecture Pulse
      const paths = gsap.utils.toArray<SVGPathElement>('.arch-path');
      paths.forEach((path) => {
        const length = path.getTotalLength();
        gsap.set(path, { strokeDasharray: length, strokeDashoffset: length });

        gsap.to(path, {
          strokeDashoffset: 0,
          duration: 2,
          repeat: -1,
          ease: 'power1.inOut',
          scrollTrigger: {
            trigger: '.architecture-section',
            start: 'top 70%',
          }
        });
      });

      const nodes = gsap.utils.toArray<HTMLElement>('.architecture-node');
      nodes.forEach((node, i) => {
        gsap.from(node, {
          autoAlpha: 0,
          y: 20,
          duration: 0.8,
          delay: i * 0.08,
          scrollTrigger: {
            trigger: '.architecture-section',
            start: 'top 85%',
          },
        });
      });
    }, rootRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={rootRef} className="bg-obsidian text-white font-ui selection:bg-crimson selection:text-white antialiased">
      <LandingNav />
      <HeroSection />
      <PinnedMockupSection />
      <UseCasesSection />
      <TranscriptAnimationSection />
      <ArchitectureSection />
      <FinalCtaSection />
      <SectionNav />
    </div>
  );
}

function LandingNav() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-[100] border-b border-white/5 bg-obsidian/40 backdrop-blur-xl">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 sm:px-10">
        <a href="/" className="text-xl font-bold tracking-tighter flex items-center gap-2">
          <Activity className="w-5 h-5 text-crimson" />
          LIVECAP
        </a>
        <div className="flex items-center gap-6">
          <a href="#architecture" className="hidden text-[10px] font-bold uppercase tracking-widest text-white/60 hover:text-white sm:block">Architecture</a>
          <a
            href="/app"
            className="font-mono text-[10px] uppercase tracking-widest border border-white/20 px-4 py-2 hover:bg-white hover:text-black transition-colors"
          >
            Launch App
          </a>
        </div>
      </div>
    </nav>
  );
}

function SectionNav() {
  const sections = [
    { id: 'hero', label: 'Intro' },
    { id: 'flow', label: 'Flow' },
    { id: 'use-cases', label: 'Domains' },
    { id: 'precision', label: 'Accuracy' },
    { id: 'architecture', label: 'Stack' },
  ];

  return (
    <div className="fixed right-6 top-1/2 z-[100] hidden -translate-y-1/2 space-y-4 lg:block">
      {sections.map((s) => (
        <a
          key={s.id}
          href={`#${s.id}`}
          className="group flex items-center justify-end gap-3 outline-none"
        >
          <span className="text-[9px] font-bold uppercase tracking-widest opacity-0 transition-opacity group-hover:opacity-60 text-white/80">
            {s.label}
          </span>
          <div className="h-1 w-4 bg-white/10 transition-all group-hover:w-8 group-hover:bg-crimson" />
        </a>
      ))}
    </div>
  );
}

function HeroSection() {
  return (
    <section id="hero" className="hero-section relative flex min-h-[90vh] overflow-hidden px-6 py-12 sm:px-10 items-center justify-center">
      {/* Background Video */}
      <div className="absolute inset-0 z-0">
        <video
          autoPlay
          muted
          loop
          playsInline
          className="h-full w-full object-cover opacity-50 grayscale"
          poster="https://images.pexels.com/videos/28561007/3d-4k-abstract-backdrop-28561007.jpeg?auto=compress&cs=tinysrgb&fit=crop&h=630&w=1200"
        >
          <source src="https://videos.pexels.com/video-files/28561007/12421211_640_360_30fps.mp4" type="video/mp4" />
        </video>
        <div className="absolute inset-0 bg-gradient-to-b from-obsidian/30 via-obsidian/50 to-obsidian" />
      </div>

      <div className="absolute inset-0 z-0 bg-[linear-gradient(rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:80px_80px]" />

      <div className="relative z-10 mx-auto flex w-full max-w-7xl flex-col items-center">
        <div className="hero-copy flex flex-col items-center text-center">
          <p className="mb-6 font-mono text-[10px] uppercase tracking-[0.4em] text-white/60 flex items-center gap-3">
            <span className="w-8 h-px bg-white/20" />
            Bilingual Processing
            <span className="w-8 h-px bg-white/20" />
          </p>
          <h1 className="max-w-5xl text-6xl font-bold tracking-tighter text-white sm:text-8xl lg:text-9xl uppercase leading-[0.85]">
            Precision. <br /> Real Time.
          </h1>
          <p className="mt-10 max-w-2xl text-lg leading-relaxed text-white/70 font-light">
            Sub-100ms latency translation for Vietnamese and English.
            98.5% word accuracy powered by private secure compute.
          </p>
          <div className="mt-12 flex flex-col gap-4 sm:flex-row">
            <ProButton variant="primary" size="lg" onClick={() => window.location.href = '/app'} className="min-w-[200px]">
              Start Capturing
            </ProButton>
            <ProButton variant="outline" size="lg" onClick={() => document.getElementById('flow')?.scrollIntoView({ behavior: 'smooth' })} className="min-w-[200px]">
              How it works
            </ProButton>
          </div>
        </div>
      </div>
    </section>
  );
}

function PinnedMockupSection() {
  return (
    <section id="flow" className="mockup-section relative min-h-screen px-6 py-12 sm:px-10">
      <div className="mx-auto grid h-full min-h-[700px] w-full max-w-7xl gap-16 lg:grid-cols-[0.7fr_1.3fr] lg:items-center">
        <div className="z-10 bg-obsidian py-4 lg:bg-transparent">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.4em] text-crimson">
            01 / Workflow
          </p>
          <h2 className="mt-6 text-5xl font-bold tracking-tighter uppercase sm:text-7xl leading-tight">
            Stream <br /> Context.
          </h2>
          <p className="mt-8 max-w-lg text-lg leading-relaxed text-white/70 font-light">
            LiveCap orchestrates browser audio and AWS managed speech services
            to deliver contextual bilingual transcripts as you speak.
          </p>
        </div>

        <div className="relative min-h-[500px] border border-white/10 bg-white/[0.03] p-3 backdrop-blur-pro">
          <div className="h-full border border-white/5 bg-black/60 p-6 sm:p-10">
            <div className="mb-8 flex items-center justify-between border-b border-white/10 pb-8">
              <div>
                <p className="font-mono text-xs font-bold uppercase tracking-widest">Global Stream</p>
                <p className="mt-2 font-mono text-[9px] text-white/50 tracking-widest uppercase">ESTABLISHED: SECURE ENCRYPTED</p>
              </div>
              <div className="flex items-center gap-3 font-mono text-[10px] text-crimson font-bold">
                <span className="h-2 w-2 rounded-full bg-crimson animate-ping" />
                LIVE
              </div>
            </div>

            <div className="relative min-h-[350px] overflow-hidden">
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

function UseCasesSection() {
  return (
    <section id="use-cases" className="px-6 py-20 sm:px-10 border-t border-white/5">
      <div className="mx-auto max-w-7xl">
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.4em] text-crimson">
          01.5 / Domains
        </p>
        <h2 className="mt-6 text-5xl font-bold tracking-tighter uppercase sm:text-7xl leading-tight">
          Built for <br /> Specialists.
        </h2>

        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {useCases.map((uc) => (
            <div key={uc.title} className="group border border-white/10 bg-white/[0.02] p-8 hover:bg-white/[0.05] transition-all">
              <div className="text-emerald-pro font-mono text-[10px] font-bold uppercase tracking-widest mb-8 flex items-center gap-2">
                <ShieldAlert className="w-3.5 h-3.5" />
                {uc.metric}
              </div>
              <h3 className="text-xl font-bold uppercase tracking-tighter text-white/90 mb-4">{uc.title}</h3>
              <p className="text-sm text-white/50 leading-relaxed font-light">{uc.desc}</p>
            </div>
          ))}
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
  icon,
}: {
  eyebrow: string;
  title: string;
  body: string;
  primary: string;
  secondary: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="mockup-step absolute inset-0 flex flex-col justify-between">
      <div>
        <div className="flex items-center gap-3">
          <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-crimson font-bold">
            {eyebrow}
          </p>
          <div className="h-px flex-1 bg-white/10" />
        </div>
        <h3 className="mt-4 text-3xl font-bold tracking-tighter text-white uppercase leading-tight">
          {title}
        </h3>
        <p className="mt-4 max-w-md text-sm leading-relaxed text-white/70 font-light">{body}</p>
      </div>

      <div className="border border-white/10 bg-white/5 p-6 mt-8">
        <div className="flex items-center justify-between mb-4">
          <p className="font-mono text-[9px] uppercase tracking-widest text-white/40">
            Node Data
          </p>
          <div className="text-white/30">{icon}</div>
        </div>
        <p className="text-xl sm:text-2xl font-mono tracking-tight text-white leading-snug">
          {primary}
        </p>
        <p className="mt-4 font-mono text-[9px] text-emerald-pro uppercase tracking-widest font-bold bg-emerald-pro/10 px-2 py-1 inline-block">
          {secondary}
        </p>
      </div>
    </div>
  );
}

function TranscriptAnimationSection() {
  return (
    <section id="precision" className="transcript-section px-6 py-20 sm:px-10 border-y border-white/5 bg-white/[0.01]">
      <div className="mx-auto grid max-w-7xl gap-16 lg:grid-cols-[0.8fr_1.2fr] lg:items-start">
        <div className="sticky top-24">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.4em] text-crimson">
            02 / Quality
          </p>
          <h2 className="mt-6 text-5xl font-bold tracking-tighter uppercase leading-tight sm:text-7xl">
            Extreme <br /> Precision.
          </h2>
          <p className="mt-8 text-lg leading-relaxed text-white/70 font-light max-w-md">
            LiveCap leverages AWS Transcribe Medical and custom-tuned Transformer models to achieve 98.5% accuracy on technical domain vocabulary.
          </p>
          <div className="mt-10 flex gap-4 border border-white/5 bg-white/[0.02] p-4 max-w-xs">
            <Info className="w-4 h-4 text-white/30 shrink-0" />
            <p className="text-[10px] leading-relaxed text-white/50 uppercase tracking-wider">
              Privacy first: data is encrypted in transit and purged after 14 days.
            </p>
          </div>
        </div>

        <div className="space-y-4">
          {transcriptLines.map((line) => (
            <div
              key={line.vi}
              className="transcript-line border border-white/10 bg-white/[0.03] p-8 backdrop-blur-pro"
            >
              <div className="mb-6 flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.3em] text-white/40">
                <span className="flex items-center gap-2">
                  <Activity className="w-3 h-3" />
                  {line.speaker}
                </span>
                <span className="text-emerald-pro font-bold tracking-widest uppercase">Finalized</span>
              </div>
              <div className="grid gap-8 md:grid-cols-2">
                <div className="space-y-3">
                  <span className="text-[8px] font-mono text-white/40 uppercase tracking-widest font-bold">SOURCE // VI</span>
                  <p className="text-lg leading-relaxed text-white font-mono tracking-tight">{line.vi}</p>
                </div>
                <div className="space-y-3">
                  <span className="text-[8px] font-mono text-emerald-pro/50 uppercase tracking-widest font-bold">TRANS // EN</span>
                  <p className="text-lg leading-relaxed text-emerald-pro/80 font-mono tracking-tight">{line.en}</p>
                </div>
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
    <section id="architecture" className="architecture-section px-6 py-20 sm:px-10">
      <div className="mx-auto max-w-7xl">
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.4em] text-crimson">
          03 / Infrastructure
        </p>
        <h2 className="mt-6 max-w-3xl text-5xl font-bold tracking-tighter uppercase sm:text-7xl leading-tight">
          Cloud Path.
        </h2>

        <div className="mt-16 grid gap-4 sm:grid-cols-2 lg:grid-cols-7 lg:items-center">
          {architectureNodes.map((node, index) => (
            <div key={node.id} className="relative flex items-center lg:block">
              <div className="architecture-node group relative z-10 w-full border border-white/10 bg-white/[0.03] p-6 transition-all hover:border-crimson/40">
                <div className="flex items-center justify-between mb-4">
                  <div className="font-mono text-[9px] text-white/30 uppercase tracking-widest font-bold">
                    {String(index + 1).padStart(2, '0')}
                  </div>
                  <div className="text-white/30 group-hover:text-crimson transition-colors">{node.icon}</div>
                </div>
                <div className="mt-4 text-[10px] font-bold uppercase tracking-widest text-white/80 group-hover:text-white transition-colors">
                  {node.label}
                </div>
              </div>

              {index < architectureNodes.length - 1 && (
                <div className="absolute left-[calc(100%-8px)] top-1/2 z-0 hidden h-px w-full lg:block">
                  <svg className="h-px w-full overflow-visible">
                    <path
                      d="M 0 0.5 L 64 0.5"
                      stroke="white"
                      strokeWidth="1"
                      strokeOpacity="0.1"
                      fill="none"
                      className="arch-path"
                    />
                  </svg>
                  <ArrowRight className="absolute right-0 -top-2 w-4 h-4 text-white/10" />
                </div>
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
    <section className="px-6 py-20 sm:px-10">
      <div className="mx-auto max-w-5xl border border-white/10 bg-white/[0.02] p-12 text-center sm:p-24 relative overflow-hidden">
        <div className="absolute inset-0 z-0 pointer-events-none opacity-10">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[400px] w-[400px] rounded-full bg-crimson blur-[120px]" />
        </div>

        <div className="relative z-10">
          <h2 className="text-5xl font-bold tracking-tighter uppercase sm:text-8xl leading-none">
            Join the <br /> Stream.
          </h2>
          <p className="mx-auto mt-8 max-w-2xl text-lg leading-relaxed text-white/60 font-light">
            Launch the secure bilingual dashboard to start captioning.
          </p>
          <div className="mt-12 flex flex-col items-center gap-4">
            <ProButton variant="primary" size="lg" onClick={() => window.location.href = '/app'} className="min-w-[240px]">
              Launch Dashboard
            </ProButton>
            <p className="text-[10px] font-mono text-white/40 uppercase tracking-widest">No Registration Required</p>
          </div>
        </div>
      </div>
    </section>
  );
}
