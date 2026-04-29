import { GaugeChart } from './GaugeChart';
import { BarIndicator } from './BarIndicator';
import { Badge } from '@/components/ui/badge';
import type { SystemMetrics } from '@/types';

interface SystemUsageCardProps {
  metrics: SystemMetrics;
}

export function SystemUsageCard({ metrics }: SystemUsageCardProps) {
  return (
    <div className="dashboard-card p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">System Usage</h2>
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className={
              metrics.isOperational
                ? 'border-status-online text-status-online'
                : 'border-status-offline text-status-offline'
            }
          >
            {metrics.isOperational ? 'Operational' : 'Issues Detected'}
          </Badge>
          <span className="text-sm text-muted-foreground">
            Updated {metrics.lastUpdated}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* CPU Usage */}
        <div className="rounded-xl bg-secondary/30 p-4">
          <div className="flex items-center justify-between mb-4">
            <span className="font-medium">CPU Usage</span>
            <span className="text-sm text-muted-foreground">{metrics.cpuCores}</span>
          </div>
          <GaugeChart value={metrics.cpuUsage} />
        </div>

        {/* Memory */}
        <div className="rounded-xl bg-secondary/30 p-4">
          <div className="flex items-center justify-between mb-4">
            <span className="font-medium">Memory</span>
            <span className="text-sm text-muted-foreground">
              {metrics.memoryUsed}GB / {metrics.memoryTotal}GB
            </span>
          </div>
          <div className="flex items-end justify-center gap-2 h-32">
            <BarIndicator
              value={metrics.memoryUsed}
              max={metrics.memoryTotal}
              className="w-full"
            />
          </div>
        </div>

        {/* Storage */}
        <div className="rounded-xl bg-secondary/30 p-4">
          <div className="flex items-center justify-between mb-4">
            <span className="font-medium">Storage</span>
            <span className="text-sm text-muted-foreground">
              {metrics.incidentsStored.toLocaleString()} Incidents
            </span>
          </div>
          <div className="flex items-end justify-center gap-2 h-32">
            <BarIndicator
              value={metrics.storageUsed}
              max={metrics.storageTotal}
              unit="MB"
              className="w-full"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
