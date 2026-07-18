import LandingPage from './LandingPage';
import DashboardPage from './DashboardPage';
import AuthGate from './AuthGate';

export default function App() {
  const path = window.location.pathname;

  if (path === '/app') {
    return <AuthGate><DashboardPage /></AuthGate>;
  }

  return <LandingPage />;
}
