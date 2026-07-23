import { useCallback, useEffect, useState } from 'react';
import { BarChart3, Zap, Crown, LoaderCircle, AlertCircle } from 'lucide-react';
import { authenticatedFetch } from '../services/authService';
import { startCheckout, openBillingPortal, BillingError } from '../services/billingService';

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
  business: { label: 'Plus', color: 'text-amber-500', icon: Crown },
  unlimited: { label: 'Unlimited', color: 'text-emerald-pro', icon: Zap },
};

export default function UsagePanel() {
  const [usage, setUsage] = useState<UsageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [showTierChoice, setShowTierChoice] = useState(false);
  const [billingBusy, setBillingBusy] = useState(false);
  const [billingError, setBillingError] = useState<string | null>(null);

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

  const handleCheckout = useCallback(async (tier: 'pro' | 'business') => {
    setBillingError(null);
    setBillingBusy(true);
    try {
      await startCheckout(tier);
      // Browser is navigating away to Stripe Checkout; no need to reset busy state.
    } catch (err) {
      setBillingError(err instanceof BillingError ? err.message : 'Could not start checkout.');
      setBillingBusy(false);
    }
  }, []);

  const handleManageSubscription = useCallback(async () => {
    setBillingError(null);
    setBillingBusy(true);
    try {
      await openBillingPortal();
    } catch (err) {
      setBillingError(err instanceof BillingError ? err.message : 'Could not open the billing portal.');
      setBillingBusy(false);
    }
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
            onClick={() => setShowTierChoice((v) => !v)}
            disabled={billingBusy}
            className="text-[11px] font-bold text-emerald-pro bg-emerald-pro/10 px-2.5 py-1 rounded-full hover:bg-emerald-pro/20 transition-colors disabled:opacity-50"
          >
            Upgrade
          </button>
        )}
        {(usage.tier === 'pro' || usage.tier === 'business') && (
          <button
            type="button"
            onClick={() => void handleManageSubscription()}
            disabled={billingBusy}
            className="text-[11px] font-bold text-ink-muted bg-[#eef2f8] px-2.5 py-1 rounded-full hover:bg-[#e3e9f4] transition-colors disabled:opacity-50"
          >
            {billingBusy ? 'Opening…' : 'Manage subscription'}
          </button>
        )}
      </div>

      {/* Tier choice (free -> Pro/Business checkout) */}
      {usage.tier === 'free' && showTierChoice && (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            onClick={() => void handleCheckout('pro')}
            disabled={billingBusy}
            className="flex-1 rounded-lg border border-emerald-pro/30 py-2 text-[11px] font-bold text-emerald-pro hover:bg-emerald-pro/5 disabled:opacity-50"
          >
            {billingBusy ? 'Redirecting…' : 'Pro'}
          </button>
          <button
            type="button"
            onClick={() => void handleCheckout('business')}
            disabled={billingBusy}
            className="flex-1 rounded-lg border border-amber-400/40 py-2 text-[11px] font-bold text-amber-600 hover:bg-amber-50 disabled:opacity-50"
          >
            {billingBusy ? 'Redirecting…' : 'Plus'}
          </button>
        </div>
      )}

      {billingError && (
        <div className="mt-3 flex items-center gap-2 rounded-lg bg-red-50 p-2.5 text-xs text-crimson">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          {billingError}
        </div>
      )}

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
