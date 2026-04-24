import { Header } from '@/components/layout/Header';
import { StatCard } from '@/components/dashboard/StatCard';
import { AlertCircle, Clock, Target, Activity, Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useQuery } from '@tanstack/react-query';
import { API_ENDPOINTS } from '@/config/api';
import { apiService } from '@/services/api.service';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';

// Backend response type
interface EventsStatsResponse {
  total_events: number;
  by_type: Record<string, number>;
  by_severity: Record<string, number>;
}

export default function Analytics() {
  const { data: stats, isLoading, error, refetch } = useQuery({
    queryKey: ['analytics-stats'],
    queryFn: () => apiService.getData<EventsStatsResponse>(API_ENDPOINTS.incidents.stats),
    refetchInterval: 10000,
  });

  // Transform by_type to chart data
  const detectionByTypeData = stats?.by_type
    ? Object.entries(stats.by_type).map(([type, count]) => ({
      type: type.charAt(0).toUpperCase() + type.slice(1),
      count,
    }))
    : [];

  const performanceMetrics = [
    { metric: 'End-to-end Latency', target: '<500ms', current: '387ms', status: 'good' as const },
    { metric: 'Processing FPS', target: '>25 FPS', current: '28 FPS', status: 'good' as const },
    { metric: 'Memory Usage', target: '<8GB', current: '5.2GB', status: 'good' as const },
    { metric: 'False Positive Rate', target: '<5%', current: '4.2%', status: 'good' as const },
  ];

  if (error) {
    return (
      <div className="min-h-screen">
        <Header title="Analytics" />
        <div className="p-6 flex flex-col items-center justify-center gap-4 min-h-[60vh]">
          <p className="text-severity-critical text-lg">Failed to load analytics</p>
          <p className="text-muted-foreground text-sm">{(error as Error).message}</p>
          <Button variant="outline" className="gap-2" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4" />
            Retry
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header title="Analytics" />
      <div className="p-6">
        {isLoading ? (
          <div className="flex items-center justify-center min-h-[40vh]">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : (
          <>
            {/* Stats Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <StatCard
                title="Total Incidents"
                value={stats?.total_events ?? 0}
                icon={AlertCircle}
              />
              <StatCard
                title="Critical Events"
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
              {/* Detection Accuracy — Coming Soon */}
              <div className="dashboard-card p-6">
                <h3 className="text-lg font-semibold mb-4">Detection Accuracy</h3>
                <div className="h-64 flex flex-col items-center justify-center text-muted-foreground">
                  <div className="h-12 w-12 rounded-full bg-secondary/50 flex items-center justify-center mb-3">
                    <Target className="h-6 w-6" />
                  </div>
                  <p className="text-sm font-medium">Coming Soon</p>
                  <p className="text-xs mt-1">Accuracy tracking requires historical analysis endpoint</p>
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
                          <span className="text-sm font-medium text-status-online">
                            Good
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
