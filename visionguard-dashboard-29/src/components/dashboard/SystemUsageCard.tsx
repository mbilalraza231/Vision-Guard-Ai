import { GaugeChart } from './GaugeChart';
import { BarIndicator } from './BarIndicator';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle } from 'lucide-react';
import type { SystemMetrics } from '@/types';

interface SystemUsageCardProps {
  metrics: SystemMetrics;
}

export function SystemUsageCard({ metrics }: SystemUsageCardProps) {
  const ecsDetails = metrics.components?.ecs?.details;
  const redisDetails = metrics.components?.redis?.details;
  const cameraDetails = metrics.components?.cameras?.details;

  const ecsStatus = metrics.components?.ecs?.status || 'unknown';
  const redisStatus = metrics.components?.redis?.status || 'unknown';

  const ecsOk = ecsStatus === 'running';
  const redisOk = redisStatus === 'connected';

  // Only gather items that are ACTUALLY FAILED or DEGRADED
  const failures: { name: string; info: string }[] = [];

  if (!redisOk) {
    failures.push({
      name: 'Redis Message Bus',
      info: redisDetails?.error || 'Connection lost or broker error. Stream processing paused.'
    });
  }

  if (!ecsOk) {
    failures.push({
      name: 'ECS Classification Engine',
      info: ecsDetails?.last_error || 'Classification service is stopped. Real-time threat evaluation offline.'
    });
  }

  if (cameraDetails?.last_error) {
    failures.push({
      name: 'Camera Pipeline',
      info: cameraDetails.last_error
    });
  }

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

      {/* CONDITIONAL FAILURE ALERT - ONLY RENDERED IF SOMETHING IS ACTUALLY FAILED / NOT ACTIVE */}
      {failures.length > 0 && (
        <div className="mb-6 rounded-lg bg-destructive/10 border border-destructive/20 p-4">
          <div className="flex items-center gap-2 font-semibold text-destructive text-sm mb-2">
            <AlertTriangle className="w-4 h-4" />
            <span>Inactive / Failed Component Diagnostics:</span>
          </div>
          <div className="space-y-1.5">
            {failures.map((f, i) => (
              <div key={i} className="text-xs text-muted-foreground flex items-start gap-2">
                <span className="font-semibold text-destructive">• {f.name}:</span>
                <span className="text-foreground">{f.info}</span>
              </div>
            ))}
          </div>
        </div>
      )}

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
