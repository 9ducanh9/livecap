import { useEffect, useState, useCallback } from 'react';
import {
  DollarSign,
  CreditCard,
  UserMinus,
  LoaderCircle,
  AlertCircle,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react';
import { StatsCard } from './StatsCard';
import {
  getRevenue,
  AdminAccessError,
} from '../../services/adminService';
import type { RevenueData } from '../../services/adminService';

function formatCentsToDollars(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function formatDate(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatMrr(mrr: number): string {
  return `$${mrr.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function AdminRevenuePage() {
  const [data, setData] = useState<RevenueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchRevenue = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getRevenue();
      setData(result);
    } catch (err) {
      const msg =
        err instanceof AdminAccessError
          ? err.message
          : 'Could not load revenue data. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRevenue();
  }, [fetchRevenue]);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <DollarSign className="h-6 w-6 text-emerald-pro" />
          <h1 className="text-2xl font-bold text-ink">Revenue</h1>
        </div>
        <a
          href="https://dashboard.stripe.com"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-lg border border-[#dce5f2] bg-white px-4 py-2 text-sm font-medium text-ink hover:bg-paper transition-colors"
        >
          Open Stripe Dashboard
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>

      {/* Warning Banner */}
      {data && (!data.stripe_data_available || data.warning) && (
        <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <AlertTriangle className="h-5 w-5 shrink-0 text-amber-600 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-amber-800">Stripe data may be incomplete</p>
            <p className="text-xs text-amber-700 mt-1">
              {data.warning || 'The Stripe API could not be fully reached. Displayed revenue data may not reflect the latest transactions.'}
            </p>
          </div>
        </div>
      )}

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <LoaderCircle className="h-5 w-5 animate-spin text-emerald-pro" />
          <span className="ml-2 text-sm text-ink-muted">Loading revenue data...</span>
        </div>
      )}

      {/* Error State */}
      {!loading && error && (
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <AlertCircle className="h-5 w-5 text-crimson mb-2" />
          <p className="text-sm text-crimson">{error}</p>
          <button
            onClick={fetchRevenue}
            className="mt-3 rounded-lg border border-[#dce5f2] px-3 py-1.5 text-xs font-medium text-ink hover:bg-paper transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Stats Cards */}
      {!loading && !error && data && (
        <>
          <section aria-label="Revenue stats">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <StatsCard
                icon={<DollarSign className="h-5 w-5" />}
                label="Monthly Recurring Revenue"
                value={formatMrr(data.mrr_usd)}
                subText="Current MRR from Stripe"
              />
              <StatsCard
                icon={<CreditCard className="h-5 w-5" />}
                label="Active Subscriptions"
                value={data.active_subscriptions.toLocaleString()}
                subText="Currently active"
              />
              <StatsCard
                icon={<UserMinus className="h-5 w-5" />}
                label="Churned Subscriptions"
                value={data.churned_subscriptions.toLocaleString()}
                subText="Cancelled or expired"
              />
            </div>
          </section>

          {/* Recent Transactions Table */}
          <section aria-label="Recent transactions">
            <div className="rounded-2xl border border-[#dce5f2] bg-white shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-[#dce5f2]">
                <h2 className="text-sm font-semibold text-ink">Recent Transactions</h2>
              </div>
              {data.recent_transactions.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#dce5f2] bg-paper">
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
                          Date
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
                          User Email
                        </th>
                        <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-ink-muted">
                          Amount
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-muted">
                          Type
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.recent_transactions.map((tx, idx) => (
                        <tr
                          key={`${tx.date}-${idx}`}
                          className="border-b border-[#dce5f2] last:border-b-0 hover:bg-paper/50 transition-colors"
                        >
                          <td className="px-4 py-3 text-ink tabular-nums">
                            {formatDate(tx.date)}
                          </td>
                          <td className="px-4 py-3 text-ink font-medium truncate max-w-[200px]">
                            {tx.user_email || '—'}
                          </td>
                          <td className="px-4 py-3 text-right text-ink tabular-nums">
                            {formatCentsToDollars(tx.amount_cents)}
                          </td>
                          <td className="px-4 py-3">
                            <span className="inline-block rounded-full bg-paper px-2.5 py-0.5 text-xs font-medium text-ink capitalize">
                              {tx.transaction_type.replace(/_/g, ' ')}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-sm text-ink-muted py-8 text-center">
                  No recent transactions available.
                </p>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
