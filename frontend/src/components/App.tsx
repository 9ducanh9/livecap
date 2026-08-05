import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { LoaderCircle } from 'lucide-react';
import LandingPage from './LandingPage';
import DashboardPage from './DashboardPage';
import AdminShell from './AdminShell';
import AdminGuard from './AdminGuard';
import AuthGate from './AuthGate';
import PrivacyPolicyPage from './PrivacyPolicyPage';

// Lazy-loaded admin sub-pages
const AdminUsersPage = lazy(() => import('./admin/AdminUsersPage'));
const AdminUserDetailPage = lazy(() => import('./admin/AdminUserDetailPage'));
const AdminUsagePage = lazy(() => import('./admin/AdminUsagePage'));
const AdminRevenuePage = lazy(() => import('./admin/AdminRevenuePage'));
const AdminSystemPage = lazy(() => import('./admin/AdminSystemPage'));

function PageLoader() {
  return (
    <div className="min-h-screen grid place-items-center bg-paper">
      <LoaderCircle className="h-6 w-6 animate-spin text-emerald-pro" />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Public landing */}
          <Route path="/" element={<LandingPage />} />
          <Route path="/privacy" element={<PrivacyPolicyPage />} />

          {/* Authenticated workspace */}
          <Route
            path="/app"
            element={
              <AuthGate>
                <DashboardPage />
              </AuthGate>
            }
          />

          {/* Admin panel — requires authentication + admin group */}
          <Route
            path="/admin/*"
            element={
              <AuthGate>
                <AdminGuard />
              </AuthGate>
            }
          >
            <Route element={<AdminShell />}>
              <Route index element={<Navigate to="/admin/users" replace />} />
              <Route path="users" element={<AdminUsersPage />} />
              <Route path="users/:username" element={<AdminUserDetailPage />} />
              <Route path="usage" element={<AdminUsagePage />} />
              <Route path="revenue" element={<AdminRevenuePage />} />
              <Route path="system" element={<AdminSystemPage />} />
            </Route>
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}
