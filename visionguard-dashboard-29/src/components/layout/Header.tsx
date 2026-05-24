import { Bell, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useAuth } from '@/contexts/AuthContext';
import { useProfile } from '@/hooks/useProfile';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { useQuery } from '@tanstack/react-query';
import { apiService } from '@/services/api.service';

interface HeaderProps {
  title?: string;
  showDateNav?: boolean;
}

export function Header({ title, showDateNav = true }: HeaderProps) {
  const { logout } = useAuth();
  const { data: user } = useProfile();
  const navigate = useNavigate();
  const today = new Date();

  // Fetch count of recent alerts in the last 24 hours
  const { data: notificationData } = useQuery({
    queryKey: ['header-notifications'],
    queryFn: () => apiService.getData<{ total: number; events: any[] }>('/events', { time_period: '24h', limit: '5' }),
    staleTime: 1000 * 30, // 30 seconds
    refetchInterval: 1000 * 30, // Poll every 30 seconds
    enabled: !!user,
  });

  const handleLogout = async () => {
    await logout();
    navigate('/auth/login');
  };

  if (!user) {
    return (
      <header className="flex h-16 items-center justify-between border-b border-border bg-background px-6">
        <div className="flex items-center gap-4">
          {title && <h1 className="text-2xl font-bold">{title}</h1>}
        </div>
      </header>
    );
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-border bg-background px-6">
      <div className="flex items-center gap-4">
        {title && <h1 className="text-2xl font-bold">{title}</h1>}
      </div>

      <div className="flex items-center gap-4">
        {/* Date Navigation */}
        {showDateNav && (
          <div className="hidden items-center gap-2 rounded-lg bg-secondary/50 px-3 py-1.5 md:flex">
            <Button variant="ghost" size="icon" className="h-6 w-6">
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm font-medium">
              Today, {format(today, 'MMM d')}
            </span>
            <Button variant="ghost" size="icon" className="h-6 w-6">
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        {/* Notifications Dropdown */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="relative">
              <Bell className="h-5 w-5" />
              {notificationData && notificationData.total > 0 && (
                <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-severity-critical text-[10px] font-medium text-white animate-pulse">
                  {notificationData.total}
                </span>
              )}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80 bg-[#0f1117] border-white/10 text-white shadow-2xl">
            <DropdownMenuLabel className="flex items-center justify-between">
              <span>Recent Alerts (24h)</span>
              <span className="text-[10px] font-normal text-muted-foreground bg-white/5 px-2 py-0.5 rounded">
                {notificationData?.total ?? 0} active
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-white/10" />
            {notificationData?.events && notificationData.events.length > 0 ? (
              <>
                {notificationData.events.map((event) => (
                  <DropdownMenuItem
                    key={event.id}
                    className="flex flex-col items-start gap-1 p-3 cursor-pointer hover:bg-white/5 focus:bg-white/5"
                    onClick={() => navigate(`/incidents/${event.id}`)}
                  >
                    <div className="flex items-center justify-between w-full">
                      <span className="text-xs font-semibold capitalize text-severity-high">
                        {event.event_type} Detected
                      </span>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        {new Date(event.start_ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <span className="text-[10px] text-muted-foreground font-mono">
                      Camera: {event.camera_id}
                    </span>
                  </DropdownMenuItem>
                ))}
                <DropdownMenuSeparator className="bg-white/10" />
                <DropdownMenuItem
                  className="flex items-center justify-center text-xs text-primary font-medium py-2 cursor-pointer hover:bg-white/5 focus:bg-white/5"
                  onClick={() => navigate('/incidents')}
                >
                  View All Incidents
                </DropdownMenuItem>
              </>
            ) : (
              <div className="py-6 text-center text-xs text-muted-foreground">
                No new alerts in the last 24 hours.
              </div>
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        {/* User Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-10 w-10 rounded-full p-0">
              <Avatar className="h-10 w-10">
                <AvatarImage src={user.avatar} alt={user.name} />
                <AvatarFallback className="bg-primary text-primary-foreground">
                  {user.name
                    .split(' ')
                    .map((n) => n[0])
                    .join('')
                    .toUpperCase()}
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="flex flex-col">
                <span>{user.name}</span>
                <span className="text-xs font-normal text-muted-foreground">
                  {user.email}
                </span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate('/settings')}>
              Settings
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate('/profile')}>
              Profile
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout} className="text-severity-critical">
              Logout
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
