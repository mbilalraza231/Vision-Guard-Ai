import { NavLink, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  Monitor,
  AlertTriangle,
  BarChart3,
  Camera,
  MapPin,
  Users,
  Settings,
  Menu,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';

interface NavItem {
  label: string;
  path: string;
  icon: React.ComponentType<{ className?: string }>;
}

const navItems: NavItem[] = [
  { label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
  { label: 'Live Monitoring', path: '/monitoring', icon: Monitor },
  { label: 'Incidents', path: '/incidents', icon: AlertTriangle },
  { label: 'Analytics', path: '/analytics', icon: BarChart3 },
  { label: 'Cameras', path: '/cameras', icon: Camera },
  { label: 'Zones', path: '/zones', icon: MapPin },
  { label: 'Users', path: '/users', icon: Users },
  { label: 'Settings', path: '/settings', icon: Settings },
];

export function Sidebar() {
  const location = useLocation();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMobileOpen, setIsMobileOpen] = useState(false);

  return (
    <>
      {/* Mobile menu button */}
      <Button
        variant="ghost"
        size="icon"
        className="fixed left-4 top-4 z-50 md:hidden"
        onClick={() => setIsMobileOpen(!isMobileOpen)}
      >
        {isMobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </Button>

      {/* Mobile overlay */}
      {isMobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-background/80 backdrop-blur-sm md:hidden"
          onClick={() => setIsMobileOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          'fixed left-0 top-0 z-40 flex h-screen flex-col border-r border-sidebar-border bg-sidebar transition-all duration-300',
          isCollapsed ? 'w-20' : 'w-56',
          isMobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        )}
      >
        {/* Logo */}
        <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
            <Camera className="h-5 w-5 text-primary" />
          </div>
          {!isCollapsed && (
            <div className="flex flex-col">
              <span className="font-semibold text-foreground">VisionGuard AI</span>
              <span className="text-xs text-muted-foreground">v2.0</span>
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path || 
              (item.path !== '/dashboard' && location.pathname.startsWith(item.path));

            return (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setIsMobileOpen(false)}
                className={cn(
                  'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all',
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                    : 'text-sidebar-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground'
                )}
              >
                <Icon className={cn('h-5 w-5 flex-shrink-0', isActive && 'text-primary')} />
                {!isCollapsed && <span>{item.label}</span>}
              </NavLink>
            );
          })}
        </nav>

        {/* Collapse button - desktop only */}
        <div className="hidden border-t border-sidebar-border p-3 md:block">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-3 text-sidebar-foreground"
            onClick={() => setIsCollapsed(!isCollapsed)}
          >
            <Menu className="h-5 w-5" />
            {!isCollapsed && <span>Collapse</span>}
          </Button>
        </div>
      </aside>
    </>
  );
}
