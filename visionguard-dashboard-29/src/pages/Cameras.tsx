import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus, Play, Square, Loader2, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { API_ENDPOINTS } from '@/config/api';
import { apiService } from '@/services/api.service';
import type { Camera } from '@/types';

// Backend camera from GET /cameras
interface BackendCamera {
  id: string;
  name: string;
  source: string;
  fps: number;
  priority: string;
  enabled: boolean;
  status: 'running' | 'stopped' | 'unknown';
  pid: number | null;
}

// Map backend camera to frontend Camera type
function adaptCamera(cam: BackendCamera): Camera & { enabled: boolean; source: string } {
  // Only cameras with an explicit running runtime state are counted as online.
  // Unknown means configured but not confirmed running.
  const isOnline = cam.enabled && cam.status === 'running';
  return {
    id: cam.id,
    name: cam.name,
    location: cam.source,
    status: isOnline ? 'online' : 'offline',
    aiActive: isOnline,
    streamUrl: cam.source,
    lastActivity: cam.pid ? `PID: ${cam.pid}` : undefined,
    enabled: cam.enabled,
    source: cam.source,
  };
}

export default function Cameras() {
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => apiService.getData<BackendCamera[]>(API_ENDPOINTS.cameras.list),
    refetchInterval: 10000,
  });

  const startMutation = useMutation({
    mutationFn: (id: string) => apiService.postData(API_ENDPOINTS.cameras.start(id)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['cameras'] }),
  });

  const stopMutation = useMutation({
    mutationFn: (id: string) => apiService.postData(API_ENDPOINTS.cameras.stop(id)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['cameras'] }),
  });

  const cameras = data?.map(adaptCamera) ?? [];
  const onlineCount = cameras.filter((c) => c.status === 'online').length;

  if (error) {
    return (
      <div className="min-h-screen">
        <Header title="Cameras" showDateNav={false} />
        <div className="p-6 flex flex-col items-center justify-center gap-4 min-h-[60vh]">
          <p className="text-severity-critical text-lg">Failed to load cameras</p>
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
      <Header title="Cameras" showDateNav={false} />
      <div className="p-6">
        {/* Header Actions */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-muted-foreground">
              {isLoading
                ? 'Loading...'
                : `${onlineCount} of ${cameras.length} cameras running`}
            </p>
          </div>
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            Add Camera
          </Button>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center min-h-[40vh]">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : cameras.length === 0 ? (
          <div className="flex flex-col items-center justify-center min-h-[40vh] text-muted-foreground">
            <p className="text-lg">No cameras configured</p>
            <p className="text-sm mt-1">Add cameras to cameras.json to get started</p>
          </div>
        ) : (
          /* Camera Grid */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {cameras.map((camera) => (
              <div key={camera.id} className="dashboard-card p-5">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="font-semibold text-lg">{camera.name}</h3>
                    <p className="text-sm text-muted-foreground truncate max-w-[220px]" title={camera.location}>
                      {camera.location}
                    </p>
                  </div>
                  {/* Start/Stop buttons — only for enabled cameras */}
                  {camera.enabled ? (
                    camera.status === 'online' ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1 text-severity-critical border-severity-critical/30"
                        onClick={() => stopMutation.mutate(camera.id)}
                        disabled={stopMutation.isPending}
                      >
                        {stopMutation.isPending ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Square className="h-3 w-3" />
                        )}
                        Stop
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1 text-status-online border-status-online/30"
                        onClick={() => startMutation.mutate(camera.id)}
                        disabled={startMutation.isPending}
                      >
                        {startMutation.isPending ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Play className="h-3 w-3" />
                        )}
                        Start
                      </Button>
                    )
                  ) : null}
                </div>

                {/* Camera Preview */}
                <div className="camera-feed mb-4 h-40">
                  {camera.status === 'online' && camera.source.startsWith('http') ? (
                    <img
                      src={camera.source}
                      alt={`${camera.name} feed`}
                      className="w-full h-full object-contain rounded-lg"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = 'none';
                        (e.target as HTMLImageElement).nextElementSibling?.classList.remove('hidden');
                      }}
                    />
                  ) : null}
                  <div className={cn(
                    'absolute inset-0 flex items-center justify-center',
                    camera.status === 'online' && camera.source.startsWith('http') && 'hidden'
                  )}>
                    <div className="text-center">
                      <div className="h-10 w-10 rounded-full bg-secondary/50 flex items-center justify-center mx-auto mb-2">
                        <svg
                          className="h-5 w-5 text-muted-foreground"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={1.5}
                            d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                          />
                        </svg>
                      </div>
                      <p className="text-xs text-muted-foreground">Preview</p>
                    </div>
                  </div>
                </div>

                {/* Status Badges */}
                <div className="flex items-center gap-2 mb-3">
                  {!camera.enabled ? (
                    <Badge
                      variant="outline"
                      className="border-muted-foreground/30 text-muted-foreground"
                    >
                      Disabled
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className={cn(
                        camera.status === 'online'
                          ? 'border-status-online/50 text-status-online'
                          : 'border-status-offline/50 text-status-offline'
                      )}
                    >
                      <span
                        className={cn(
                          'mr-1.5 h-1.5 w-1.5 rounded-full',
                          camera.status === 'online'
                            ? 'bg-status-online pulse-live'
                            : 'bg-status-offline'
                        )}
                      />
                      {camera.status === 'online' ? 'Online' : 'Offline'}
                    </Badge>
                  )}
                  {camera.aiActive && (
                    <Badge variant="outline" className="border-primary/50 text-primary">
                      AI Active
                    </Badge>
                  )}
                </div>

                {/* Last Activity */}
                {camera.lastActivity && (
                  <p className="text-xs text-muted-foreground">{camera.lastActivity}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
