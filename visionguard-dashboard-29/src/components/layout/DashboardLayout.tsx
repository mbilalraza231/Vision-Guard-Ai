import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';

export function DashboardLayout() {
  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 md:ml-56">
        <Outlet />
      </main>
    </div>
  );
}
