import { useState, useEffect, useCallback, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Users, UserCheck, Crown, Building2, AlertCircle, LoaderCircle, ToggleLeft, ToggleRight, Trash2 } from 'lucide-react';
import { StatsCard } from './StatsCard';
import { DataTable, type Column } from './DataTable';
import { FilterBar } from './FilterBar';
import { ConfirmDialog } from './ConfirmDialog';
import { AdminNotification } from './AdminNotification';
import { getUsers, disableUser, enableUser, deleteUser, AdminAccessError, type PaginatedUsers } from '../../services/adminService';

/** Row type compatible with DataTable's Record<string, unknown> constraint. */
interface UserRow {
  [key: string]: unknown;
  cognito_username: string;
  email: string;
  tier: string;
  status: string;
  identity_provider: string;
  created_date: string;
  last_active: string | null;
}

export default function AdminUsersPage() {
  // Filter and pagination state
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [searchEmail, setSearchEmail] = useState('');
  const [tierFilter, setTierFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Mutation state for row actions
  const [mutatingUser, setMutatingUser] = useState<string | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<UserRow | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<UserRow | null>(null);
  const [notification, setNotification] = useState<{
    message: string;
    type: 'success' | 'error';
    visible: boolean;
  }>({ message: '', type: 'success', visible: false });

  // Data state
  const [data, setData] = useState<PaginatedUsers | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch users whenever filters or page change
  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await getUsers({
        page,
        page_size: pageSize,
        search_email: searchEmail || undefined,
        filter_tier: tierFilter || undefined,
        filter_status: statusFilter || undefined,
      });
      setData(result);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load users. Please try again.';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, searchEmail, tierFilter, statusFilter]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  // Reset to page 1 when filters change
  const handleSearchChange = (value: string) => {
    setSearchEmail(value);
    setPage(1);
  };

  const handleTierChange = (value: string) => {
    setTierFilter(value);
    setPage(1);
  };

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setPage(1);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setPage(1);
  };

  // Row action handlers
  const handleToggleClick = (user: UserRow) => {
    setConfirmTarget(user);
  };

  const handleConfirmToggle = async () => {
    if (!confirmTarget) return;
    setConfirmTarget(null);
    setMutatingUser(confirmTarget.cognito_username);
    try {
      if (confirmTarget.status === 'enabled') {
        const result = await disableUser(confirmTarget.cognito_username);
        setNotification({ message: result.message || 'User disabled.', type: 'success', visible: true });
      } else {
        const result = await enableUser(confirmTarget.cognito_username);
        setNotification({ message: result.message || 'User enabled.', type: 'success', visible: true });
      }
      fetchUsers();
    } catch (err) {
      const message = err instanceof AdminAccessError ? err.message : 'Action failed.';
      setNotification({ message, type: 'error', visible: true });
    } finally {
      setMutatingUser(null);
    }
  };

  const handleDeleteClick = (user: UserRow) => {
    setDeleteTarget(user);
  };

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return;
    const target = deleteTarget;
    setDeleteTarget(null);
    setMutatingUser(target.cognito_username);
    try {
      const result = await deleteUser(target.cognito_username);
      setNotification({ message: result.message || 'User deleted.', type: 'success', visible: true });
      fetchUsers();
    } catch (err) {
      const message = err instanceof AdminAccessError ? err.message : 'Delete failed.';
      setNotification({ message, type: 'error', visible: true });
    } finally {
      setMutatingUser(null);
    }
  };

  // Show Identity Provider column when duplicate emails exist
  const showIdentityProvider = useMemo(() => {
    if (!data?.users) return false;
    const emailCounts = new Map<string, number>();
    for (const user of data.users) {
      emailCounts.set(user.email, (emailCounts.get(user.email) ?? 0) + 1);
    }
    return Array.from(emailCounts.values()).some((count) => count > 1);
  }, [data?.users]);

  // Build table columns dynamically
  const columns = useMemo((): Column<UserRow>[] => {
    const cols: Column<UserRow>[] = [
      {
        key: 'email',
        header: 'Email',
        render: (item) => (
          <Link
            to={`/admin/users/${encodeURIComponent(item.cognito_username)}`}
            className="text-sm font-medium text-[#0a9c88] hover:underline"
          >
            {item.email}
          </Link>
        ),
      },
    ];

    if (showIdentityProvider) {
      cols.push({
        key: 'identity_provider',
        header: 'Provider',
        render: (item) => (
          <span className="text-sm text-[#102247]/70 capitalize">{item.identity_provider}</span>
        ),
      });
    }

    cols.push(
      {
        key: 'tier',
        header: 'Tier',
        render: (item) => {
          const colors: Record<string, string> = {
            free: 'bg-gray-100 text-gray-700',
            pro: 'bg-[#0a9c88]/10 text-[#0a9c88]',
            business: 'bg-[#102247]/10 text-[#102247]',
          };
          return (
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${colors[item.tier] ?? 'bg-gray-100 text-gray-700'}`}
            >
              {item.tier}
            </span>
          );
        },
      },
      {
        key: 'status',
        header: 'Status',
        render: (item) => (
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${
              item.status === 'enabled' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
            }`}
          >
            {item.status}
          </span>
        ),
      },
      {
        key: 'created_date',
        header: 'Created',
        render: (item) => (
          <span className="text-sm text-[#102247]/70">
            {new Date(item.created_date).toLocaleDateString(undefined, {
              year: 'numeric',
              month: 'short',
              day: 'numeric',
            })}
          </span>
        ),
      },
      {
        key: 'last_active',
        header: 'Last Active',
        render: (item) =>
          item.last_active ? (
            <span className="text-sm text-[#102247]/70">
              {new Date(item.last_active).toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric',
              })}
            </span>
          ) : (
            <span className="text-sm text-[#102247]/40">—</span>
          ),
      },
      {
        key: 'actions',
        header: 'Actions',
        render: (item) => (
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => {
                e.preventDefault();
                handleToggleClick(item);
              }}
              disabled={mutatingUser === item.cognito_username}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                item.status === 'enabled'
                  ? 'border border-red-200 bg-red-50 text-red-700 hover:bg-red-100'
                  : 'border border-green-200 bg-green-50 text-green-700 hover:bg-green-100'
              }`}
              title={item.status === 'enabled' ? 'Disable user' : 'Enable user'}
            >
              {item.status === 'enabled' ? (
                <>
                  <ToggleLeft className="h-3.5 w-3.5" />
                  Disable
                </>
              ) : (
                <>
                  <ToggleRight className="h-3.5 w-3.5" />
                  Enable
                </>
              )}
            </button>
            <button
              onClick={(e) => {
                e.preventDefault();
                handleDeleteClick(item);
              }}
              disabled={mutatingUser === item.cognito_username}
              className="inline-flex items-center gap-1.5 rounded-lg border border-red-300 bg-white px-3 py-1.5 text-xs font-medium text-red-700 transition-colors hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed"
              title="Permanently delete user"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          </div>
        ),
      }
    );

    return cols;
  }, [showIdentityProvider, mutatingUser]);

  return (
    <div className="space-y-6">
      {/* Notification */}
      <AdminNotification
        message={notification.message}
        type={notification.type}
        visible={notification.visible}
        onClose={() => setNotification((prev) => ({ ...prev, visible: false }))}
      />

      {/* Confirm Dialog for disable/enable */}
      <ConfirmDialog
        open={confirmTarget !== null}
        title={confirmTarget?.status === 'enabled' ? 'Disable User' : 'Enable User'}
        message={
          confirmTarget?.status === 'enabled'
            ? `Are you sure you want to disable ${confirmTarget?.email ?? 'this user'}? They will not be able to sign in.`
            : `Are you sure you want to re-enable ${confirmTarget?.email ?? 'this user'}?`
        }
        confirmLabel={confirmTarget?.status === 'enabled' ? 'Disable' : 'Enable'}
        variant="danger"
        onConfirm={handleConfirmToggle}
        onCancel={() => setConfirmTarget(null)}
      />

      {/* Confirm Dialog for permanent delete */}
      <ConfirmDialog
        open={deleteTarget !== null}
        title="Permanently Delete User"
        message={`This will permanently delete ${deleteTarget?.email ?? 'this user'}'s account and usage data. This cannot be undone — the account cannot be recovered.`}
        confirmLabel="Delete permanently"
        variant="danger"
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* Page header */}
      <div className="flex items-center gap-3">
        <Users className="h-6 w-6 text-[#0a9c88]" />
        <h1 className="text-2xl font-bold text-[#102247]">Users</h1>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {loading && !data ? (
          <div className="col-span-full flex items-center justify-center py-6">
            <LoaderCircle className="h-5 w-5 animate-spin text-[#0a9c88]" />
            <span className="ml-2 text-sm text-[#102247]/60">Loading stats...</span>
          </div>
        ) : (
          <>
            <StatsCard
              icon={<Users className="h-5 w-5" />}
              label="Total Users"
              value={data?.stats.total_users ?? '—'}
              subText="All registered accounts"
            />
            <StatsCard
              icon={<UserCheck className="h-5 w-5" />}
              label="Free"
              value={data?.stats.free_count ?? '—'}
              subText="Free tier users"
            />
            <StatsCard
              icon={<Crown className="h-5 w-5" />}
              label="Pro"
              value={data?.stats.pro_count ?? '—'}
              subText="Pro tier users"
            />
            <StatsCard
              icon={<Building2 className="h-5 w-5" />}
              label="Business"
              value={data?.stats.business_count ?? '—'}
              subText="Business tier users"
            />
          </>
        )}
      </div>

      {/* Filter bar */}
      <FilterBar
        searchValue={searchEmail}
        onSearchChange={handleSearchChange}
        tierFilter={tierFilter}
        onTierChange={handleTierChange}
        statusFilter={statusFilter}
        onStatusChange={handleStatusChange}
      />

      {/* Error state */}
      {error && (
        <div className="flex items-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-4">
          <AlertCircle className="h-5 w-5 shrink-0 text-red-600" />
          <p className="flex-1 text-sm font-medium text-red-800">{error}</p>
          <button
            onClick={fetchUsers}
            className="rounded-lg bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-200 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {/* Data Table */}
      {loading && !data && !error ? (
        <div className="rounded-2xl border border-[#dce5f2] bg-white shadow-sm overflow-hidden">
          <div className="flex items-center justify-center py-16">
            <LoaderCircle className="h-6 w-6 animate-spin text-[#0a9c88]" />
            <span className="ml-2 text-sm text-[#102247]/60">Loading users...</span>
          </div>
        </div>
      ) : data && !error ? (
        <DataTable<UserRow>
          columns={columns}
          data={data.users as unknown as UserRow[]}
          page={page}
          totalPages={data.total_pages}
          pageSize={pageSize}
          onPageChange={setPage}
          onPageSizeChange={handlePageSizeChange}
          loading={loading}
        />
      ) : null}
    </div>
  );
}
