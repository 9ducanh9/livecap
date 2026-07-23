import { useEffect, useState, useCallback } from 'react';
import {
  BarChart3,
  Activity,
  Clock,
  Users,
  LoaderCircle,
  AlertCircle,
  Info,
} from 'lucide-react';
import { StatsCard } from './StatsCard';
import {
  getUsageAnalytics,
  getTopUsers,
  AdminAccessError,
} from '../../services/adminService';
import type { UsageAnalytics, TopUser, DateRangeParams } from '../../services/adminService';

/** Tier badge colors */
const TIER_COLORS: Record<string, string> = {
  free: 'bg-gray-100 text-gray-700',
  pro: 'bg-emerald-pro/10 text-emerald-pro',
  business: 'bg-blue-100 text-blue-700',
};

/** Colors for tier distribution bars */
const TIER_BAR_COLORS: Record<string, string> = {
  free: 'bg-gray-400',
  pro: 'bg-emerald-pro',
  business: 'bg-blue-500',
};

function formatMonth(monthStr: string): string {
  const [year, month] = monthStr.split('-');
  const date = new Date(Number(year), Number(month) - 1);
  return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
}

function getMonthInputValue(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  return `${y}-${m}`;
}

function SectionLoader() {
  return (
    <div className="flex items-center justify-center py-12">
      <LoaderCircle className="h-5 w-5 animate-spin text-emerald-pro" />
      <span className="ml-2 text-sm text-ink-muted">Loading...</span>
    </div>
  );
}

function SectionError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <AlertCircle className="h-5 w-5 text-crimson mb-2" />
      <p className="text-sm text-crimson">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-3 rounded-lg border border-[#dce5f2] px-3 py-1.5 text-xs font-medium text-ink hover:bg-paper transition-colors"
        >
          Retry
        </button>
      )}
    </div>
  );
}

export default function AdminUsagePage() {
  // Date range filter state
  const now = new Date();
  const defaultEnd = getMonthInputValue(now);
  const threeMonthsAgo = new Date(now.getFullYear(), now.getMonth() - 2, 1);
  const defaultStart = getMonthInputValue(threeMonthsAgo);

  const [startMonth, setStartMonth] = useState(defaultStart);
  const [endMonth, setEndMonth] = useState(defaultEnd);

  // Data state
  const [analytics, setAnalytics] = useState<UsageAnalytics | null>(null);
  const [topUsers, setTopUsers] = useState<TopUser[] | null>(null);

  // Loading/error state per section
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [topUsersLoading, setTopUsersLoading] = useState(true);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [topUsersError, setTopUsersError] = useState<string | null>(null);

  const fetchAnalytics = useCallback(async (params?: DateRangeParams) => {
    setAnalyticsLoading(true);
    setAnalyticsError(null);
    try {
      const data = await getUsageAnalytics(params);
      setAnalytics(data);
    } catch (err) {
      const msg =
        err instanceof AdminAccessError
          ? err.message
          : 'Could not load usage analytics. Please try again.';
      setAnalyticsError(msg);
    } finally {
      setAnalyticsLoading(false);
    }
  }, []);

  const fetchTopUsers = useCallback(async () => {
    setTopUsersLoading(true);
    setTopUsersError(null);
    try {
      const data = await getTopUsers();
      setTopUsers(data);
    } catch (err) {
      const msg =
        err instanceof AdminAccessError
          ? err.message
          : 'Could not load top users data. Please try again.';
      setTopUsersError(msg);
    } finally {
      setTopUsersLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAnalytics({ start_month: startMonth, end_month: endMonth });
    fetchTopUsers();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFilterApply = () => {
    fetchAnalytics({ start_month: startMonth, end_month: endMonth });
  };

  // Compute max values for chart scaling
  const maxSessions = analytics
    ? Math.max(...analytics.months.map((m) => m.total_sessions), 1)
    : 1;
  const maxMinutes = analytics
    ? Math.max(...analytics.months.map((m) => m.total_minutes), 1)
    : 1;

  // Compute 90-day limit for month inputs
  const minMonthDate = new Date(now.getFullYear(), now.getMonth() - 2, 1);
  const minMonth = getMonthInputValue(minMonthDate);
  const maxMonth = getMonthInputValue(now);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center gap-3">
        <BarChart3 className="h-6 w-6 text-emerald-pro" />
        <h1 className="text-2xl font-bold text-ink">Usage Analytics</h1>
      </div>

      {/* Date Range Filter */}
      <div className="rounded-2xl border border-[#dce5f2] bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label htmlFor="start-month" className="block text-xs font-medium text-ink-muted mb-1">
              Start Month
            </label>
            <input
              id="start-month"
              type="month"
              value={startMonth}
              min={minMonth}
              max={maxMonth}
              onChange={(e) => setStartMonth(e.target.value)}
              className="rounded-lg border border-[#dce5f2] px-3 py-2 text-sm text-ink focus:border-emerald-pro focus:outline-none focus:ring-1 focus:ring-emerald-pro"
            />
          </div>
          <div>
            <label htmlFor="end-month" className="block text-xs font-medium text-ink-muted mb-1">
              End Month
            </label>
            <input
              id="end-month"
              type="month"
              value={endMonth}
              min={minMonth}
              max={maxMonth}
              onChange={(e) => setEndMonth(e.target.value)}
              className="rounded-lg border border-[#dce5f2] px-3 py-2 text-sm text-ink focus:border-emerald-pro focus:outline-none focus:ring-1 focus:ring-emerald-pro"
            />
          </div>
          <button
            onClick={handleFilterApply}
            className="rounded-lg bg-emerald-pro px-4 py-2 text-sm font-medium text-white hover:bg-emerald-pro-light transition-colors"
          >
            Apply
          </button>
        </div>
        <div className="mt-2 flex items-start gap-1.5">
          <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-faint" />
          <p className="text-xs text-ink-faint">
            Usage data is limited to a 90-day window. Historical data beyond this period is unavailable due to DynamoDB TTL expiration on monthly usage items.
          </p>
        </div>
      </div>

      {/* Monthly Totals Stats Cards */}
      <section aria-label="Monthly totals">
        {analyticsLoading ? (
          <SectionLoader />
        ) : analyticsError ? (
          <SectionError message={analyticsError} onRetry={() => fetchAnalytics({ start_month: startMonth, end_month: endMonth })} />
        ) : analytics ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatsCard
              icon={<Activity className="h-5 w-5" />}
              label="Total Sessions"
              value={analytics.totals.total_sessions.toLocaleString()}
              subText="Across selected period"
            />
            <StatsCard
              icon={<Clock className="h-5 w-5" />}
              label="Total Minutes"
              value={analytics.totals.total_minutes.toLocaleString()}
              subText="Across selected period"
            />
            <StatsCard
              icon={<Users className="h-5 w-5" />}
              label="Unique Active Users"
              value={analytics.totals.unique_active_users.toLocaleString()}
              subText="Across selected period"
            />
          </div>
        ) : null}
      </section>

      {/* Usage Trend Chart */}
      <section aria-label="Usage trend">
        <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-ink mb-4">Usage Trend</h2>
          {analyticsLoading ? (
            <SectionLoader />
          ) : analyticsError ? (
            <SectionError message={analyticsError} />
          ) : analytics && analytics.months.length > 0 ? (
            <div className="space-y-4">
              {/* Sessions chart */}
              <div>
                <p className="text-xs font-medium text-ink-muted mb-2">Sessions per Month</p>
                <div className="flex items-end gap-2 h-32">
                  {analytics.months.map((m) => (
                    <div key={`sessions-${m.month}`} className="flex flex-1 flex-col items-center gap-1">
                      <span className="text-[10px] text-ink-muted">{m.total_sessions}</span>
                      <div
                        className="w-full rounded-t bg-emerald-pro/80 transition-all"
                        style={{ height: `${(m.total_sessions / maxSessions) * 100}%`, minHeight: '2px' }}
                      />
                      <span className="text-[10px] text-ink-faint">{formatMonth(m.month)}</span>
                    </div>
                  ))}
                </div>
              </div>
              {/* Minutes chart */}
              <div>
                <p className="text-xs font-medium text-ink-muted mb-2">Minutes per Month</p>
                <div className="flex items-end gap-2 h-32">
                  {analytics.months.map((m) => (
                    <div key={`minutes-${m.month}`} className="flex flex-1 flex-col items-center gap-1">
                      <span className="text-[10px] text-ink-muted">{m.total_minutes}</span>
                      <div
                        className="w-full rounded-t bg-blue-400/80 transition-all"
                        style={{ height: `${(m.total_minutes / maxMinutes) * 100}%`, minHeight: '2px' }}
                      />
                      <span className="text-[10px] text-ink-faint">{formatMonth(m.month)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-muted py-8 text-center">No usage data available for the selected period.</p>
          )}
        </div>
      </section>

      {/* Top 10 Users Table */}
      <section aria-label="Top users">
        <div className="rounded-2xl border border-[#dce5f2] bg-white shadow-sm overflow-hidden">
          <div className="px-6 py-4 border-b border-[#dce5f2]">
            <h2 className="text-sm font-semibold text-ink">Top 10 Users by Minutes</h2>
          </div>
          {topUsersLoading ? (
            <SectionLoader />
          ) : topUsersError ? (
            <SectionError message={topUsersError} onRetry={fetchTopUsers} />
          ) : topUsers && topUsers.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#dce5f2] bg-paper">
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
                      Email
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
                      Tier
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-ink-muted">
                      Sessions
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-ink-muted">
                      Minutes
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {topUsers.slice(0, 10).map((user, idx) => (
                    <tr
                      key={`${user.email}-${idx}`}
                      className="border-b border-[#dce5f2] last:border-b-0 hover:bg-paper/50 transition-colors"
                    >
                      <td className="px-4 py-3 text-ink font-medium truncate max-w-[200px]">
                        {user.email}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${TIER_COLORS[user.tier] ?? 'bg-gray-100 text-gray-700'}`}
                        >
                          {user.tier}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-ink tabular-nums">
                        {user.sessions_used.toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right text-ink tabular-nums">
                        {user.minutes_used.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-ink-muted py-8 text-center">No user data available.</p>
          )}
        </div>
      </section>

      {/* Tier Distribution */}
      <section aria-label="Tier distribution">
        <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
          <h2 className="text-sm font-semibold text-ink mb-4">Tier Distribution</h2>
          {analyticsLoading ? (
            <SectionLoader />
          ) : analyticsError ? (
            <SectionError message={analyticsError} />
          ) : analytics && Object.keys(analytics.tier_distribution).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(analytics.tier_distribution).map(([tier, { count, percentage }]) => (
                <div key={tier} className="flex items-center gap-3">
                  <span className="w-20 text-xs font-medium text-ink capitalize">{tier}</span>
                  <div className="flex-1 h-6 rounded-full bg-paper overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${TIER_BAR_COLORS[tier] ?? 'bg-gray-400'}`}
                      style={{ width: `${Math.max(percentage, 1)}%` }}
                    />
                  </div>
                  <span className="w-24 text-xs text-ink-muted text-right">
                    {count} ({percentage.toFixed(1)}%)
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-ink-muted py-4 text-center">No tier data available.</p>
          )}
        </div>
      </section>
    </div>
  );
}
