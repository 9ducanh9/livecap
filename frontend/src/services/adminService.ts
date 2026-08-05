import { authenticatedFetch } from './authService';

function apiBaseUrl(): string {
  const configured = String(import.meta.env.VITE_API_BASE_URL ?? '').trim();
  return configured ? configured.replace(/\/$/, '') : '';
}

export class AdminAccessError extends Error {}

export interface AdminUserRow {
  user_id: string;
  email: string;
  tier: 'free' | 'pro' | 'business' | string;
  sessions_used: number;
  minutes_used: number;
  subscription_status: string | null;
}

export interface AdminOverview {
  users: AdminUserRow[];
  stats: {
    total_users: number;
    by_tier: Record<string, number>;
    total_sessions_this_month: number;
    total_minutes_this_month: number;
    estimated_mrr_usd: number;
  };
  system: {
    backend_reachable: boolean;
    desired_count: number | null;
    running_count: number | null;
    pending_count: number | null;
  };
}

// --- Phase 2: Mutation Response Interfaces ---

export interface ActionResult {
  success: boolean;
  message: string;
  warning?: string | null;
}

export interface TierChangeResult {
  success: boolean;
  message: string;
  updated_user?: UserRecord | null;
  warning?: string | null;
}

// --- Phase 1: User Management Interfaces ---

export interface UserRecord {
  cognito_username: string;
  email: string;
  tier: 'free' | 'pro' | 'business';
  status: 'enabled' | 'disabled';
  identity_provider: string;
  created_date: string;
  last_active: string | null;
  sessions_used: number;
  minutes_used: number;
  subscription_status: string | null;
}

export interface PaginatedUsers {
  users: UserRecord[];
  page: number;
  page_size: number;
  total_pages: number;
  total_users: number;
  stats: {
    total_users: number;
    free_count: number;
    pro_count: number;
    business_count: number;
  };
}

export interface AuditLogEntry {
  entry_id: string;
  admin_user_id: string;
  target_user_id: string;
  action_type: string;
  previous_value: string | null;
  new_value: string | null;
  timestamp: string;
}

export interface UserDetail {
  profile: UserRecord;
  usage_history: { month: string; sessions_used: number; minutes_used: number }[];
  transcript_sessions: {
    session_id: string;
    created_at: string;
    segment_count: number;
    duration_seconds: number | null;
  }[];
  audit_log: AuditLogEntry[];
  has_stripe_subscription: boolean;
}

export interface UserListParams {
  page?: number;
  page_size?: number;
  search_email?: string;
  filter_tier?: string;
  filter_status?: string;
}

// --- Phase 1: User Management API Calls ---

/** Fetches paginated user list with optional search/filter params.
 * Throws AdminAccessError for 401/403 responses. */
export async function getUsers(params: UserListParams = {}): Promise<PaginatedUsers> {
  const query = new URLSearchParams();
  if (params.page != null) query.set('page', String(params.page));
  if (params.page_size != null) query.set('page_size', String(params.page_size));
  if (params.search_email) query.set('search_email', params.search_email);
  if (params.filter_tier) query.set('filter_tier', params.filter_tier);
  if (params.filter_status) query.set('filter_status', params.filter_status);

  const qs = query.toString();
  const url = `${apiBaseUrl()}/api/admin/users${qs ? `?${qs}` : ''}`;
  const response = await authenticatedFetch(url);

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to view the user list.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    throw new AdminAccessError('Could not load the user list. Please try again.');
  }
  return (await response.json()) as PaginatedUsers;
}

/** Fetches detailed information for a single user by cognito username.
 * Throws AdminAccessError for 401/403 responses. */
export async function getUserDetail(username: string): Promise<UserDetail> {
  const response = await authenticatedFetch(
    `${apiBaseUrl()}/api/admin/users/${encodeURIComponent(username)}`
  );

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to view user details.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    throw new AdminAccessError('Could not load user details. Please try again.');
  }
  return (await response.json()) as UserDetail;
}

/** Fetches the admin dashboard payload. Throws AdminAccessError with a
 * user-facing message for 401 (sign in required) and 403 (not an admin). */
export async function getAdminOverview(): Promise<AdminOverview> {
  const response = await authenticatedFetch(`${apiBaseUrl()}/api/admin/overview`);
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to view the admin dashboard.');
  }
  if (!response.ok) {
    throw new AdminAccessError('Could not load the admin dashboard. Please try again.');
  }
  return (await response.json()) as AdminOverview;
}

// --- Phase 2: Mutation API Calls ---

/** Parses error detail from a non-OK response body.
 * Falls back to a generic message if parsing fails. */
async function parseErrorDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (body && typeof body.detail === 'string') {
      return body.detail;
    }
  } catch {
    // JSON parsing failed — use fallback
  }
  return fallback;
}

/** Disables a user account via Cognito.
 * Throws AdminAccessError for auth/permission issues or operation failures. */
export async function disableUser(username: string): Promise<ActionResult> {
  const response = await authenticatedFetch(
    `${apiBaseUrl()}/api/admin/users/${encodeURIComponent(username)}/disable`,
    { method: 'POST' }
  );

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to perform this action.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    const detail = await parseErrorDetail(response, 'Failed to disable user. Please try again.');
    throw new AdminAccessError(detail);
  }
  return (await response.json()) as ActionResult;
}

/** Enables a previously disabled user account via Cognito.
 * Throws AdminAccessError for auth/permission issues or operation failures. */
export async function enableUser(username: string): Promise<ActionResult> {
  const response = await authenticatedFetch(
    `${apiBaseUrl()}/api/admin/users/${encodeURIComponent(username)}/enable`,
    { method: 'POST' }
  );

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to perform this action.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    const detail = await parseErrorDetail(response, 'Failed to enable user. Please try again.');
    throw new AdminAccessError(detail);
  }
  return (await response.json()) as ActionResult;
}

/** Triggers a password reset for a user via Cognito.
 * Throws AdminAccessError for auth/permission issues or if user is federated-only. */
export async function resetPassword(username: string): Promise<ActionResult> {
  const response = await authenticatedFetch(
    `${apiBaseUrl()}/api/admin/users/${encodeURIComponent(username)}/reset-password`,
    { method: 'POST' }
  );

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to perform this action.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    const detail = await parseErrorDetail(response, 'Failed to reset password. Please try again.');
    throw new AdminAccessError(detail);
  }
  return (await response.json()) as ActionResult;
}

/** Permanently deletes a user's Cognito account and usage-table rows.
 * Irreversible -- there is no "undo" endpoint. Throws AdminAccessError for
 * auth/permission issues or operation failures. */
export async function deleteUser(username: string): Promise<ActionResult> {
  const response = await authenticatedFetch(
    `${apiBaseUrl()}/api/admin/users/${encodeURIComponent(username)}`,
    { method: 'DELETE' }
  );

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to perform this action.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    const detail = await parseErrorDetail(response, 'Failed to delete user. Please try again.');
    throw new AdminAccessError(detail);
  }
  return (await response.json()) as ActionResult;
}

// --- Phase 3: Analytics Interfaces ---

export interface DateRangeParams {
  start_month?: string;
  end_month?: string;
}

export interface UsageAnalytics {
  months: { month: string; total_sessions: number; total_minutes: number; unique_active_users: number }[];
  totals: { total_sessions: number; total_minutes: number; unique_active_users: number };
  tier_distribution: Record<string, { count: number; percentage: number }>;
}

export interface TopUser {
  email: string;
  tier: string;
  sessions_used: number;
  minutes_used: number;
}

/** Changes a user's subscription tier.
 * Throws AdminAccessError for auth/permission issues, invalid tier, or operation failures. */
export async function changeTier(username: string, tier: string): Promise<TierChangeResult> {
  const response = await authenticatedFetch(
    `${apiBaseUrl()}/api/admin/users/${encodeURIComponent(username)}/change-tier`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier }),
    }
  );

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to perform this action.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    const detail = await parseErrorDetail(response, 'Failed to change tier. Please try again.');
    throw new AdminAccessError(detail);
  }
  return (await response.json()) as TierChangeResult;
}

// --- Phase 3: Analytics API Calls ---

/** Fetches aggregated usage analytics with optional date range filtering.
 * Throws AdminAccessError for 401/403 responses. */
export async function getUsageAnalytics(params?: DateRangeParams): Promise<UsageAnalytics> {
  const query = new URLSearchParams();
  if (params?.start_month) query.set('start_month', params.start_month);
  if (params?.end_month) query.set('end_month', params.end_month);

  const qs = query.toString();
  const url = `${apiBaseUrl()}/api/admin/usage${qs ? `?${qs}` : ''}`;
  const response = await authenticatedFetch(url);

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to view usage analytics.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    throw new AdminAccessError('Could not load usage analytics. Please try again.');
  }
  return (await response.json()) as UsageAnalytics;
}

/** Fetches top users by minutes used for a given month.
 * Throws AdminAccessError for 401/403 responses. */
export async function getTopUsers(month?: string): Promise<TopUser[]> {
  const query = new URLSearchParams();
  if (month) query.set('month', month);

  const qs = query.toString();
  const url = `${apiBaseUrl()}/api/admin/usage/top-users${qs ? `?${qs}` : ''}`;
  const response = await authenticatedFetch(url);

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to view top users.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    throw new AdminAccessError('Could not load top users data. Please try again.');
  }
  return (await response.json()) as TopUser[];
}

// --- Phase 4: Revenue & System Health Interfaces ---

export interface RevenueTransaction {
  date: string;
  user_email: string | null;
  amount_cents: number;
  currency: string;
  transaction_type: string;
}

export interface RevenueData {
  mrr_usd: number;
  active_subscriptions: number;
  churned_subscriptions: number;
  recent_transactions: RevenueTransaction[];
  stripe_data_available: boolean;
  warning: string | null;
}

export interface EcsStatus {
  running_count: number;
  desired_count: number;
  pending_count: number;
  health_status: string;
}

export interface CloudWatchAlarm {
  alarm_name: string;
  state: string;
  reason: string | null;
}

export interface CostEstimate {
  current_month_usd: number;
  data_timestamp: string;
}

export interface SystemHealth {
  ecs: EcsStatus;
  alarms: CloudWatchAlarm[];
  cost_estimate: CostEstimate | null;
  warnings: string[];
}

// --- Phase 4: Revenue & System Health API Calls ---

/** Fetches revenue metrics including MRR, subscriptions, and recent transactions.
 * Handles partial data when Stripe is unreachable (stripe_data_available=false with warning).
 * Throws AdminAccessError for 401/403 responses. */
export async function getRevenue(): Promise<RevenueData> {
  const response = await authenticatedFetch(`${apiBaseUrl()}/api/admin/revenue`);

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to view revenue data.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    throw new AdminAccessError('Could not load revenue data. Please try again.');
  }
  return (await response.json()) as RevenueData;
}

/** Fetches system health data including ECS status, CloudWatch alarms, and cost estimate.
 * The response may contain partial data with warnings if individual AWS services are unreachable.
 * Throws AdminAccessError for 401/403 responses. */
export async function getSystemHealth(): Promise<SystemHealth> {
  const response = await authenticatedFetch(`${apiBaseUrl()}/api/admin/system`);

  if (response.status === 401) {
    throw new AdminAccessError('Sign in is required to view system health.');
  }
  if (response.status === 403) {
    throw new AdminAccessError('Your account does not have admin access.');
  }
  if (!response.ok) {
    throw new AdminAccessError('Could not load system health data. Please try again.');
  }
  return (await response.json()) as SystemHealth;
}
