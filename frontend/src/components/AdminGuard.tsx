import { Outlet } from 'react-router-dom';
import { ShieldX } from 'lucide-react';
import { isAdminUser } from '../services/authService';

/**
 * AdminGuard sits inside AuthGate (user is already signed in).
 * It checks whether the signed-in user belongs to the Cognito "admin" group.
 * - If yes: renders the nested routes (Outlet).
 * - If no: shows an access-denied page with a link back to the workspace.
 */
export default function AdminGuard() {
  if (isAdminUser()) {
    return <Outlet />;
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-paper px-4">
      <div className="w-full max-w-md text-center">
        <div className="flex justify-center mb-6">
          <span className="grid h-16 w-16 place-items-center rounded-2xl bg-crimson/10">
            <ShieldX className="h-8 w-8 text-crimson" />
          </span>
        </div>
        <h1 className="font-instrument text-2xl font-bold text-ink">Access Denied</h1>
        <p className="mt-3 text-sm text-ink-muted leading-relaxed">
          You don't have permission to access the admin panel. This area is restricted to administrators only.
        </p>
        <a
          href="/app"
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-emerald-pro px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-emerald-pro/90"
        >
          Back to workspace
        </a>
      </div>
    </main>
  );
}
