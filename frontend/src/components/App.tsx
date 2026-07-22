import LandingPage from './LandingPage';
import DashboardPage from './DashboardPage';
import AdminDashboardPage from './AdminDashboardPage';
import AuthGate from './AuthGate';

export default function App() {
  const path = window.location.pathname;

  if (path === '/app') {
    return <AuthGate><DashboardPage /></AuthGate>;
  }

  if (path === '/admin') {
    return <AuthGate><AdminDashboardPage /></AuthGate>;
  }

  return <LandingPage />;
}
