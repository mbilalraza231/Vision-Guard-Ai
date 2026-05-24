import { Bell, ChevronLeft, ChevronRight, Flame, Shield, PersonStanding, AlertCircle } from 'lucide-react';
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

const eventConfigs: Record<string, { icon: any; color: string; label: string; bg: string; border: string }> = {
  fire: { icon: Flame, color: 'text-orange-500', label: 'Fire Detected', bg: 'bg-orange-500/10', border: 'border-orange-500/20' },
  weapon: { icon: Shield, color: 'text-red-500', label: 'Weapon Detected', bg: 'bg-red-500/10', border: 'border-red-500/20' },
  fall: { icon: PersonStanding, color: 'text-blue-500', label: 'Fall Detected', bg: 'bg-blue-500/10', border: 'border-blue-500/20' },
};

interface HeaderProps {
  title?: string;
  showDateNav?: boolean;
}

export function Header({ title, showDateNav = true }: HeaderProps) {
  const { logout } = useAuth();
  const { data: user } = useProfile();
  const navigate = useNavigate();
  const today = new Date();

  // Passively read from the SSE cache populated by useGlobalSSE (DashboardLayout).
  // Zero HTTP requests — the global SSE stream already pushes recentEvents every 1.5s.
  const { data: sseRecentEvents } = useQuery<{ total: number; events: any[] }>(
    { queryKey: ['dashboard-recent-events'], enabled: false }
  );
  const notificationData = sseRecentEvents;

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
          <DropdownMenuContent align="end" className="w-80 p-1 bg-background/95 backdrop-blur-md border border-border/80 shadow-2xl rounded-xl">
            <DropdownMenuLabel className="px-3 py-2 flex items-center justify-between">
              <span className="text-xs font-bold tracking-wide">Recent Alerts (24h)</span>
              <span className="text-[10px] font-bold text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-0.5 rounded-full animate-pulse">
                {notificationData?.total ?? 0} Active
              </span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator className="bg-border/50" />
            {notificationData?.events && notificationData.events.length > 0 ? (
              <div className="max-h-[300px] overflow-y-auto">
                {notificationData.events.map((event) => {
                  const config = eventConfigs[event.event_type.toLowerCase()] || {
                    icon: AlertCircle,
                    color: 'text-yellow-500',
                    label: `${event.event_type} Detected`,
                    bg: 'bg-yellow-500/10',
                    border: 'border-yellow-500/20',
                  };
                  const Icon = config.icon;
                  return (
                    <DropdownMenuItem
                      key={event.id}
                      className="flex items-center gap-3 p-3 cursor-pointer hover:bg-secondary/40 focus:bg-secondary/40 border-b border-border/30 last:border-b-0 transition-colors"
                      onClick={() => navigate(`/incidents/${event.id}`)}
                    >
                      <div className={`h-9 w-9 rounded-lg ${config.bg} border ${config.border} flex items-center justify-center shrink-0`}>
                        <Icon className={`h-5 w-5 ${config.color}`} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-xs font-semibold text-foreground truncate">{config.label}</p>
                          <span className="text-[10px] text-muted-foreground whitespace-nowrap">
                            {new Date(event.start_ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                        <p className="text-[10px] text-muted-foreground truncate mt-0.5">
                          Camera: <span className="font-mono text-foreground/80">{event.camera_id}</span>
                        </p>
                      </div>
                    </DropdownMenuItem>
                  );
                })}
                <DropdownMenuSeparator className="bg-border/50 m-1" />
                <DropdownMenuItem
                  className="flex items-center justify-center text-xs text-primary font-semibold py-2 cursor-pointer hover:bg-secondary/40 focus:bg-secondary/40 rounded-lg"
                  onClick={() => navigate('/incidents')}
                >
                  View All Incidents
                </DropdownMenuItem>
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-muted-foreground">
                <Bell className="h-8 w-8 mx-auto mb-2 opacity-20" />
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
