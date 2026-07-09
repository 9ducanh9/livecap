import { useEffect, useRef, useState } from 'react';
import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';

gsap.registerPlugin(ScrollTrigger);

export default function LandingPage() {
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!rootRef.current) return;

    const ctx = gsap.context(() => {
      // 1. Hero Entrance
      gsap.from('.reveal-up', {
        y: 40,
        autoAlpha: 0,
        duration: 1.2,
        stagger: 0.1,
        ease: 'expo.out'
      });

      // 2. Background Blob Drift
      gsap.to('.hero-blob', {
        x: "random(-100, 100)",
        y: "random(-100, 100)",
        scale: "random(0.9, 1.1)",
        duration: 15,
        repeat: -1,
        yoyo: true,
        ease: 'sine.inOut',
        stagger: {
          each: 2,
          from: 'random'
        }
      });

      // 3. Workflow Scroll Line
      gsap.to('#drawing-line', {
        scaleY: 1,
        ease: 'none',
        scrollTrigger: {
          trigger: '#workflow',
          start: 'top 40%',
          end: 'bottom 60%',
          scrub: true
        }
      });

      // 4. Orbit Rotation
      gsap.to('.orbiting-item-wrapper', {
        rotate: 360,
        duration: 60,
        repeat: -1,
        ease: 'none'
      });

      gsap.to('.orbiting-item', {
        rotate: -360,
        duration: 60,
        repeat: -1,
        ease: 'none'
      });

      // 5. Precision Hover Sync (via CSS or GSAP, let's use GSAP for interaction if needed)
      // Tooltips are handled by CSS/React state in this version for simplicity but can be GSAP
    }, rootRef);

    return () => ctx.revert();
  }, []);

  return (
    <div ref={rootRef} className="bg-white text-navy-pro font-['Be_Vietnam_Pro'] selection:bg-verdigris/20 selection:text-verdigris overflow-x-clip">
      <Navbar />
      <Hero />
      <Workflow />
      <UseCases />
      <Precision />
      <Infrastructure />
      <Footer />
    </div>
  );
}

function Navbar() {
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <nav className={`fixed top-0 left-0 w-full z-50 px-8 py-6 flex justify-between items-center transition-all duration-300 ${isScrolled ? 'bg-white/80 backdrop-blur-md border-b border-navy-pro/5 py-4' : 'bg-transparent'}`}>
      <div className="text-xl font-bold tracking-tighter text-navy-pro font-instrument">LIVECAP</div>
      <div className="hidden md:flex gap-10 text-[11px] font-bold uppercase tracking-widest text-navy-pro/60">
        <a href="#hero" className="hover:text-verdigris transition-colors">Intro</a>
        <a href="#workflow" className="hover:text-verdigris transition-colors">Flow</a>
        <a href="#use-cases" className="hover:text-verdigris transition-colors">Domains</a>
        <a href="#precision" className="hover:text-verdigris transition-colors">Accuracy</a>
        <a href="#infrastructure" className="hover:text-verdigris transition-colors">Stack</a>
      </div>
      <button className="bg-verdigris text-white px-8 py-3 text-[11px] font-bold uppercase tracking-widest hover:bg-navy-pro transition-colors">
        Start Interface
      </button>
    </nav>
  );
}

function Hero() {
  return (
    <section id="hero" className="relative min-h-screen flex items-center px-8 pt-20 overflow-hidden">
      {/* Aurora Blobs */}
      <div className="absolute right-[-15%] top-[10%] w-full h-full pointer-events-none overflow-visible opacity-60">
        <div className="hero-blob absolute top-[5%] right-[20%] w-[800px] h-[800px] bg-baby-blue/30 rounded-full blur-[180px]"></div>
        <div className="hero-blob absolute bottom-[15%] right-[10%] w-[700px] h-[700px] bg-lavender-pro/25 rounded-full blur-[160px]"></div>
      </div>

      <div className="relative z-10 w-full max-w-7xl mx-auto grid grid-cols-12 gap-8 items-center">
        <div className="col-span-12 lg:col-span-7">
          <h1 className="reveal-up font-instrument text-[clamp(4rem,12vw,9.5rem)] font-bold leading-[0.85] tracking-tighter text-navy-pro mb-8">
            Precision<br />Real Time
          </h1>

          {/* pulsating bars below slogan */}
          <div className="reveal-up flex items-center gap-4 mb-16">
            <div className="flex gap-1">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="w-1 bg-verdigris rounded-full h-3 animate-[hero-pulse_1s_infinite_alternate]" style={{ animationDelay: `${i * 0.1}s` }} />
              ))}
            </div>
            <span className="text-[11px] font-bold uppercase tracking-[0.3em] text-verdigris">Live Stream Active</span>
          </div>

          <div className="reveal-up flex flex-wrap gap-12 items-center">
            <button className="bg-navy-pro text-white px-14 py-7 text-xl font-bold hover:bg-verdigris transition-all duration-500 group flex items-center gap-6 shadow-2xl">
              Launch Interface
              <i className="ti ti-arrow-right group-hover:translate-x-1 transition-transform"></i>
            </button>
            <div className="space-y-2">
              <div className="text-[11px] font-bold uppercase tracking-[0.4em] text-navy-pro/50">LIVECAP ENGINE V4.8</div>
              <div className="flex items-center gap-4">
                <span className="text-3xl font-bold text-verdigris font-instrument leading-none">98.5%</span>
                <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-navy-pro/40 leading-none">Global Accuracy <br /> Word Recall</span>
              </div>
            </div>
          </div>
        </div>

        <div className="col-span-12 lg:col-span-5 relative reveal-up mt-12 lg:mt-0">
          <div className="backdrop-blur-2xl bg-white/45 border border-navy-pro/5 shadow-[0_32px_64px_-16px_rgba(1,31,91,0.08)] rounded-3xl p-10 overflow-hidden relative">
            <div className="flex justify-between items-center mb-12">
              <div className="flex items-center gap-3">
                <div className="w-2.5 h-2.5 bg-verdigris rounded-full animate-pulse shadow-[0_0_12px_rgba(0,166,147,0.5)]"></div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-navy-pro">System Monitor</span>
              </div>
              <span className="text-[9px] font-mono text-navy-pro/40 uppercase tracking-tighter">Instance: US-EAST-1 // 884-X</span>
            </div>

            <div className="space-y-8 h-48 overflow-y-auto no-scrollbar">
              <div className="space-y-3 opacity-40">
                <p className="text-[10px] font-bold text-verdigris uppercase tracking-wider">Source // VI</p>
                <p className="text-xl font-medium text-navy-pro">"Xác nhận dữ liệu đồng bộ thành công."</p>
              </div>
              <div className="space-y-3 pl-6 border-l-2 border-verdigris">
                <p className="text-[10px] font-bold text-verdigris uppercase tracking-wider">Output // EN</p>
                <p className="text-2xl font-bold text-navy-pro tracking-tight">"Confirming data synchronization success."</p>
              </div>
            </div>

            <div className="mt-12 flex justify-between items-end">
              <div className="flex gap-1.5 items-end h-8">
                <div className="w-1.5 bg-baby-blue rounded-full h-1/2 animate-[bounce_1s_infinite]"></div>
                <div className="w-1.5 bg-lavender-pro rounded-full h-full animate-[bounce_1.2s_infinite]"></div>
                <div className="w-1.5 bg-verdigris rounded-full h-1/3 animate-[bounce_0.8s_infinite]"></div>
                <div className="w-1.5 bg-navy-pro/10 rounded-full h-3/4"></div>
              </div>
              <div className="text-right">
                <p className="text-[9px] font-bold text-navy-pro/30 uppercase tracking-widest mb-1">Latency</p>
                <p className="text-lg font-bold text-navy-pro">14ms <span className="text-[10px] font-medium text-verdigris">NORMAL</span></p>
              </div>
            </div>
          </div>
        </div>
      </div>
      <style>{`
        @keyframes hero-pulse {
          from { height: 12px; }
          to { height: 32px; }
        }
      `}</style>
    </section>
  );
}

function Workflow() {
  const steps = [
    { num: '01', label: 'Ingress', title: 'Edge Handshake', desc: 'Capture raw PCM streams via encrypted WebSocket nodes for sub-10ms ingress latency.' },
    { num: '02', label: 'Processing', title: 'Linguistic Engine', desc: 'Multi-layered acoustic models isolate domain terms using Llama-powered attention heads.' },
    { num: '03', label: 'Mapping', title: 'Precision Mapping', desc: 'Bilingual synthesis with 99.5% terminology recall across specialized domains like telehealth and corporate law.' },
    { num: '04', label: 'Artifacts', title: 'Verified Artifacts', desc: 'Finalized sessions are compiled into immutable audit logs with automated 14-day data lifecycle management.' }
  ];

  return (
    <section id="workflow" className="py-48 bg-[#FAFAFA] relative">
      <div className="max-w-6xl mx-auto px-8 relative">
        <div className="mb-48 grid grid-cols-1 md:grid-cols-2 gap-16 items-start">
          <div className="reveal-up">
            <div className="flex items-center gap-4 mb-8">
              <span className="w-12 h-px bg-verdigris"></span>
              <h2 className="text-[11px] font-bold uppercase tracking-[0.4em] text-verdigris">The Capture Pipeline</h2>
            </div>
            <h3 className="font-instrument text-8xl font-bold tracking-tighter text-navy-pro leading-[0.85]">Orchestration.</h3>
          </div>
          <div className="reveal-up md:pt-16">
            <p className="text-xl text-navy-pro/60 leading-relaxed font-medium">LiveCap transforms ambient audio into deterministic artifacts via a secure, high-availability architecture.</p>
          </div>
        </div>

        <div className="relative min-h-[1600px]">
          <div id="feature-ladder" className="absolute left-1/2 top-0 bottom-0 w-[1px] bg-navy-pro/20 -translate-x-1/2 overflow-hidden">
            <div id="drawing-line" className="absolute top-0 left-0 w-full bg-verdigris h-full origin-top scale-y-0 shadow-[0_0_10px_rgba(0,166,147,0.5)]"></div>
          </div>

          <div className="space-y-48">
            {steps.map((step, i) => (
              <div key={i} className={`reveal-up flex items-center ${i % 2 === 0 ? 'justify-start' : 'justify-end'} relative w-full group`}>
                <div className={`w-full md:w-1/2 ${i % 2 === 0 ? 'md:pr-32 text-right' : 'md:pl-32 text-left'} relative`}>
                  <div className={`hidden md:block absolute ${i % 2 === 0 ? 'right-0' : 'left-0'} top-1/2 w-32 h-px bg-navy-pro/20`}>
                    <div className={`absolute ${i % 2 === 0 ? 'right-0' : 'left-0'} top-1/2 -translate-y-1/2 w-1.5 h-1.5 rounded-full bg-navy-pro/20`}></div>
                  </div>
                  <div className="p-12 bg-white border border-navy-pro/10 hover:border-verdigris/30 transition-colors duration-500 rounded-none shadow-sm group-hover:shadow-xl group-hover:-translate-y-2 transform-gpu">
                    <span className="text-[10px] font-bold text-verdigris uppercase tracking-widest mb-6 block">{step.num} / {step.label}</span>
                    <h4 className="text-3xl font-bold text-navy-pro mb-6 font-instrument">{step.title}</h4>
                    <p className="text-base text-navy-pro/60 leading-relaxed">{step.desc}</p>
                  </div>
                </div>
                <div className="absolute left-1/2 -translate-x-1/2 w-4 h-4 rounded-full border-2 border-verdigris bg-white z-10 shadow-lg"></div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

function UseCases() {
  return (
    <section id="use-cases" className="py-48 bg-white overflow-hidden">
      <div className="max-w-7xl mx-auto px-8">
        <div className="mb-40 flex flex-col items-center text-center">
          <div className="reveal-up flex items-center gap-4 mb-8">
            <span className="w-12 h-px bg-verdigris"></span>
            <h2 className="text-[11px] font-bold uppercase tracking-[0.4em] text-verdigris">Vertical Focus</h2>
            <span className="w-12 h-px bg-verdigris"></span>
          </div>
          <h3 className="reveal-up font-instrument text-8xl font-bold tracking-tighter text-navy-pro leading-[0.85] max-w-4xl">Built for Specialized Intent.</h3>
        </div>

        <div className="grid grid-cols-12 gap-8 lg:h-[900px]">
          <div className="reveal-up col-span-12 lg:col-span-8 relative group rounded-[3rem] overflow-hidden border border-navy-pro/10">
            <video src="https://videos.pexels.com/video-files/33481534/14243327_640_360_25fps.mp4" autoPlay muted loop playsInline className="absolute inset-0 w-full h-full object-cover grayscale opacity-20 group-hover:opacity-40 transition-opacity duration-[2000ms]"></video>
            <div className="absolute inset-0 bg-gradient-to-tr from-white/95 via-white/50 to-transparent"></div>
            <div className="absolute inset-0 p-16 flex flex-col justify-end items-start">
              <div className="backdrop-blur-3xl bg-white/60 border border-white/80 p-14 max-w-xl rounded-[2.5rem] shadow-2xl relative overflow-hidden">
                <span className="inline-block px-5 py-2 bg-verdigris text-white text-[10px] font-bold uppercase tracking-[0.2em] mb-12">Critical Path // Medical</span>
                <h4 className="text-5xl font-instrument font-bold text-navy-pro mb-8 leading-tight">Telehealth Surgery.</h4>
                <p className="text-lg text-navy-pro/70 leading-relaxed font-medium mb-12">Ensuring 99% terminology accuracy for mission-critical medical consultations across global regions.</p>
                <div className="flex items-center justify-between py-5 px-8 bg-navy-pro/5 rounded-2xl border border-navy-pro/5">
                  <div className="flex items-center gap-4">
                    <div className="w-2.5 h-2.5 rounded-full bg-verdigris animate-pulse"></div>
                    <span className="text-sm font-bold text-navy-pro/70">Recalling Terminology...</span>
                  </div>
                  <span className="text-[10px] font-mono text-navy-pro/30 uppercase">Latency: 12ms</span>
                </div>
              </div>
            </div>
          </div>

          <div className="col-span-12 lg:col-span-4 flex flex-col gap-8">
            <div className="reveal-up flex-1 rounded-[3rem] border border-navy-pro/10 p-14 flex flex-col justify-center bg-[#FAFAFA] relative overflow-hidden group">
              <div className="w-20 h-20 bg-verdigris/10 rounded-[1.5rem] flex items-center justify-center mb-10"><i className="ti ti-shield-lock text-verdigris text-4xl"></i></div>
              <h4 className="text-3xl font-bold text-navy-pro mb-6 font-instrument">Secure Discovery.</h4>
              <p className="text-lg text-navy-pro/60 leading-relaxed">E2E encrypted capturing for confidential proceedings and legal records.</p>
            </div>
            <div className="reveal-up flex-1 rounded-[3rem] border border-navy-pro/10 p-14 flex flex-col justify-center bg-[#FAFAFA] relative overflow-hidden group">
              <div className="w-20 h-20 bg-baby-blue/10 rounded-[1.5rem] flex items-center justify-center mb-10"><i className="ti ti-cpu text-baby-blue text-4xl"></i></div>
              <h4 className="text-3xl font-bold text-navy-pro mb-6 font-instrument">Architectural Sync.</h4>
              <p className="text-lg text-navy-pro/60 leading-relaxed">Sub-100ms latency for cross-border teams discussing complex systems.</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Precision() {
  const pairs = [
    { vi: 'Chúng ta bắt đầu với phần cập nhật kiến trúc.', en: 'Let us begin with the system architecture update.', term: 'cập nhật', def: 'The process of synchronizing technical architecture to current operational standards.' },
    { vi: 'Backend sẽ tự bật khi có phiên capture mới.', en: 'The backend wakes when a new capture session starts.', term: 'capture', def: 'High-fidelity 16kHz PCM audio stream ingestion via secure WebSocket tunnel.' }
  ];

  return (
    <section id="precision" className="py-48 bg-[#FAFAFA] relative">
      <div className="max-w-7xl mx-auto px-8 mb-32">
        <div className="flex flex-col md:flex-row justify-between items-end gap-12">
          <div className="reveal-up max-w-2xl">
            <h2 className="text-[11px] font-bold uppercase tracking-[0.4em] text-verdigris mb-6">03 / Benchmarks</h2>
            <h3 className="font-instrument text-7xl font-bold tracking-tighter text-navy-pro leading-[0.9]">Exactitude.</h3>
          </div>
          <div className="reveal-up border-l-2 border-verdigris pl-10">
            <p className="text-xl text-navy-pro/60 font-medium leading-relaxed">98.5% word accuracy benchmarks <br />optimized for technical lexicons.</p>
          </div>
        </div>
      </div>

      <div className="border-y border-navy-pro/10 grid grid-cols-1 md:grid-cols-2">
        <div className="p-16 lg:px-28 lg:pt-28 lg:pb-12 border-b md:border-b-0 md:border-r border-navy-pro/10">
          <h5 className="text-[10px] font-bold uppercase tracking-[0.5em] text-navy-pro/30">Source // VI</h5>
        </div>
        <div className="p-16 lg:px-28 lg:pt-28 lg:pb-12 bg-white">
          <h5 className="text-[10px] font-bold uppercase tracking-[0.5em] text-verdigris">Translation // EN</h5>
        </div>

        {pairs.map((p, i) => (
          <div key={i} className="contents">
            <div className="p-16 lg:p-28 border-b md:border-r border-navy-pro/10 flex items-center min-h-[300px]">
              <div className="reveal-up text-4xl lg:text-5xl font-light text-navy-pro/80 leading-tight">
                {p.vi.split(p.term).map((part, idx, arr) => (
                  <span key={idx}>
                    {part}
                    {idx < arr.length - 1 && (
                      <span className="inline-block border-b-2 border-dotted border-verdigris/30 cursor-help relative group">
                        {p.term}
                        <div className="tooltip-content invisible group-hover:visible opacity-0 group-hover:opacity-100 absolute bottom-full left-1/2 -translate-x-1/2 mb-4 p-6 backdrop-blur-2xl bg-white/90 border border-navy-pro/5 rounded-3xl shadow-2xl w-64 transition-all duration-300 pointer-events-none z-50">
                          <p className="text-[10px] font-bold text-verdigris uppercase tracking-widest mb-3">Diagnostic Definition</p>
                          <p className="text-sm font-medium text-navy-pro leading-relaxed">{p.def}</p>
                        </div>
                      </span>
                    )}
                  </span>
                ))}
              </div>
            </div>
            <div className="p-16 lg:p-28 bg-white border-b border-navy-pro/10 flex items-center min-h-[300px]">
              <div className="reveal-up text-4xl lg:text-5xl font-bold text-navy-pro leading-tight">{p.en}</div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function Infrastructure() {
  const nodes = [
    { label: 'Capture', icon: 'ti-microphone', detail: '< 15ms', color: 'text-verdigris', bg: 'bg-verdigris/5', angle: 0 },
    { label: 'Ingress', icon: 'ti-cloud-computing', detail: 'AWS ALB', color: 'text-baby-blue', bg: 'bg-baby-blue/5', angle: 90 },
    { label: 'Compute', icon: 'ti-server', detail: 'Fargate', color: 'text-lavender-pro', bg: 'bg-lavender-pro/5', angle: 180 },
    { label: 'Engine', icon: 'ti-replace', detail: 'Llama 3.1', color: 'text-verdigris', bg: 'bg-verdigris/5', angle: 270 }
  ];

  return (
    <section id="infrastructure" className="py-64 bg-white overflow-hidden relative">
      <div className="max-w-7xl mx-auto px-8 relative z-10">
        <div className="text-center mb-40">
          <h2 className="reveal-up text-[11px] font-bold uppercase tracking-[0.4em] text-verdigris mb-6">04 / Infrastructure</h2>
          <h3 className="reveal-up font-instrument text-7xl font-bold tracking-tighter text-navy-pro leading-[0.9]">Distributed Engine.</h3>
        </div>

        <div className="relative flex items-center justify-center h-[900px] w-full max-w-[900px] mx-auto">
          <div className="absolute w-[700px] h-[700px] border border-dashed border-navy-pro/15 rounded-full orbit-ring"></div>

          <div className="z-20 w-64 h-64 rounded-full backdrop-blur-3xl bg-white/50 border border-white shadow-[0_48px_96px_-24px_rgba(1,31,91,0.12)] flex flex-col items-center justify-center group relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-tr from-baby-blue/15 via-transparent to-lavender-pro/15 opacity-0 group-hover:opacity-100 transition-opacity duration-1000"></div>
            <div className="w-20 h-20 bg-navy-pro rounded-full flex items-center justify-center shadow-2xl mb-5 group-hover:scale-110 transition-transform duration-700">
              <i className="ti ti-activity text-white text-4xl"></i>
            </div>
            <span className="text-[10px] font-bold uppercase tracking-[0.3em] text-navy-pro">LiveCap Core</span>
            <span className="text-[10px] font-mono text-navy-pro/40 mt-1 uppercase tracking-tighter">v4.8 Stable</span>
          </div>

          <div className="orbiting-item-wrapper absolute w-full h-full">
            {nodes.map((n, i) => (
              <div key={i} className="absolute left-1/2 top-1/2" style={{ transform: `translate(-50%, -50%) rotate(${n.angle}deg) translate(350px) rotate(-${n.angle}deg)` }}>
                <div className="orbiting-item p-6 bg-white border border-navy-pro/5 shadow-xl rounded-3xl flex flex-col items-center gap-2 w-36 hover:border-verdigris/40 transition-colors">
                  <i className={`ti ${n.icon} ${n.color} text-2xl`}></i>
                  <span className="text-[10px] font-bold uppercase text-navy-pro tracking-widest">{n.label}</span>
                  <div className={`text-[9px] font-bold ${n.color} ${n.bg} px-2 py-0.5 rounded-full`}>{n.detail}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-96 pb-48 text-center bg-white relative">
        <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[400px] bg-baby-blue/5 blur-[120px] pointer-events-none"></div>
        <div className="reveal-up inline-block mb-12">
          <div className="flex items-center gap-3 px-8 py-3 bg-navy-pro/5 rounded-full border border-navy-pro/5">
            <div className="w-2.5 h-2.5 rounded-full bg-verdigris animate-pulse"></div>
            <span className="text-[11px] font-bold uppercase tracking-[0.3em] text-navy-pro/60">LiveCap Studio v4.8 Beta Active</span>
          </div>
        </div>
        <h2 className="reveal-up text-[clamp(4.5rem,11vw,11.5rem)] font-bold tracking-tighter text-navy-pro leading-[0.75] mb-24 font-instrument">Join the Stream.</h2>
        <div className="reveal-up flex flex-col md:flex-row justify-center items-center gap-12">
          <button className="bg-verdigris text-white px-16 py-8 text-2xl font-bold hover:bg-navy-pro transition-all duration-500 shadow-2xl rounded-none transform hover:scale-105 active:scale-95">
            Launch Secure Interface
          </button>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="py-20 px-8 border-t border-navy-pro/5 bg-white">
      <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-10">
        <div className="text-2xl font-bold tracking-tighter font-instrument text-navy-pro">LIVECAP</div>
        <div className="flex flex-wrap justify-center gap-12 text-[10px] font-bold uppercase tracking-[0.3em] text-navy-pro/40">
          <a href="#" className="hover:text-verdigris transition-colors">Platform</a>
          <a href="#" className="hover:text-verdigris transition-colors">Architecture</a>
          <a href="#" className="hover:text-verdigris transition-colors">Privacy</a>
          <a href="#" className="hover:text-verdigris transition-colors">Compliance</a>
        </div>
        <div className="text-[10px] font-bold text-navy-pro/30 uppercase tracking-widest">&copy; 2026 LiveCap Inc.</div>
      </div>
    </footer>
  );
}
