import { useEffect } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { useAuth } from '@/contexts/AuthContext';
import { useGlobalSSE } from '@/hooks/useGlobalSSE';
import { Loader2 } from 'lucide-react';

export function DashboardLayout() {
  const { isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  
  // Initialize Global Server-Sent Events to populate React Query cache automatically
  useGlobalSSE();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/auth/login');
    }
  }, [isAuthenticated, isLoading, navigate]);

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar />
      <main className="flex-1 md:ml-56">
        <Outlet />
      </main>
    </div>
  );
}

