import { Header } from '@/components/layout/Header';
import { StatCard } from '@/components/dashboard/StatCard';
import { SystemUsageCard } from '@/components/dashboard/SystemUsageCard';
import { RecentIncidentsTable } from '@/components/dashboard/RecentIncidentsTable';
import { Camera, AlertTriangle, TrendingUp, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { API_ENDPOINTS } from '@/config/api';
import { apiService } from '@/services/api.service';
import type { SystemMetrics, Incident } from '@/types';

// Backend response types
interface EventsStatsResponse {
  total_events: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
}

// Backend /cameras returns an array of camera objects
interface CameraItem {
  id: string;
  name: string;
  source: string;
  fps: number;
  priority: string;
  enabled: boolean;
  status: string;
  pid: number | null;
}

interface StatusResponse {
  status: 'healthy' | 'degraded' | 'unhealthy' | string;
  timestamp: string;
  uptime_seconds: number;
  components: {
    ecs: { name: string; status: string; details: Record<string, unknown> };
    redis: { name: string; status: string; details: Record<string, unknown> };
    cameras: { name: string; status: string; details: Record<string, unknown> };
  };
  cpu_usage: number;
  cpu_cores: number;
  memory_used_gb: number;
  memory_total_gb: number;
  storage_used_mb: number;
  storage_total_mb: number;
}

interface BackendEvent {
  id: string;
  camera_id: string;
  event_type: string;
  severity: string;
  start_ts: number;
  end_ts: number;
  confidence: number;
  model_version: string;
  created_at: number;
}

interface EventsListResponse {
  total: number;
  limit: number;
  offset: number;
  events: BackendEvent[];
}

// Adapt backend event to frontend Incident type
function adaptEventToIncident(event: BackendEvent): Incident {
  return {
    id: event.id,
    time: new Date(event.start_ts * 1000).toLocaleTimeString(),
    camera: {
      id: event.camera_id,
      name: event.camera_id,
      location: 'Camera',
      status: 'online',
      aiActive: true,
    },
    type: event.event_type as Incident['type'],
    severity: event.severity as Incident['severity'],
    status: 'active',
    createdAt: new Date(event.start_ts * 1000).toISOString(),
    updatedAt: new Date(event.end_ts * 1000).toISOString(),
  };
}

export default function Dashboard() {
  const navigate = useNavigate();

  // Fetch event stats
  const { data: stats, isLoading: statsLoading, error: statsError, refetch: refetchStats } =
    useQuery({
      queryKey: ['dashboard-stats'],
      queryFn: () => apiService.getData<EventsStatsResponse>(API_ENDPOINTS.dashboard.stats),
      refetchInterval: 10000,
    });

  // Fetch camera status
  const { data: cameraList, isLoading: camerasLoading } =
    useQuery({
      queryKey: ['dashboard-cameras'],
      queryFn: () => apiService.getData<CameraItem[]>(API_ENDPOINTS.cameras.list),
      refetchInterval: 10000,
    });

  // Fetch system status
  const { data: systemStatus, isLoading: systemLoading } =
    useQuery({
      queryKey: ['dashboard-system'],
      queryFn: () => apiService.getData<StatusResponse>(API_ENDPOINTS.dashboard.systemMetrics),
      refetchInterval: 10000,
    });

  // Fetch recent events
  const { data: recentEvents, isLoading: eventsLoading } =
    useQuery({
      queryKey: ['dashboard-recent-events'],
      queryFn: () => apiService.getData<EventsListResponse>(API_ENDPOINTS.dashboard.recentEvents, { limit: '5' }),
      refetchInterval: 10000,
    });

  const handleViewIncident = (incident: Incident) => {
    navigate(`/incidents/${incident.id}`);
  };

  const isLoading = statsLoading || camerasLoading || systemLoading || eventsLoading;
  const runningCameras = cameraList?.filter((c) => c.status === 'running').length ?? 0;
  const totalCameras = cameraList?.length ?? 0;

  // Map system status to SystemMetrics shape for the existing component
  const metrics: SystemMetrics = {
    cpuUsage: systemStatus?.cpu_usage ?? 0,
    cpuCores: `${systemStatus?.cpu_cores ?? '-'} Cores`,
    memoryUsed: systemStatus?.memory_used_gb ?? 0,
    memoryTotal: systemStatus?.memory_total_gb ?? 0,
    storageUsed: systemStatus?.storage_used_mb ?? 0,
    storageTotal: systemStatus?.storage_total_mb ?? 0,
    incidentsStored: stats?.total_events ?? 0,
    isOperational: systemStatus?.status === 'healthy',
    lastUpdated: systemStatus
      ? `Uptime: ${Math.floor((systemStatus.uptime_seconds ?? 0) / 60)}m`
      : '-',
  };

  const incidents: Incident[] = recentEvents?.events?.map(adaptEventToIncident) ?? [];

  if (statsError) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="p-6 flex flex-col items-center justify-center gap-4 min-h-[60vh]">
          <p className="text-severity-critical text-lg">Failed to load dashboard data</p>
          <p className="text-muted-foreground text-sm">{(statsError as Error).message}</p>
          <Button variant="outline" className="gap-2" onClick={() => refetchStats()}>
            <RefreshCw className="h-4 w-4" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header />
      <div className="p-6">
        {/* Greeting */}
        <h1 className="text-3xl font-bold mb-6">VisionGuard AI Dashboard</h1>

        {isLoading ? (
          <div className="flex items-center justify-center min-h-[40vh]">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : (
          <>
            {/* Stats Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <StatCard
                title="Active Cameras"
                value={`${runningCameras}/${totalCameras}`}
                subtitle={runningCameras > 0 ? 'Online' : 'No cameras running'}
                icon={Camera}
              />
              <StatCard
                title="Total Events"
                value={stats?.total_events ?? 0}
                subtitle="All time"
                icon={AlertTriangle}
                iconBgColor="bg-severity-high/10"
              />
              <StatCard
                title="Critical Alerts"
                value={stats?.by_severity?.critical ?? 0}
                subtitle="Requires Attention"
                icon={AlertTriangle}
                iconBgColor="bg-severity-critical/10"
              />
              <StatCard
                title="Detection Types"
                value={Object.keys(stats?.by_type ?? {}).length}
                subtitle={
                  stats?.by_type
                    ? Object.entries(stats.by_type)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(', ')
                    : '-'
                }
                icon={TrendingUp}
              />
            </div>

            {/* System Usage */}
            <div className="mb-6">
              <SystemUsageCard metrics={metrics} />
            </div>

            {/* Recent Incidents */}
            <RecentIncidentsTable
              incidents={incidents}
              onViewIncident={handleViewIncident}
            />
          </>
        )}
      </div>
    </div>
  );
}
