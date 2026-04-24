import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon: LucideIcon;
  iconBgColor?: string;
  trend?: {
    value: string;
    positive?: boolean;
  };
}

export function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  iconBgColor = 'bg-primary/10',
  trend,
}: StatCardProps) {
  return (
    <div className="stat-card flex items-start gap-4">
      <div className={cn('flex h-12 w-12 items-center justify-center rounded-xl', iconBgColor)}>
        <Icon className="h-6 w-6 text-primary" />
      </div>
      <div className="flex-1">
        <p className="text-sm text-muted-foreground">{title}</p>
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-bold">{value}</span>
          {trend && (
            <span
              className={cn(
                'text-xs font-medium',
                trend.positive ? 'text-status-resolved' : 'text-muted-foreground'
              )}
            >
              {trend.value}
            </span>
          )}
        </div>
        {subtitle && <p className="text-xs text-muted-foreground mt-0.5">{subtitle}</p>}
      </div>
    </div>
  );
}
