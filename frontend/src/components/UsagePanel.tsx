import { useEffect, useState } from 'react';
import { CalendarDays, LoaderCircle } from 'lucide-react';
import { authenticatedFetch } from '../services/authService';

interface UsageData {
  sessions_used: number;
  limits: {
    max_sessions_per_week: number;
    unlimited_session_duration: boolean;
  };
  quota_error: string | null;
}

export default function UsagePanel() {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const baseUrl = String(import.meta.env.VITE_API_BASE_URL ?? '').trim();
        const res = await authenticatedFetch(`${baseUrl}/api/usage`);
        if (res.ok) setUsage(await res.json() as UsageData);
      } catch { /* silent */ }
      finally { setLoading(false); }
    })();
  }, []);

  if (loading) {
    return (
      <div className="px-6 py-4 border-t border-[#dce5f2]">
        <div className="flex items-center gap-2 text-xs text-ink-muted">
          <LoaderCircle className="h-3 w-3 animate-spin" /> Loading usage...
        </div>
      </div>
    );
  }

  if (!usage) return null;

  const sessionsMax = usage.limits.max_sessions_per_week;
  const sessionsPercent = Math.min(100, (usage.sessions_used / sessionsMax) * 100);

  return (
    <div className="px-6 py-5 border-t border-[#dce5f2]">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-emerald-pro" />
          <span className="text-sm font-bold text-ink">Weekly sessions</span>
        </div>
        <span className="rounded-full bg-emerald-pro/10 px-2.5 py-1 text-[11px] font-bold text-emerald-pro">5 / week</span>
      </div>

      {/* Usage bars */}
      <div className="mt-4 space-y-3">
        <UsageBar label="Sessions this week" used={usage.sessions_used} max={sessionsMax} percent={sessionsPercent} />
      </div>

      {/* Quota warning */}
      {usage.quota_error && (
        <div className="mt-3 rounded-lg bg-red-50 p-2.5 text-xs text-crimson">
          {usage.quota_error}
        </div>
      )}

      <p className="mt-3 text-[11px] text-ink-muted">
        No time limit per recording. Allowance resets every Monday.
      </p>
    </div>
  );
}

function UsageBar({ label, used, max, percent }: { label: string; used: number; max: number; percent: number }) {
  const isNearLimit = percent >= 80;
  const barColor = isNearLimit ? 'bg-amber-400' : 'bg-emerald-pro';

  return (
    <div>
      <div className="flex items-center justify-between text-[11px]">
        <span className="font-semibold text-ink-muted">{label}</span>
        <span className={`font-mono ${isNearLimit ? 'text-amber-600' : 'text-ink-muted'}`}>
          {used}/{max}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-[#e8eef6]">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
