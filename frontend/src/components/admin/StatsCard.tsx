import type { ReactNode } from 'react';

export interface StatsCardProps {
  icon: ReactNode;
  label: string;
  value: string | number;
  subText?: string;
}

export function StatsCard({ icon, label, value, subText }: StatsCardProps) {
  return (
    <div className="rounded-2xl border border-[#dce5f2] bg-white shadow-sm p-6">
      <div className="flex items-start gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#0a9c88]/10 text-[#0a9c88]">
          {icon}
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-[#102247]/60 uppercase tracking-wide">
            {label}
          </p>
          <p className="mt-1 text-2xl font-bold text-[#102247]">
            {value}
          </p>
          {subText && (
            <p className="mt-1 text-xs text-[#102247]/50">
              {subText}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
