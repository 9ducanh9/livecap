import LandingPage from './LandingPage';
import DashboardPage from './DashboardPage';

export default function App() {
  const path = window.location.pathname;

  if (path === '/app') {
    return <DashboardPage />;
  }

  return <LandingPage />;
}
