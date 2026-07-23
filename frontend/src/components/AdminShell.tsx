import { Suspense } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import {
  Users,
  BarChart3,
  DollarSign,
  Activity,
  ArrowLeft,
  LoaderCircle,
} from 'lucide-react';

const navItems = [
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/usage', label: 'Usage', icon: BarChart3 },
  { to: '/admin/revenue', label: 'Revenue', icon: DollarSign },
  { to: '/admin/system', label: 'System', icon: Activity },
] as const;

export default function AdminShell() {
  return (
    <div className="flex min-h-screen bg-paper font-ui antialiased">
      {/* Sidebar */}
      <aside className="hidden md:flex md:w-60 lg:w-64 flex-col border-r border-[#dce5f2] bg-white">
        {/* Logo area */}
        <div className="flex items-center gap-3 border-b border-[#dce5f2] px-5 py-4">
          <img src="/LiveCap.svg" alt="" className="h-9 w-9 rounded-xl" />
          <span className="font-instrument text-lg font-bold tracking-[-0.08em] text-ink">
            Admin
          </span>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-emerald-pro/10 text-emerald-pro'
                    : 'text-ink-muted hover:bg-[#f7f8fc] hover:text-ink'
                }`
              }
            >
              <Icon className="h-4.5 w-4.5 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* Back to workspace */}
        <div className="border-t border-[#dce5f2] px-3 py-4">
          <a
            href="/app"
            className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-ink-muted transition-colors hover:bg-[#f7f8fc] hover:text-ink"
          >
            <ArrowLeft className="h-4 w-4 shrink-0" />
            Back to workspace
          </a>
        </div>
      </aside>

      {/* Mobile top nav */}
      <div className="flex flex-col flex-1 min-w-0">
        <header className="md:hidden sticky top-0 z-50 border-b border-[#dce5f2] bg-white/95 backdrop-blur-sm">
          <div className="flex items-center justify-between px-4 py-3">
            <div className="flex items-center gap-2">
              <img src="/LiveCap.svg" alt="" className="h-8 w-8 rounded-lg" />
              <span className="font-instrument text-base font-bold tracking-[-0.08em] text-ink">
                Admin
              </span>
            </div>
            <a
              href="/app"
              className="flex items-center gap-1.5 text-xs font-semibold text-ink-muted hover:text-ink"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Workspace
            </a>
          </div>
          {/* Mobile tab bar */}
          <nav className="flex border-t border-[#dce5f2] overflow-x-auto">
            {navItems.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 px-4 py-2.5 text-xs font-semibold whitespace-nowrap border-b-2 transition-colors ${
                    isActive
                      ? 'border-emerald-pro text-emerald-pro'
                      : 'border-transparent text-ink-muted hover:text-ink'
                  }`
                }
              >
                <Icon className="h-3.5 w-3.5" />
                {label}
              </NavLink>
            ))}
          </nav>
        </header>

        {/* Main content */}
        <main className="flex-1 p-5 sm:p-8 max-w-[1400px] w-full mx-auto">
          <Suspense
            fallback={
              <div className="flex items-center justify-center py-20">
                <LoaderCircle className="h-6 w-6 animate-spin text-emerald-pro" />
              </div>
            }
          >
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
