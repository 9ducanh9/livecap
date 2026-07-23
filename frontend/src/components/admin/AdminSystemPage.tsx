import { useEffect, useState, useCallback } from 'react';
import {
  Activity,
  Server,
  Bell,
  DollarSign,
  ExternalLink,
  LoaderCircle,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react';
import { StatsCard } from './StatsCard';
import { getSystemHealth, AdminAccessError } from '../../services/adminService';
import type { SystemHealth } from '../../services/adminService';

// --- Health indicator helpers ---

type HealthLevel = 'healthy' | 'degraded' | 'unreachable';

const HEALTH_CONFIG: Record<HealthLevel, { label: string; color: string; bgColor: string; icon: typeof CheckCircle2 }> = {
  healthy: { label: 'Healthy', color: 'text-emerald-600', bgColor: 'bg-emerald-100', icon: CheckCircle2 },
  degraded: { label: 'Degraded', color: 'text-yellow-600', bgColor: 'bg-yellow-100', icon: AlertTriangle },
  unreachable: { label: 'Unreachable', color: 'text-red-600', bgColor: 'bg-red-100', icon: AlertCircle },
};

const ALARM_STATE_CONFIG: Record<string, { label: string; dotColor: string; bgColor: string }> = {
  OK: { label: 'OK', dotColor: 'bg-emerald-500', bgColor: 'bg-emerald-50 text-emerald-700' },
  ALARM: { label: 'ALARM', dotColor: 'bg-red-500', bgColor: 'bg-red-50 text-red-700' },
  INSUFFICIENT_DATA: { label: 'Insufficient Data', dotColor: 'bg-gray-400', bgColor: 'bg-gray-100 text-gray-600' },
};

// --- AWS Console links ---

const AWS_CONSOLE_LINKS = [
  {
    label: 'ECS Console',
    url: 'https://console.aws.amazon.com/ecs/home',
    icon: Server,
  },
  {
    label: 'CloudWatch Console',
    url: 'https://console.aws.amazon.com/cloudwatch/home',
    icon: Bell,
  },
  {
    label: 'Cost Explorer',
    url: 'https://console.aws.amazon.com/cost-management/home#/cost-explorer',
    icon: DollarSign,
  },
];

// --- Shared UI helpers ---

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

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

function formatTimestamp(isoTimestamp: string): string {
  try {
    const date = new Date(isoTimestamp);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoTimestamp;
  }
}

export default function AdminSystemPage() {
  const [data, setData] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getSystemHealth();
      setData(result);
    } catch (err) {
      const msg =
        err instanceof AdminAccessError
          ? err.message
          : 'Could not load system health data. Please try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const healthLevel = (data?.ecs.health_status ?? 'unreachable') as HealthLevel;
  const healthConfig = HEALTH_CONFIG[healthLevel] ?? HEALTH_CONFIG.unreachable;
  const HealthIcon = healthConfig.icon;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Activity className="h-6 w-6 text-emerald-pro" />
          <h1 className="text-2xl font-bold text-ink">System Health</h1>
        </div>
        {!loading && (
          <button
            onClick={fetchData}
            className="flex items-center gap-1.5 rounded-lg border border-[#dce5f2] px-3 py-1.5 text-xs font-medium text-ink hover:bg-paper transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
        )}
      </div>

      {/* Warning Banners */}
      {data && data.warnings.length > 0 && (
        <div className="space-y-2">
          {data.warnings.map((warning, idx) => (
            <div
              key={idx}
              className="flex items-start gap-3 rounded-xl border border-yellow-200 bg-yellow-50 px-4 py-3"
              role="alert"
            >
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0 text-yellow-600" />
              <p className="text-sm text-yellow-800">{warning}</p>
            </div>
          ))}
        </div>
      )}

      {/* Loading State */}
      {loading && <SectionLoader />}

      {/* Error State */}
      {!loading && error && <SectionError message={error} onRetry={fetchData} />}

      {/* Main Content */}
      {!loading && !error && data && (
        <>
          {/* ECS Section */}
          <section aria-label="ECS status">
            <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
                  <Server className="h-4 w-4 text-ink-muted" />
                  ECS Service Status
                </h2>
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${healthConfig.bgColor} ${healthConfig.color}`}
                >
                  <HealthIcon className="h-3.5 w-3.5" />
                  {healthConfig.label}
                </span>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <StatsCard
                  icon={<Activity className="h-5 w-5" />}
                  label="Running Tasks"
                  value={data.ecs.running_count}
                  subText={`of ${data.ecs.desired_count} desired`}
                />
                <StatsCard
                  icon={<Server className="h-5 w-5" />}
                  label="Desired Tasks"
                  value={data.ecs.desired_count}
                />
                <StatsCard
                  icon={<LoaderCircle className="h-5 w-5" />}
                  label="Pending Tasks"
                  value={data.ecs.pending_count}
                  subText={data.ecs.pending_count > 0 ? 'Tasks starting up' : 'None pending'}
                />
              </div>
            </div>
          </section>

          {/* CloudWatch Alarms Section */}
          <section aria-label="CloudWatch alarms">
            <div className="rounded-2xl border border-[#dce5f2] bg-white shadow-sm overflow-hidden">
              <div className="px-6 py-4 border-b border-[#dce5f2]">
                <h2 className="text-sm font-semibold text-ink flex items-center gap-2">
                  <Bell className="h-4 w-4 text-ink-muted" />
                  CloudWatch Alarms
                </h2>
              </div>
              {data.alarms.length > 0 ? (
                <div className="divide-y divide-[#dce5f2]">
                  {data.alarms.map((alarm, idx) => {
                    const stateConfig = ALARM_STATE_CONFIG[alarm.state] ?? ALARM_STATE_CONFIG.INSUFFICIENT_DATA;
                    return (
                      <div
                        key={`${alarm.alarm_name}-${idx}`}
                        className="flex items-center justify-between px-6 py-3 hover:bg-paper/50 transition-colors"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-ink truncate">
                            {alarm.alarm_name}
                          </p>
                          {alarm.reason && (
                            <p className="text-xs text-ink-muted mt-0.5 truncate">
                              {alarm.reason}
                            </p>
                          )}
                        </div>
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${stateConfig.bgColor}`}
                        >
                          <span className={`h-2 w-2 rounded-full ${stateConfig.dotColor}`} />
                          {stateConfig.label}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-ink-muted py-8 text-center">
                  No CloudWatch alarms configured.
                </p>
              )}
            </div>
          </section>

          {/* Cost Estimate Section */}
          <section aria-label="Cost estimate">
            <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-ink flex items-center gap-2 mb-4">
                <DollarSign className="h-4 w-4 text-ink-muted" />
                Current Month Cost Estimate
              </h2>
              {data.cost_estimate ? (
                <div>
                  <p className="text-3xl font-bold text-ink">
                    {formatCurrency(data.cost_estimate.current_month_usd)}
                  </p>
                  <p className="mt-2 text-xs text-ink-muted">
                    Data as of: {formatTimestamp(data.cost_estimate.data_timestamp)}
                  </p>
                  <p className="mt-1 text-xs text-ink-faint">
                    AWS Cost Explorer data typically lags ~24 hours.
                  </p>
                </div>
              ) : (
                <div className="flex items-center gap-2 py-4">
                  <AlertCircle className="h-4 w-4 text-ink-faint" />
                  <p className="text-sm text-ink-muted">
                    Cost estimate is currently unavailable.
                  </p>
                </div>
              )}
            </div>
          </section>

          {/* AWS Console Quick Links */}
          <section aria-label="AWS Console links">
            <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
              <h2 className="text-sm font-semibold text-ink mb-4">AWS Console</h2>
              <div className="flex flex-wrap gap-3">
                {AWS_CONSOLE_LINKS.map((link) => {
                  const LinkIcon = link.icon;
                  return (
                    <a
                      key={link.label}
                      href={link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 rounded-lg border border-[#dce5f2] px-4 py-2.5 text-sm font-medium text-ink hover:bg-paper hover:border-emerald-pro/30 transition-colors"
                    >
                      <LinkIcon className="h-4 w-4 text-emerald-pro" />
                      {link.label}
                      <ExternalLink className="h-3 w-3 text-ink-faint" />
                    </a>
                  );
                })}
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
