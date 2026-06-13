import { Header } from '@/components/layout/Header';
import { StatCard } from '@/components/dashboard/StatCard';
import { AlertCircle, Clock, Target, Activity, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { API_ENDPOINTS, buildApiUrl } from '@/config/api';
import { apiService } from '@/services/api.service';
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSettings } from '@/hooks/useSettings';
import { formatTimeString } from '@/lib/utils';
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

// Backend response types
interface ConfidenceHistoryItem {
  id: string;
  event_type: string;
  confidence: number;
  created_at: number;
}

interface EventsStatsResponse {
  total_events: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
  avg_confidence?: number;
  confidence_history?: ConfidenceHistoryItem[];
  avg_processing_delay?: number;
  false_positive_rate?: number;
}

interface CameraItem {
  id: string;
  name: string;
  source: string;
  fps: number;
  priority: string;
  enabled: boolean;
  status: string;
}

interface StatusResponse {
  status: string;
  timestamp: string;
  uptime_seconds: number;
  components: {
    cameras?: {
      details?: {
        running?: number;
        total?: number;
        cameras?: Record<string, any>;
      }
    }
  };
  cpu_usage: number;
  cpu_cores: number;
  memory_used_gb: number;
  memory_total_gb: number;
}

export default function Analytics() {
  const { t } = useTranslation();
  const { data: settings } = useSettings();
  const timezone = settings?.general?.timezone || 'UTC';
  const [sseSystemStatus, setSseSystemStatus] = useState<StatusResponse | null>(null);
  const [sseError, setSseError] = useState<Error | null>(null);
  const supportsSse = typeof window !== 'undefined' && 'EventSource' in window;
  const { data: stats, isLoading: isStatsLoading, isFetching: isStatsFetching, error: statsError, refetch: refetchStats } = useQuery({
    queryKey: ['analytics-stats'],
    queryFn: () => apiService.getData<EventsStatsResponse>(API_ENDPOINTS.incidents.stats),
    refetchInterval: 5000,
  });

  // Prefer SSE for system status updates (lower overhead than polling).
  // Fall back to polling if SSE is unavailable or errors.
  useEffect(() => {
    if (!supportsSse) return;

    const url = buildApiUrl('/stream');
    const es = new EventSource(url);

    es.onmessage = (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        if (parsed?.status) {
          setSseSystemStatus(parsed.status as StatusResponse);
          setSseError(null);
        }
      } catch (e) {
        setSseError(e instanceof Error ? e : new Error('Failed to parse SSE payload'));
      }
    };

    es.onerror = () => {
      setSseError(new Error('SSE stream disconnected'));
      es.close();
    };

    return () => es.close();
  }, [supportsSse]);

  const usePollingForStatus = !supportsSse || sseError != null;

  const { data: polledSystemStatus, isLoading: isStatusLoading, isFetching: isStatusFetching, error: statusError, refetch: refetchStatus } = useQuery({
    queryKey: ['analytics-status'],
    queryFn: () => apiService.getData<StatusResponse>(API_ENDPOINTS.dashboard.systemMetrics),
    refetchInterval: 5000,
    enabled: usePollingForStatus,
  });

  const systemStatus = usePollingForStatus ? polledSystemStatus : sseSystemStatus;

  const { data: cameras, isFetching: isCamerasFetching, refetch: refetchCameras } = useQuery({
    queryKey: ['analytics-cameras'],
    queryFn: () => apiService.getData<CameraItem[]>(API_ENDPOINTS.cameras.list),
    refetchInterval: 5000,
  });

  const isLoading = isStatsLoading || isStatusLoading;
  const isFetching = isStatsFetching || isStatusFetching || isCamerasFetching;
  const error = statsError || statusError || sseError;

  const refetchAll = () => {
    refetchStats();
    refetchStatus();
    refetchCameras();
  };

  // Transform by_type to chart data
  const detectionByTypeData = useMemo(() => {
    if (!stats?.by_type) return [];
    return Object.entries(stats.by_type).map(([type, count]) => ({
      type: type.charAt(0).toUpperCase() + type.slice(1),
      count,
    }));
  }, [stats]);

  // Transform confidence history to chart data
  const accuracyChartData = useMemo(() => {
    if (!stats?.confidence_history) return [];
    return stats.confidence_history.map((item, index) => {
      const date = new Date(item.created_at * 1000);
      return {
        name: `D${index + 1}`,
        confidence: Math.round(item.confidence * 100),
        type: item.event_type.charAt(0).toUpperCase() + item.event_type.slice(1),
        time: formatTimeString(date.getTime(), timezone),
      };
    });
  }, [stats, timezone]);

  // Calculate real performance metrics
  const performanceMetrics = useMemo(() => {
    if (!systemStatus) return [];

    // 1. Memory Usage (Real)
    const memUsed = systemStatus.memory_used_gb || 0;
    const memTarget = settings?.cameras?.targetMemoryGb || 8.0;
    const memStatus = memUsed > memTarget ? 'critical' : memUsed > memTarget * 0.8 ? 'warning' : 'good';

    // 2. Processing FPS (Real Config Based)
    const cameraDetails = systemStatus.components?.cameras?.details;
    const camerasMap = cameraDetails?.cameras || {};
    const runningCamerasList = Object.values(camerasMap);
    const runningCameras = runningCamerasList.filter((c: any) => c.is_running && c.enabled);
    const enabledCameras = runningCamerasList.filter((c: any) => c.enabled);
    const cameraServiceAlive = Boolean((cameraDetails as any)?.service_alive);
    const totalFramesCaptured = runningCamerasList.reduce((sum, c: any) => sum + (c.frames_captured || 0), 0);
    const totalFramesWithMotion = runningCamerasList.reduce((sum, c: any) => sum + (c.frames_with_motion || 0), 0);
    
    // Target FPS is now driven by the global setting, not the sum of individual cameras
    const targetFpsTotal = settings?.cameras?.globalFpsTarget || 15;
    const currentFps = runningCameras.reduce((sum, c: any) => sum + (c.fps_actual || 0), 0);
    
    const isIdle = runningCameras.length === 0;
    const isEnabledButNoFrames = enabledCameras.length > 0 && runningCameras.length === 0 && cameraServiceAlive;

    // FPS: target is a CEILING (cap), not a minimum.
    // Good = below cap. Warning = above 80% of cap. Critical = exceeding cap.
    const fpsStatus = isIdle ? 'good'
      : currentFps <= targetFpsTotal ? 'good'
      : currentFps <= targetFpsTotal * 1.2 ? 'warning' : 'critical';

    // 3. End-to-end Latency (Real)
    const targetLatency = settings?.cameras?.targetLatencyMs || 500;
    const currentLatency = stats?.avg_processing_delay ? (stats.avg_processing_delay * 1000) : 0;
    // Widened threshold: Warning up to 4x target, Critical after
    const latencyStatus = isIdle ? 'good' : currentLatency === 0 ? 'good' : currentLatency <= targetLatency ? 'good' : currentLatency <= targetLatency * 4 ? 'warning' : 'critical';

    // 4. False Positive Rate (Real Proxy)
    const targetFPR = settings?.cameras?.targetFalsePositiveRate || 5.0;
    const currentFPR = stats?.false_positive_rate || 0.0;
    // Widened threshold: Warning up to 3x target, Critical after
    const fprStatus = isIdle ? 'good' : currentFPR <= targetFPR ? 'good' : currentFPR <= targetFPR * 3 ? 'warning' : 'critical';

    return [
      {
        metric: 'End-to-end Latency',
        target: `<${targetLatency.toFixed(0)}ms`,
        current: isIdle ? 'Idle' : currentLatency > 0 ? `${currentLatency.toFixed(0)}ms` : 'No Events Yet',
        status: latencyStatus,
        note: 'Avg pipeline delay of last 50 events (camera → AI → DB)'
      },
      {
        metric: 'Processing FPS',
        target: `<${targetFpsTotal.toFixed(0)} FPS cap`,
        current: isIdle ? 'Idle' : currentFps === 0 ? 'No frames' : `${currentFps.toFixed(1)} FPS`,
        status: fpsStatus,
        note: 'Total frames AI processes/sec across all cameras. Cap prevents overload.'
      },
      {
        metric: 'Memory Usage',
        target: `<${memTarget.toFixed(1)}GB`,
        current: `${memUsed.toFixed(1)}GB`,
        status: memStatus
      },
      {
        metric: 'False Positive Rate',
        target: `<${targetFPR.toFixed(1)}%`,
        current: isIdle ? 'Idle' : `${currentFPR.toFixed(1)}%`,
        status: fprStatus
      },
    ];
  }, [systemStatus, stats, cameras, settings]);

  if (error) {
    return (
      <div className="min-h-screen">
        <Header title={t('analytics.title')} />
        <div className="p-6 flex flex-col items-center justify-center gap-4 min-h-[60vh]">
          <p className="text-severity-critical text-lg">{t('common.error')}</p>
          <p className="text-muted-foreground text-sm">{(error as Error).message}</p>
          <Button variant="outline" className="gap-2" disabled={isLoading || isFetching} onClick={refetchAll}>
            <RefreshCw className={cn("h-4 w-4", (isLoading || isFetching) && "animate-spin")} />
            {t('common.retry')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header title={t('analytics.title')} />
      <div className="p-6">
        {isLoading && !stats ? (
          <div className="flex items-center justify-center min-h-[40vh]">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : (
          <>
            {/* Stats Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <StatCard
                title={t('dashboard.totalEvents')}
                value={stats?.total_events ?? 0}
                icon={AlertCircle}
              />
              <StatCard
                title={t('dashboard.criticalAlerts')}
                value={stats?.by_severity?.critical ?? 0}
                icon={Clock}
              />
              <StatCard
                title="High Severity"
                value={stats?.by_severity?.high ?? 0}
                icon={Target}
              />
              <StatCard
                title="Medium Severity"
                value={stats?.by_severity?.medium ?? 0}
                icon={Activity}
              />
            </div>

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
              {/* Detection Accuracy */}
              <div className="dashboard-card p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold">Detection Accuracy</h3>
                  {stats?.avg_confidence !== undefined && stats.avg_confidence > 0 && (
                    <div className="text-right">
                      <span className="text-xs text-muted-foreground mr-1">Avg Confidence:</span>
                      <span className="text-sm font-semibold text-primary">
                        {Math.round(stats.avg_confidence * 100)}%
                      </span>
                    </div>
                  )}
                </div>
                <div className="h-64">
                  {accuracyChartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={accuracyChartData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                        <YAxis 
                          domain={[0, 100]} 
                          tickFormatter={(value) => `${value}%`}
                          stroke="hsl(var(--muted-foreground))" 
                          fontSize={12} 
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: 'hsl(var(--card))',
                            border: '1px solid hsl(var(--border))',
                            borderRadius: '8px',
                          }}
                          labelStyle={{ color: 'hsl(var(--foreground))' }}
                          formatter={(value: any, name: any, props: any) => {
                            if (name === 'confidence') {
                              return [`${value}%`, `Confidence (${props.payload.type})`];
                            }
                            return [value, name];
                          }}
                        />
                        <Line 
                          type="monotone" 
                          dataKey="confidence" 
                          stroke="hsl(var(--primary))" 
                          strokeWidth={2}
                          activeDot={{ r: 6 }} 
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
                      <Target className="h-8 w-8 mb-2 opacity-50 text-muted-foreground" />
                      <p className="text-sm font-medium">No Historical Events Available</p>
                      <p className="text-xs mt-1 text-center">Accuracy trends will appear here once the AI records detection incidents.</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Detection by Type — real data */}
              <div className="dashboard-card p-6">
                <h3 className="text-lg font-semibold mb-4">Detection by Type</h3>
                <div className="h-64">
                  {detectionByTypeData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={detectionByTypeData} layout="vertical">
                        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                        <XAxis type="number" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                        <YAxis
                          type="category"
                          dataKey="type"
                          stroke="hsl(var(--muted-foreground))"
                          fontSize={12}
                          width={70}
                        />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: 'hsl(var(--card))',
                            border: '1px solid hsl(var(--border))',
                            borderRadius: '8px',
                          }}
                          labelStyle={{ color: 'hsl(var(--foreground))' }}
                        />
                        <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center h-full text-muted-foreground">
                      No detection data available
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Performance Metrics Table */}
            <div className="dashboard-card p-6">
              <h3 className="text-lg font-semibold mb-4">Performance Metrics</h3>
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Target</th>
                      <th>Current</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {performanceMetrics.map((metric) => (
                      <tr key={metric.metric}>
                        <td className="text-sm font-medium">{metric.metric}</td>
                        <td className="text-sm text-muted-foreground">{metric.target}</td>
                        <td className="text-sm font-medium">{metric.current}</td>
                        <td>
                          <span className={cn(
                            "text-sm font-medium capitalize",
                            metric.status === 'good' ? "text-status-online" :
                            metric.status === 'warning' ? "text-amber-500" :
                            "text-severity-critical"
                          )}>
                            {metric.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
