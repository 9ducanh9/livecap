import { useEffect, useState } from 'react';
import { BarChart3, Zap, Crown, LoaderCircle } from 'lucide-react';
import { authenticatedFetch } from '../services/authService';

interface UsageData {
  tier: string;
  sessions_used: number;
  minutes_used: number;
  limits: {
    max_sessions_per_month: number;
    max_minutes_per_session: number;
    max_minutes_per_month: number;
    meeting_notes_enabled: boolean;
  };
  quota_error: string | null;
}

const TIER_LABELS: Record<string, { label: string; color: string; icon: typeof Zap }> = {
  free: { label: 'Free', color: 'text-ink-muted', icon: BarChart3 },
  pro: { label: 'Pro', color: 'text-emerald-pro', icon: Zap },
  business: { label: 'Business', color: 'text-amber-500', icon: Crown },
  unlimited: { label: 'Unlimited', color: 'text-emerald-pro', icon: Zap },
};

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

  const tierInfo = TIER_LABELS[usage.tier] ?? TIER_LABELS.free;
  const TierIcon = tierInfo.icon;
  const sessionsMax = usage.limits.max_sessions_per_month;
  const minutesMax = usage.limits.max_minutes_per_month;
  const sessionsPercent = sessionsMax > 999_000 ? 0 : Math.min(100, (usage.sessions_used / sessionsMax) * 100);
  const minutesPercent = minutesMax > 999_000 ? 0 : Math.min(100, (usage.minutes_used / minutesMax) * 100);

  return (
    <div className="px-6 py-5 border-t border-[#dce5f2]">
      {/* Tier badge */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TierIcon className={`h-4 w-4 ${tierInfo.color}`} />
          <span className={`text-sm font-bold ${tierInfo.color}`}>{tierInfo.label}</span>
        </div>
        {usage.tier === 'free' && (
          <button
            type="button"
            className="text-[11px] font-bold text-emerald-pro bg-emerald-pro/10 px-2.5 py-1 rounded-full hover:bg-emerald-pro/20 transition-colors"
          >
            Upgrade
          </button>
        )}
      </div>

      {/* Usage bars */}
      <div className="mt-4 space-y-3">
        {sessionsMax <= 999_000 && (
          <UsageBar
            label="Sessions"
            used={usage.sessions_used}
            max={sessionsMax}
            percent={sessionsPercent}
          />
        )}
        {minutesMax <= 999_000 && (
          <UsageBar
            label="Minutes"
            used={usage.minutes_used}
            max={minutesMax}
            percent={minutesPercent}
          />
        )}
        {sessionsMax > 999_000 && minutesMax > 999_000 && (
          <p className="text-xs text-ink-muted">Unlimited usage this month</p>
        )}
      </div>

      {/* Quota warning */}
      {usage.quota_error && (
        <div className="mt-3 rounded-lg bg-red-50 p-2.5 text-xs text-crimson">
          {usage.quota_error}
        </div>
      )}

      {/* Per-session limit */}
      <p className="mt-3 text-[11px] text-ink-muted">
        Max {usage.limits.max_minutes_per_session} min per session
        {!usage.limits.meeting_notes_enabled && ' • AI notes: Pro only'}
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
