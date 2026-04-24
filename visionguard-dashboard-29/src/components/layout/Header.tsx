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
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';

interface HeaderProps {
  title?: string;
  showDateNav?: boolean;
}

export function Header({ title, showDateNav = true }: HeaderProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const today = new Date();

  const handleLogout = async () => {
    await logout();
    navigate('/auth/login');
  };

  // Mock user for development
  const displayUser = user || {
    name: 'Fayaz Ali',
    email: 'fayaz@example.com',
    role: 'admin',
    avatar: undefined,
  };

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

        {/* Notifications */}
        <Button variant="ghost" size="icon" className="relative">
          <Bell className="h-5 w-5" />
          <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-severity-critical text-[10px] font-medium text-white">
            4
          </span>
        </Button>

        {/* User Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-10 w-10 rounded-full p-0">
              <Avatar className="h-10 w-10">
                <AvatarImage src={displayUser.avatar} alt={displayUser.name} />
                <AvatarFallback className="bg-primary text-primary-foreground">
                  {displayUser.name
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
                <span>{displayUser.name}</span>
                <span className="text-xs font-normal text-muted-foreground">
                  {displayUser.email}
                </span>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => navigate('/settings')}>
              Settings
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate('/users')}>
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
