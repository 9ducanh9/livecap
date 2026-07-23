import { useEffect, useState, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  User,
  Calendar,
  Clock,
  Hash,
  LoaderCircle,
  CreditCard,
  Shield,
  FileText,
  ToggleLeft,
  ToggleRight,
  KeyRound,
  ArrowUpDown,
} from 'lucide-react';
import {
  getUserDetail,
  disableUser,
  enableUser,
  resetPassword,
  changeTier,
  AdminAccessError,
  type UserDetail,
} from '../../services/adminService';
import { ConfirmDialog } from './ConfirmDialog';
import { AdminNotification } from './AdminNotification';

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    free: 'bg-gray-100 text-gray-700',
    pro: 'bg-[#0a9c88]/10 text-[#0a9c88]',
    business: 'bg-[#102247]/10 text-[#102247]',
  };
  const colorClass = colors[tier] ?? 'bg-gray-100 text-gray-700';
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${colorClass}`}>
      {tier}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const isEnabled = status === 'enabled';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
        isEnabled ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}
    >
      {status}
    </span>
  );
}

type ConfirmAction = 'disable' | 'enable' | 'changeTier';

export default function AdminUserDetailPage() {
  const { username } = useParams<{ username: string }>();
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Mutation loading states
  const [mutating, setMutating] = useState(false);

  // Confirm dialog state
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);
  const [pendingTier, setPendingTier] = useState<string>('');

  // Notification state
  const [notification, setNotification] = useState<{
    message: string;
    type: 'success' | 'error';
    visible: boolean;
  }>({ message: '', type: 'success', visible: false });

  const fetchDetail = useCallback(() => {
    if (!username) return;
    setLoading(true);
    setError(null);
    getUserDetail(username)
      .then(setDetail)
      .catch((err) => setError(err.message ?? 'Failed to load user details'))
      .finally(() => setLoading(false));
  }, [username]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const showNotification = (message: string, type: 'success' | 'error') => {
    setNotification({ message, type, visible: true });
  };

  // --- Confirm dialog handlers ---

  const handleDisableEnableClick = () => {
    if (!detail) return;
    const action: ConfirmAction = detail.profile.status === 'enabled' ? 'disable' : 'enable';
    setConfirmAction(action);
  };

  const handleChangeTierClick = (tier: string) => {
    if (!detail || tier === detail.profile.tier) return;
    setPendingTier(tier);
    setConfirmAction('changeTier');
  };

  const handleConfirm = async () => {
    if (!username || !detail) return;
    setConfirmAction(null);
    setMutating(true);

    try {
      if (confirmAction === 'disable') {
        const result = await disableUser(username);
        showNotification(result.message || 'User disabled successfully.', 'success');
      } else if (confirmAction === 'enable') {
        const result = await enableUser(username);
        showNotification(result.message || 'User enabled successfully.', 'success');
      } else if (confirmAction === 'changeTier') {
        const result = await changeTier(username, pendingTier);
        const msg = result.warning
          ? `${result.message} Warning: ${result.warning}`
          : result.message || `Tier changed to ${pendingTier}.`;
        showNotification(msg, 'success');
      }
      fetchDetail();
    } catch (err) {
      const message =
        err instanceof AdminAccessError ? err.message : 'Action failed. Please try again.';
      showNotification(message, 'error');
    } finally {
      setMutating(false);
      setPendingTier('');
    }
  };

  const handleResetPassword = async () => {
    if (!username) return;
    setMutating(true);
    try {
      const result = await resetPassword(username);
      showNotification(result.message || 'Password reset email sent.', 'success');
    } catch (err) {
      const message =
        err instanceof AdminAccessError ? err.message : 'Failed to reset password.';
      showNotification(message, 'error');
    } finally {
      setMutating(false);
    }
  };

  // --- Confirm dialog content ---

  const getConfirmDialogProps = () => {
    if (confirmAction === 'disable') {
      return {
        open: true,
        title: 'Disable User',
        message: `Are you sure you want to disable ${detail?.profile.email ?? 'this user'}? They will not be able to sign in.`,
        confirmLabel: 'Disable',
        variant: 'danger' as const,
      };
    }
    if (confirmAction === 'enable') {
      return {
        open: true,
        title: 'Enable User',
        message: `Are you sure you want to re-enable ${detail?.profile.email ?? 'this user'}?`,
        confirmLabel: 'Enable',
        variant: 'danger' as const,
      };
    }
    if (confirmAction === 'changeTier') {
      const stripeWarning = detail?.has_stripe_subscription
        ? ` This user has an active Stripe subscription — the billing system may override this change at the next renewal.`
        : '';
      return {
        open: true,
        title: 'Change Tier',
        message: `Change tier for ${detail?.profile.email ?? 'this user'} from "${detail?.profile.tier}" to "${pendingTier}"?${stripeWarning}`,
        confirmLabel: 'Change Tier',
        variant: 'warning' as const,
      };
    }
    return { open: false, title: '', message: '', confirmLabel: 'Confirm', variant: 'danger' as const };
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Link
          to="/admin/users"
          className="inline-flex items-center gap-1.5 text-sm text-[#0a9c88] hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Users
        </Link>
        <div className="flex items-center justify-center py-16">
          <LoaderCircle className="h-6 w-6 animate-spin text-[#0a9c88]" />
          <span className="ml-2 text-sm text-[#102247]/60">Loading user details...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <Link
          to="/admin/users"
          className="inline-flex items-center gap-1.5 text-sm text-[#0a9c88] hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Users
        </Link>
        <div className="rounded-2xl border border-[#dce5f2] bg-white p-8 shadow-sm">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!detail) return null;

  const { profile, usage_history, transcript_sessions, audit_log, has_stripe_subscription } = detail;
  const isFederated = profile.identity_provider !== 'native';
  const confirmDialogProps = getConfirmDialogProps();
  const tierOptions = ['free', 'pro', 'business'];

  return (
    <div className="space-y-6">
      {/* Notification */}
      <AdminNotification
        message={notification.message}
        type={notification.type}
        visible={notification.visible}
        onClose={() => setNotification((prev) => ({ ...prev, visible: false }))}
      />

      {/* Confirm Dialog */}
      <ConfirmDialog
        {...confirmDialogProps}
        onConfirm={handleConfirm}
        onCancel={() => {
          setConfirmAction(null);
          setPendingTier('');
        }}
      />

      {/* Back link */}
      <Link
        to="/admin/users"
        className="inline-flex items-center gap-1.5 text-sm text-[#0a9c88] hover:underline"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Users
      </Link>

      {/* Page heading */}
      <div className="flex items-center gap-3">
        <User className="h-6 w-6 text-[#0a9c88]" />
        <h1 className="text-2xl font-bold text-[#102247]">User Detail</h1>
      </div>

      {/* Profile Section */}
      <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-[#102247] mb-4">
          <Shield className="h-5 w-5 text-[#0a9c88]" />
          Profile
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div>
            <p className="text-xs font-medium text-[#102247]/60 uppercase tracking-wide">Email</p>
            <p className="mt-1 text-sm text-[#102247]">{profile.email}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-[#102247]/60 uppercase tracking-wide">Tier</p>
            <p className="mt-1">
              <TierBadge tier={profile.tier} />
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-[#102247]/60 uppercase tracking-wide">Status</p>
            <p className="mt-1">
              <StatusBadge status={profile.status} />
            </p>
          </div>
          <div>
            <p className="text-xs font-medium text-[#102247]/60 uppercase tracking-wide">Identity Provider</p>
            <p className="mt-1 text-sm text-[#102247]">{profile.identity_provider}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-[#102247]/60 uppercase tracking-wide">Created Date</p>
            <p className="mt-1 text-sm text-[#102247]">{formatDate(profile.created_date)}</p>
          </div>
          <div>
            <p className="text-xs font-medium text-[#102247]/60 uppercase tracking-wide">Subscription</p>
            <p className="mt-1">
              {has_stripe_subscription ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-[#0a9c88]/10 px-2.5 py-0.5 text-xs font-medium text-[#0a9c88]">
                  <CreditCard className="h-3 w-3" />
                  Stripe Active
                </span>
              ) : (
                <span className="text-sm text-[#102247]/50">No active subscription</span>
              )}
            </p>
          </div>
        </div>
      </div>

      {/* Actions Section */}
      <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-[#102247] mb-4">
          <Shield className="h-5 w-5 text-[#0a9c88]" />
          Actions
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          {/* Disable/Enable toggle */}
          <button
            onClick={handleDisableEnableClick}
            disabled={mutating}
            className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
              profile.status === 'enabled'
                ? 'border border-red-200 bg-red-50 text-red-700 hover:bg-red-100'
                : 'border border-green-200 bg-green-50 text-green-700 hover:bg-green-100'
            }`}
          >
            {profile.status === 'enabled' ? (
              <>
                <ToggleLeft className="h-4 w-4" />
                Disable User
              </>
            ) : (
              <>
                <ToggleRight className="h-4 w-4" />
                Enable User
              </>
            )}
          </button>

          {/* Reset Password */}
          <button
            onClick={handleResetPassword}
            disabled={mutating || isFederated}
            title={isFederated ? 'Password reset is not available for federated users' : 'Send password reset email'}
            className="inline-flex items-center gap-2 rounded-lg border border-[#dce5f2] bg-white px-4 py-2 text-sm font-medium text-[#102247] transition-colors hover:bg-[#f7f8fc] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <KeyRound className="h-4 w-4" />
            Reset Password
          </button>

          {/* Change Tier */}
          <div className="inline-flex items-center gap-2">
            <ArrowUpDown className="h-4 w-4 text-[#102247]/60" />
            <span className="text-sm font-medium text-[#102247]/70">Change Tier:</span>
            {tierOptions.map((tier) => (
              <button
                key={tier}
                onClick={() => handleChangeTierClick(tier)}
                disabled={mutating || tier === profile.tier}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium capitalize transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                  tier === profile.tier
                    ? 'bg-[#0a9c88]/10 text-[#0a9c88] border border-[#0a9c88]/30'
                    : 'border border-[#dce5f2] text-[#102247] hover:bg-[#f7f8fc]'
                }`}
              >
                {tier}
              </button>
            ))}
          </div>
        </div>
        {isFederated && (
          <p className="mt-3 text-xs text-[#102247]/50">
            Password reset is not available for federated (non-native) users.
          </p>
        )}
        {has_stripe_subscription && (
          <p className="mt-3 text-xs text-amber-600">
            ⚠ This user has an active Stripe subscription. Tier changes may be overridden at the next billing cycle.
          </p>
        )}
      </div>

      {/* Usage History Section */}
      <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-[#102247] mb-4">
          <Calendar className="h-5 w-5 text-[#0a9c88]" />
          Monthly Usage History
        </h2>
        {usage_history.length === 0 ? (
          <p className="text-sm text-[#102247]/50">No usage data available.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#dce5f2]">
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    Month
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    Sessions
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    Minutes
                  </th>
                </tr>
              </thead>
              <tbody>
                {usage_history.map((row) => (
                  <tr key={row.month} className="border-b border-[#dce5f2] last:border-b-0">
                    <td className="px-4 py-3 text-[#102247]">{row.month}</td>
                    <td className="px-4 py-3 text-[#102247]">{row.sessions_used}</td>
                    <td className="px-4 py-3 text-[#102247]">{row.minutes_used}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Transcript Sessions Section */}
      <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-[#102247] mb-4">
          <FileText className="h-5 w-5 text-[#0a9c88]" />
          Recent Transcript Sessions
        </h2>
        {transcript_sessions.length === 0 ? (
          <p className="text-sm text-[#102247]/50">No sessions found.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#dce5f2]">
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    Date
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    <span className="inline-flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      Duration
                    </span>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    <span className="inline-flex items-center gap-1">
                      <Hash className="h-3 w-3" />
                      Segments
                    </span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {transcript_sessions.map((session) => (
                  <tr key={session.session_id} className="border-b border-[#dce5f2] last:border-b-0">
                    <td className="px-4 py-3 text-[#102247]">{formatDate(session.created_at)}</td>
                    <td className="px-4 py-3 text-[#102247]">{formatDuration(session.duration_seconds)}</td>
                    <td className="px-4 py-3 text-[#102247]">{session.segment_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Audit Log Section */}
      <div className="rounded-2xl border border-[#dce5f2] bg-white p-6 shadow-sm">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-[#102247] mb-4">
          <FileText className="h-5 w-5 text-[#0a9c88]" />
          Audit Log
        </h2>
        {audit_log.length === 0 ? (
          <p className="text-sm text-[#102247]/50">No audit entries yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#dce5f2]">
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    Timestamp
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    Action
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    Admin
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    Previous
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-[#102247]/60">
                    New
                  </th>
                </tr>
              </thead>
              <tbody>
                {audit_log.map((entry) => (
                  <tr key={entry.entry_id} className="border-b border-[#dce5f2] last:border-b-0">
                    <td className="px-4 py-3 text-[#102247]">{formatDateTime(entry.timestamp)}</td>
                    <td className="px-4 py-3 text-[#102247] capitalize">{entry.action_type.replace(/_/g, ' ')}</td>
                    <td className="px-4 py-3 text-[#102247]/70 text-xs font-mono">{entry.admin_user_id}</td>
                    <td className="px-4 py-3 text-[#102247]/70">{entry.previous_value ?? '—'}</td>
                    <td className="px-4 py-3 text-[#102247]/70">{entry.new_value ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
