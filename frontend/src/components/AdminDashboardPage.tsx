import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  LoaderCircle,
  ShieldAlert,
  Users,
  DollarSign,
  Activity,
  Server,
  RefreshCw,
} from 'lucide-react';
import { getAdminOverview, AdminAccessError, type AdminOverview } from '../services/adminService';

const TIER_ORDER = ['free', 'pro', 'business'] as const;

export default function AdminDashboardPage() {
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    void getAdminOverview()
      .then(setOverview)
      .catch((err: unknown) => {
        setError(err instanceof AdminAccessError ? err.message : 'Something went wrong loading the dashboard.');
      })
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="min-h-screen bg-paper text-ink font-ui antialiased">
      <header className="sticky top-0 z-[60] border-b border-[#dce5f2] bg-white/90 backdrop-blur-xl">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-3 sm:px-8">
          <div className="flex items-center divide-x divide-ink/10">
            <a href="/app" className="flex items-center gap-2 pr-5 py-2 group transition-colors">
              <ArrowLeft className="w-4 h-4 text-ink/45 group-hover:text-emerald-pro transition-colors" />
              <span className="text-sm font-semibold text-ink/55 group-hover:text-ink transition-colors">Workspace</span>
            </a>
            <div className="flex items-center gap-3 pl-5 py-2">
              <img src="/LiveCap.svg" alt="" className="h-10 w-10 rounded-xl" />
              <span className="font-instrument text-xl font-bold tracking-[-0.08em] text-ink">Admin</span>
            </div>
          </div>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="flex items-center gap-2 rounded-full border border-[#dce5f2] px-3 py-1.5 text-xs font-semibold text-ink-muted hover:bg-[#f7f8fc] disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-8 sm:px-8">
        {loading && !overview && (
          <div className="flex items-center gap-2 text-sm text-ink-muted">
            <LoaderCircle className="h-4 w-4 animate-spin" /> Loading admin dashboard...
          </div>
        )}

        {error && (
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-[#dce5f2] bg-white p-10 text-center shadow-[0_16px_50px_rgba(16,34,71,0.07)]">
            <ShieldAlert className="h-8 w-8 text-crimson" />
            <p className="text-sm font-semibold text-ink">{error}</p>
            <a href="/app" className="text-sm font-semibold text-emerald-pro hover:underline">Back to workspace</a>
          </div>
        )}

        {overview && (
          <>
            {/* Stat cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard
                icon={<Users className="h-4 w-4 text-emerald-pro" />}
                label="Total users"
                value={overview.stats.total_users.toString()}
                sub={TIER_ORDER.map((t) => `${t}: ${overview.stats.by_tier[t] ?? 0}`).join(' · ')}
              />
              <StatCard
                icon={<DollarSign className="h-4 w-4 text-amber-500" />}
                label="Estimated MRR"
                value={`$${overview.stats.estimated_mrr_usd}`}
                sub="from active Pro/Business tiers"
              />
              <StatCard
                icon={<Activity className="h-4 w-4 text-emerald-pro" />}
                label="Sessions this month"
                value={overview.stats.total_sessions_this_month.toString()}
                sub={`${overview.stats.total_minutes_this_month} min total`}
              />
              <StatCard
                icon={<Server className={`h-4 w-4 ${overview.system.backend_reachable ? 'text-emerald-pro' : 'text-crimson'}`} />}
                label="Backend"
                value={overview.system.backend_reachable ? 'Healthy' : 'Unreachable'}
                sub={
                  overview.system.desired_count === null
                    ? 'ECS not configured'
                    : `${overview.system.running_count}/${overview.system.desired_count} tasks running`
                }
              />
            </div>

            {/* User table */}
            <div className="mt-6 overflow-hidden rounded-2xl border border-[#dce5f2] bg-white shadow-[0_16px_50px_rgba(16,34,71,0.07)]">
              <div className="border-b border-[#dce5f2] px-6 py-4">
                <p className="text-sm font-bold text-ink">Users</p>
                <p className="mt-0.5 text-xs text-ink-muted">Tier, usage this month, and subscription status.</p>
              </div>
              {overview.users.length === 0 ? (
                <p className="px-6 py-8 text-center text-sm text-ink-muted">No users yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#dce5f2] text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
                        <th className="px-6 py-3">Email</th>
                        <th className="px-6 py-3">Tier</th>
                        <th className="px-6 py-3">Sessions</th>
                        <th className="px-6 py-3">Minutes</th>
                        <th className="px-6 py-3">Subscription</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.users.map((user) => (
                        <tr key={user.user_id} className="border-b border-[#eef2f8] last:border-0">
                          <td className="px-6 py-3 text-ink">{user.email || user.user_id}</td>
                          <td className="px-6 py-3">
                            <TierBadge tier={user.tier} />
                          </td>
                          <td className="px-6 py-3 font-mono text-ink-muted">{user.sessions_used}</td>
                          <td className="px-6 py-3 font-mono text-ink-muted">{user.minutes_used}</td>
                          <td className="px-6 py-3 text-ink-muted">{user.subscription_status ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function StatCard({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string; sub: string }) {
  return (
    <div className="rounded-2xl border border-[#dce5f2] bg-white p-5 shadow-[0_16px_50px_rgba(16,34,71,0.05)]">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {icon} {label}
      </div>
      <p className="mt-2 text-2xl font-bold text-ink">{value}</p>
      <p className="mt-1 text-xs text-ink-muted">{sub}</p>
    </div>
  );
}

function TierBadge({ tier }: { tier: string }) {
  const styles: Record<string, string> = {
    free: 'bg-[#eef2f8] text-ink-muted',
    pro: 'bg-emerald-pro/10 text-emerald-pro',
    business: 'bg-amber-100 text-amber-700',
  };
  return (
    <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${styles[tier] ?? styles.free}`}>
      {tier}
    </span>
  );
}
