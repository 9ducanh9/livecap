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
