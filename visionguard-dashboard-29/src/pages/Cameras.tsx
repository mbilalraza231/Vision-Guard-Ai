import { useState, useEffect } from 'react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus, Play, Square, Loader2, RefreshCw, Trash2, Pencil, MapPin } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { API_ENDPOINTS, API_CONFIG } from '@/config/api';
import { apiService } from '@/services/api.service';
import type { Camera, ZoneApiResponse } from '@/types';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

// Backend camera from GET /cameras
interface BackendCamera {
  id: string;
  name: string;
  source: string;
  fps: number;
  priority: string;
  enabled: boolean;
  motion_threshold: number;
  status: 'running' | 'stopped' | 'unknown' | 'online' | 'offline';
  pid: number | null;
  zone_id?: string | null;
}

// Map backend camera to frontend Camera type
function adaptCamera(cam: BackendCamera): Camera & { enabled: boolean; source: string; priority: string; motionThreshold: number; fps: number; zone_id?: string | null } {
  const isOnline = cam.status === 'running' || cam.status === 'online';
  
  // If it's a local video (source doesn't start with http/rtsp) and it's offline, 
  // treat it as disabled so the toggle snaps back to 'Start' automatically!
  const isLocal = cam.source && !cam.source.toLowerCase().match(/^(http|https|rtsp|rtmp):\/\//);
  const effectiveEnabled = (isLocal && !isOnline) ? false : cam.enabled;

  return {
    id: cam.id,
    name: cam.name,
    location: cam.source,
    status: isOnline ? 'online' : 'offline',
    aiActive: isOnline,
    streamUrl: cam.source,
    lastActivity: cam.pid ? `PID: ${cam.pid}` : undefined,
    enabled: effectiveEnabled,
    source: cam.source,
    priority: cam.priority,
    motionThreshold: cam.motion_threshold,
    fps: cam.fps,
    zone_id: cam.zone_id,
  };
}

export default function Cameras() {
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  // Add/Edit Camera Form States
  const [isOpen, setIsOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [cameraId, setCameraId] = useState('');
  const [name, setName] = useState('');
  const [source, setSource] = useState('');
  const [fps, setFps] = useState(5);
  const [priority, setPriority] = useState('all');
  const [motionThreshold, setMotionThreshold] = useState(0.02);
  const [enabled, setEnabled] = useState(false); // Default to false (stopped on add)
  const [zoneId, setZoneId] = useState<string>('');

  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ['cameras-list'],
    queryFn: () => apiService.getData<BackendCamera[]>(API_ENDPOINTS.cameras.list),
  });

  // Listen to SSE system stream for real-time camera status updates
  useEffect(() => {
    // Point directly at the FastAPI backend stream endpoint
    const streamUrl = `${API_CONFIG.baseUrl}/api/v1/system/stream`;
    const eventSource = new EventSource(streamUrl);
    
    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload?.metrics?.cameras) {
          // Invalidate the cameras list silently in the background when we get a heartbeat 
          // to ensure the UI stays perfectly in sync with the backend.
          // We use refetch() instead of invalidateQueries to avoid full loading spinners.
          refetch();
        }
      } catch (err) {
        console.error("SSE parse error", err);
      }
    };

    return () => {
      eventSource.close();
    };
  }, [refetch]);

  // Fetch zones for zone selection dropdown
  const { data: zonesData } = useQuery({
    queryKey: ['zones'],
    queryFn: () => apiService.getData<{ zones: ZoneApiResponse[] }>(API_ENDPOINTS.zones.list),
  });
  const zones = zonesData?.zones ?? [];

  const registerMutation = useMutation({
    mutationFn: (newCam: {
      camera_id: string;
      rtsp_url: string;
      name?: string;
      fps?: number;
      motion_threshold?: number;
      priority?: string;
      enabled?: boolean;
      zone_id?: string | null;
    }) => apiService.postData(API_ENDPOINTS.cameras.register, newCam),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras-list'] });
      setIsOpen(false);
      const isEditing = editingId !== null;
      toast.success(isEditing ? 'Camera config updated instantly via Pub/Sub.' : 'Camera registered successfully', {
        icon: isEditing ? '⚡' : undefined,
        duration: isEditing ? 5000 : 3000,
      });
      // Reset form
      setEditingId(null);
      setCameraId('');
      setName('');
      setSource('');
      setFps(5);
      setPriority('medium');
      setMotionThreshold(0.02);
      setEnabled(false);
      setZoneId('');
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to register camera');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiService.deleteData(API_ENDPOINTS.cameras.delete(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras-list'] });
      toast.success('Camera deleted successfully');
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to delete camera');
    },
  });

  const startMutation = useMutation({
    mutationFn: (id: string) => apiService.postData(API_ENDPOINTS.cameras.start(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras-list'] });
      toast.success('Camera stream started');
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to start stream');
    },
  });

  const stopMutation = useMutation({
    mutationFn: (id: string) => apiService.postData(API_ENDPOINTS.cameras.stop(id)),
    onSuccess: () => {
      // Force-kill ALL pending HTTP connections (including the persistent MJPEG stream).
      // This is the only reliable way to sever a chunked-transfer MJPEG connection
      // that the browser's TCP pool keeps alive even after the <img> is removed from DOM.
      window.stop();

      // Re-fetch camera list (the window.stop() killed the previous in-flight fetch too)
      queryClient.invalidateQueries({ queryKey: ['cameras-list'] });
      toast.success('Camera stream stopped');
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to stop stream');
    },
  });

  const cameras = data?.map(adaptCamera) ?? [];
  const onlineCount = cameras.filter((c) => c.status === 'online').length;

  if (error) {
    return (
      <div className="min-h-screen">
        <Header title={t('cameras.title')} showDateNav={false} />
        <div className="p-6 flex flex-col items-center justify-center gap-4 min-h-[60vh]">
          <p className="text-severity-critical text-lg">{t('common.error')}</p>
          <p className="text-muted-foreground text-sm">{(error as Error).message}</p>
          <Button variant="outline" className="gap-2" disabled={isLoading || isFetching} onClick={() => refetch()}>
            <RefreshCw className={cn("h-4 w-4", (isLoading || isFetching) && "animate-spin")} />
            {t('common.retry')}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Header title={t('cameras.title')} showDateNav={false} />
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
          
          <Dialog open={isOpen} onOpenChange={(open) => {
            setIsOpen(open);
            if (!open) {
              setEditingId(null);
            }
          }}>
            <Button
              className="gap-2"
              onClick={() => {
                setEditingId(null);
                setCameraId('');
                setName('');
                setSource('');
                setFps(5);
                setPriority('medium');
                setMotionThreshold(0.02);
                setEnabled(false); // Default false for new camera
                setZoneId('');
                setIsOpen(true);
              }}
            >
              <Plus className="h-4 w-4" />
              {t('cameras.add')}
            </Button>
            <DialogContent className="sm:max-w-[480px] max-h-[88vh] p-0 flex flex-col overflow-hidden top-[50%] translate-y-[-50%]">
              <DialogHeader className="p-6 pb-3 border-b">
                <DialogTitle>{editingId ? t('cameras.editCamera') : t('cameras.add')}</DialogTitle>
                <DialogDescription>
                  {editingId ? 'Modify configuration options for this camera source.' : 'Configure a new camera source for VisionGuard AI monitoring.'}
                </DialogDescription>
              </DialogHeader>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  registerMutation.mutate({
                    camera_id: cameraId,
                    rtsp_url: source,
                    name: name || undefined,
                    fps,
                    motion_threshold: motionThreshold,
                    priority,
                    enabled,
                    zone_id: zoneId || null,
                  });
                }}
                className="flex-1 flex flex-col min-h-0 overflow-hidden"
              >
                {/* Scrollable Form Fields */}
                <div className="flex-1 overflow-y-auto p-6 space-y-4 min-h-0">
                  <div className="space-y-2">
                    <Label htmlFor="id">Camera ID (Slug)</Label>
                    <Input
                      id="id"
                      placeholder="e.g. cam_front"
                      value={cameraId}
                      onChange={(e) => setCameraId(e.target.value)}
                      required
                      disabled={editingId !== null}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="name">Camera Name</Label>
                    <Input
                      id="name"
                      placeholder="e.g. Front Gate"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="source">Source (RTSP / HTTP / Path)</Label>
                    <Input
                      id="source"
                      placeholder="rtsp://192.168.x.x/stream  or  /app/camera_capture/video.mp4"
                      value={source}
                      onChange={(e) => setSource(e.target.value)}
                      required
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="fps">FPS (1 - 30)</Label>
                      <Input
                        id="fps"
                        type="number"
                        min={1}
                        max={30}
                        value={fps}
                        onChange={(e) => setFps(parseInt(e.target.value))}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="priority">Worker Selection</Label>
                      <select
                        id="priority"
                        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 text-foreground"
                        value={priority}
                        onChange={(e) => setPriority(e.target.value)}
                      >
                        <option value="all">All workers (Weapon, Fire, Fall)</option>
                        <option value="critical">Weapon only (Critical queue)</option>
                        <option value="high">Fire only (High queue)</option>
                        <option value="medium">Fall only (Medium queue)</option>
                      </select>
                      <p className="text-xs text-muted-foreground mt-1">
                        Controls which AI workers process frames. Zone priority controls event severity (separate from this).
                      </p>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="motion">Motion Threshold (0.01 - 1.0)</Label>
                    <Input
                      id="motion"
                      type="number"
                      step="0.01"
                      min="0.01"
                      max="1.0"
                      value={motionThreshold}
                      onChange={(e) => setMotionThreshold(parseFloat(e.target.value))}
                    />
                  </div>
                  
                  <div className="flex items-center space-x-2 pt-2">
                    <input
                      type="checkbox"
                      id="enabled"
                      checked={enabled}
                      onChange={(e) => setEnabled(e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                    />
                    <Label htmlFor="enabled">Enable camera stream</Label>
                  </div>

                  {/* Zone Selection */}
                  <div className="space-y-2">
                    <Label htmlFor="zone" className="flex items-center gap-1">
                      <MapPin className="h-3 w-3" /> Zone
                    </Label>
                    <select
                      id="zone"
                      className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      value={zoneId}
                      onChange={(e) => setZoneId(e.target.value)}
                    >
                      <option value="">— No Zone —</option>
                      {zones.map((z) => (
                        <option key={z.id} value={z.id}>{z.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                
                {/* Fixed Footer */}
                <div className="p-6 border-t bg-muted/30">
                  <Button
                    type="submit"
                    disabled={registerMutation.isPending}
                    className="w-full font-semibold"
                  >
                    {registerMutation.isPending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        {t('common.loading')}
                      </>
                    ) : (
                      editingId ? t('common.save') : t('cameras.add')
                    )}
                  </Button>
                </div>
              </form>
            </DialogContent>
          </Dialog>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center min-h-[40vh]">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : cameras.length === 0 ? (
          <div className="flex flex-col items-center justify-center min-h-[40vh] text-muted-foreground">
            <p className="text-lg">{t('cameras.noCameras')}</p>
            <p className="text-sm mt-1">{t('cameras.addFirst')}</p>
          </div>
        ) : (
          /* Camera Grid */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {cameras.map((camera) => (
              <CameraCard
                key={camera.id}
                camera={camera}
                startMutation={startMutation}
                stopMutation={stopMutation}
                deleteMutation={deleteMutation}
                onEdit={(cam) => {
                  setEditingId(cam.id);
                  setCameraId(cam.id);
                  setName(cam.name);
                  setSource(cam.source);
                  setFps(cam.fps);
                  setPriority(cam.priority);
                  setMotionThreshold(cam.motionThreshold);
                  setEnabled(cam.enabled);
                  setZoneId(cam.zone_id || '');
                  setIsOpen(true);
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

interface CameraCardProps {
  camera: Camera & { enabled: boolean; source: string; priority: string; motionThreshold: number; fps: number };
  startMutation: any;
  stopMutation: any;
  deleteMutation: any;
  onEdit: (camera: any) => void;
}

function CameraCard({ camera, startMutation, stopMutation, deleteMutation, onEdit }: CameraCardProps) {
  const { t } = useTranslation();
  const [isStarting, setIsStarting] = useState(false);
  const [startCountdown, setStartCountdown] = useState(0);

  // Detect if this is a local file (not http/rtsp)
  const isLocalFile = camera.source && !camera.source.toLowerCase().match(/^(http|https|rtsp|rtmp):\/\//);

  // When camera goes online, clear the initializing state
  useEffect(() => {
    if (camera.status === 'online' && isStarting) {
      if (isLocalFile) {
        // Force a 1-second delay for local files to ensure visual feedback
        const timer = setTimeout(() => {
          setIsStarting(false);
          setStartCountdown(0);
        }, 1000);
        return () => clearTimeout(timer);
      } else {
        setIsStarting(false);
        setStartCountdown(0);
      }
    }
  }, [camera.status, isStarting, isLocalFile]);

  const handleStart = () => {
    startMutation.mutate(camera.id);
    if (isLocalFile) {
      // Show "Initializing..." state with countdown for local files
      setIsStarting(true);
      setStartCountdown(12);
      const interval = setInterval(() => {
        setStartCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(interval);
            setIsStarting(false);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
  };

  return (
    <div className="dashboard-card p-5 flex flex-col justify-between h-full min-h-[390px]">
      <div>
        {/* Header: Name and Status */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex flex-col min-w-0 flex-1">
            <h3 className="font-semibold text-base text-foreground truncate" title={camera.name}>
              {camera.name}
            </h3>
            <span className="text-xs text-muted-foreground font-mono mt-0.5 truncate" title={camera.id}>
              {camera.id}
            </span>
          </div>
          
          <div className="flex items-center gap-1.5 ml-2 shrink-0">
            <Badge
              variant="secondary"
              className={cn(
                "capitalize text-[10px] px-2 py-0.5 font-semibold border",
                camera.priority === 'all' && "bg-green-500/10 text-green-500 border-green-500/20",
                camera.priority === 'critical' && "bg-red-500/10 text-red-500 border-red-500/20",
                camera.priority === 'high' && "bg-amber-500/10 text-amber-500 border-amber-500/20",
                camera.priority === 'medium' && "bg-blue-500/10 text-blue-500 border-blue-500/20",
                camera.priority === 'low' && "bg-slate-500/10 text-slate-500 border-slate-500/20"
              )}
            >
              {camera.priority === 'all' ? 'All Workers' : 
               camera.priority === 'critical' ? 'Weapon' :
               camera.priority === 'high' ? 'Fire' :
               camera.priority === 'medium' ? 'Fall' : camera.priority}
            </Badge>
          </div>
        </div>

        {/* Source / Location */}
        <p className="text-xs text-muted-foreground truncate mb-4 bg-muted/40 p-2 rounded border border-muted font-mono" title={camera.location}>
          {camera.location}
        </p>

        {/* Camera Preview Placeholder - Flex Centered (No actual stream rendered here) */}
        <div className="mb-4 h-40 border border-border bg-black/20 rounded-lg overflow-hidden relative flex items-center justify-center bg-black/40">
          <div className="text-center z-10 flex flex-col items-center justify-center">
            <div className="h-10 w-10 rounded-full bg-secondary/80 flex items-center justify-center mx-auto mb-2 border border-border">
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
            <p className="text-xs text-muted-foreground font-medium">Live Feed</p>
          </div>
        </div>

        {/* Status Badges */}
        <div className="flex flex-wrap items-center gap-1.5 mb-4">
          {isStarting ? (
            <Badge
              variant="outline"
              className="border-yellow-500/50 text-yellow-400 bg-yellow-500/10 text-[10px] font-semibold"
            >
              <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-yellow-400 animate-pulse" />
              Initializing... {startCountdown}s
            </Badge>
          ) : !camera.enabled ? (
            <Badge
              variant="outline"
              className="border-muted-foreground/30 text-muted-foreground text-[10px]"
            >
              Disabled
            </Badge>
          ) : (camera.status === 'online') ? (
            <Badge
              variant="outline"
              className="border-status-online/50 text-status-online bg-status-online/5 text-[10px] font-semibold"
            >
              <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-status-online pulse-live" />
              {t('cameras.online')}
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="border-amber-500/50 text-amber-500 bg-amber-500/5 text-[10px] font-semibold"
            >
              <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
              Connecting...
            </Badge>
          )}
          {camera.aiActive && (
            <Badge variant="outline" className="border-primary/50 text-primary bg-primary/5 text-[10px] font-semibold">
              {t('monitoring.aiActive')}
            </Badge>
          )}
        </div>
      </div>

      {/* Bottom Row Actions - Separated cleanly to prevent overlap */}
      <div className="flex items-center justify-between border-t border-border pt-4 mt-auto">
        <div className="flex items-center gap-2">
          {camera.enabled ? (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs h-8 text-severity-critical border-severity-critical/30 hover:bg-severity-critical/10"
              onClick={() => stopMutation.mutate(camera.id)}
              disabled={stopMutation.isPending}
            >
              {stopMutation.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Square className="h-3 w-3 fill-current" />
              )}
              {t('cameras.stop')}
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs h-8 text-status-online border-status-online/30 hover:bg-status-online/10"
              onClick={handleStart}
              disabled={startMutation.isPending || isStarting}
            >
              {(startMutation.isPending || isStarting) ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Play className="h-3 w-3 fill-current" />
              )}
              {isStarting ? `Starting...` : t('cameras.start')}
            </Button>
          )}
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-primary hover:bg-primary/10 rounded-md transition-colors"
            title="Edit Camera Settings"
            onClick={() => onEdit(camera)}
          >
            <Pencil className="h-4 w-4" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10 rounded-md transition-colors"
            title="Delete Camera"
            onClick={() => {
              if (confirm(`Are you sure you want to delete camera "${camera.name}"?`)) {
                deleteMutation.mutate(camera.id);
              }
            }}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}
