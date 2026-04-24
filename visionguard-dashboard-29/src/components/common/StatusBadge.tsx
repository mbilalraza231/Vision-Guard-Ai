import { cn } from '@/lib/utils';
import type { Severity, IncidentStatus } from '@/types';

interface SeverityBadgeProps {
  severity: Severity;
  className?: string;
}

const severityColors: Record<Severity, string> = {
  critical: 'text-severity-critical',
  high: 'text-severity-high',
  medium: 'text-severity-medium',
  low: 'text-severity-low',
};

const severityLabels: Record<Severity, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

export function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  return (
    <span className={cn('font-medium text-sm', severityColors[severity], className)}>
      {severityLabels[severity]}
    </span>
  );
}

interface StatusBadgeProps {
  status: IncidentStatus;
  className?: string;
}

const statusColors: Record<IncidentStatus, string> = {
  active: 'text-status-active',
  acknowledged: 'text-status-acknowledged',
  resolved: 'text-status-resolved',
};

const statusLabels: Record<IncidentStatus, string> = {
  active: 'Active',
  acknowledged: 'Acknowledged',
  resolved: 'Resolved',
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span className={cn('font-medium text-sm', statusColors[status], className)}>
      {statusLabels[status]}
    </span>
  );
}
