import React, { useEffect, useRef } from 'react';
import { gsap } from 'gsap';

export type BadgeStatus = 'idle' | 'active' | 'warning' | 'error' | 'connecting' | 'waking' | 'success';

interface StatusBadgeProps {
  status: BadgeStatus;
  label: string;
  pulse?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, label, pulse = true }) => {
  const dotRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const shouldPulse = pulse && (status === 'active' || status === 'connecting' || status === 'waking');

    if (shouldPulse) {
      gsap.fromTo(dotRef.current,
        { scale: 1, opacity: 0.8 },
        {
          scale: status === 'active' ? 2.5 : 1.6,
          opacity: 0,
          duration: status === 'active' ? 1.4 : 1,
          repeat: -1,
          ease: 'sine.out',
        }
      );
    } else {
      gsap.killTweensOf(dotRef.current);
      gsap.set(dotRef.current, { scale: 1, opacity: 1 });
    }
  }, [status, pulse]);

  const colors = {
    idle: 'text-white/50 border-white/10 bg-white/5',
    active: 'text-crimson border-crimson/30 bg-crimson/10',
    warning: 'text-amber-400 border-amber-400/30 bg-amber-400/10',
    error: 'text-rose-500 border-rose-500/30 bg-rose-500/10',
    connecting: 'text-sky-400 border-sky-400/30 bg-sky-400/10',
    waking: 'text-purple-400 border-purple-400/30 bg-purple-400/10',
    success: 'text-emerald-pro border-emerald-pro/30 bg-emerald-pro/10',
  };

  const dotColors = {
    idle: 'bg-white/40',
    active: 'bg-crimson shadow-[0_0_10px_#E11D48]',
    warning: 'bg-amber-400',
    error: 'bg-rose-500',
    connecting: 'bg-sky-400',
    waking: 'bg-purple-400',
    success: 'bg-emerald-pro shadow-[0_0_8px_#059669]',
  };

  return (
    <div className={`inline-flex items-center gap-2.5 border px-3 py-1.5 font-mono text-[9px] font-bold uppercase tracking-[0.25em] backdrop-blur-sm ${colors[status]}`}>
      <span className="relative flex h-2 w-2">
        <span
          ref={dotRef}
          className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${dotColors[status]}`}
        />
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dotColors[status]}`} />
      </span>
      {label}
    </div>
  );
};
