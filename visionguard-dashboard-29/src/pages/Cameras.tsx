import { useState } from 'react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Plus, Play, Square, Loader2, RefreshCw, Trash2, Pencil } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { API_ENDPOINTS } from '@/config/api';
import { apiService } from '@/services/api.service';
import type { Camera } from '@/types';
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
}

// Map backend camera to frontend Camera type
function adaptCamera(cam: BackendCamera): Camera & { enabled: boolean; source: string; priority: string; motionThreshold: number; fps: number } {
  const isOnline = cam.enabled && (cam.status === 'running' || cam.status === 'online');
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
    priority: cam.priority,
    motionThreshold: cam.motion_threshold,
    fps: cam.fps,
  };
}

export default function Cameras() {
  const queryClient = useQueryClient();

  // Add/Edit Camera Form States
  const [isOpen, setIsOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [cameraId, setCameraId] = useState('');
  const [name, setName] = useState('');
  const [source, setSource] = useState('');
  const [fps, setFps] = useState(5);
  const [priority, setPriority] = useState('medium');
  const [motionThreshold, setMotionThreshold] = useState(0.02);
  const [enabled, setEnabled] = useState(false); // Default to false (stopped on add)

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['cameras'],
    queryFn: () => apiService.getData<BackendCamera[]>(API_ENDPOINTS.cameras.list),
  });

  const registerMutation = useMutation({
    mutationFn: (newCam: {
      camera_id: string;
      rtsp_url: string;
      name?: string;
      fps?: number;
      motion_threshold?: number;
      priority?: string;
      enabled?: boolean;
    }) => apiService.postData(API_ENDPOINTS.cameras.register, newCam),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] });
      setIsOpen(false);
      const isEditing = editingId !== null;
      toast.success(isEditing ? 'Camera settings updated' : 'Camera registered successfully');
      if (isEditing) {
        toast.info('Restart the camera service to apply configuration updates.', {
          duration: 5000,
        });
      }
      // Reset form
      setEditingId(null);
      setCameraId('');
      setName('');
      setSource('');
      setFps(5);
      setPriority('medium');
      setMotionThreshold(0.02);
      setEnabled(false);
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to register camera');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiService.deleteData(API_ENDPOINTS.cameras.delete(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] });
      toast.success('Camera deleted successfully');
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to delete camera');
    },
  });

  const startMutation = useMutation({
    mutationFn: (id: string) => apiService.postData(API_ENDPOINTS.cameras.start(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] });
      toast.success('Camera stream started');
    },
    onError: (err: any) => {
      toast.error(err.message || 'Failed to start stream');
    },
  });

  const stopMutation = useMutation({
    mutationFn: (id: string) => apiService.postData(API_ENDPOINTS.cameras.stop(id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cameras'] });
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
                setIsOpen(true);
              }}
            >
              <Plus className="h-4 w-4" />
              Add Camera
            </Button>
            <DialogContent className="sm:max-w-[425px] max-h-[85vh] p-0 flex flex-col overflow-hidden">
              <DialogHeader className="p-6 pb-3 border-b">
                <DialogTitle>{editingId ? 'Edit Camera Settings' : 'Add New Camera'}</DialogTitle>
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
                      placeholder="rtsp://... or /app/video.mp4"
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
                      <Label htmlFor="priority">Priority</Label>
                      <select
                        id="priority"
                        className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 text-foreground"
                        value={priority}
                        onChange={(e) => setPriority(e.target.value)}
                      >
                        <option value="critical">Critical</option>
                        <option value="high">High</option>
                        <option value="medium">Medium</option>
                        <option value="low">Low</option>
                      </select>
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
                        Saving...
                      </>
                    ) : (
                      editingId ? 'Save Changes' : 'Save Camera'
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
            <p className="text-lg">No cameras configured</p>
            <p className="text-sm mt-1">Click "Add Camera" above to get started</p>
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
  const [imageError, setImageError] = useState(false);
  const isHttpStream = camera.status === 'online' && camera.source.startsWith('http');

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
                camera.priority === 'critical' && "bg-red-500/10 text-red-500 border-red-500/20",
                camera.priority === 'high' && "bg-amber-500/10 text-amber-500 border-amber-500/20",
                camera.priority === 'medium' && "bg-blue-500/10 text-blue-500 border-blue-500/20",
                camera.priority === 'low' && "bg-slate-500/10 text-slate-500 border-slate-500/20"
              )}
            >
              {camera.priority}
            </Badge>
          </div>
        </div>

        {/* Source / Location */}
        <p className="text-xs text-muted-foreground truncate mb-4 bg-muted/40 p-2 rounded border border-muted font-mono" title={camera.location}>
          {camera.location}
        </p>

        {/* Camera Preview / Video Feed - Flex Centered */}
        <div className="mb-4 h-40 border border-border bg-black/20 rounded-lg overflow-hidden relative flex items-center justify-center bg-black/40">
          <img
            src={isHttpStream && !imageError ? camera.source : "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs="}
            alt={`${camera.name} feed`}
            className={cn(
              "w-full h-full object-contain absolute inset-0 z-0",
              (!isHttpStream || imageError) && "hidden"
            )}
            onError={() => setImageError(true)}
          />
          
          {(!isHttpStream || imageError) && (
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
          )}
        </div>

        {/* Status Badges */}
        <div className="flex flex-wrap items-center gap-1.5 mb-4">
          {!camera.enabled ? (
            <Badge
              variant="outline"
              className="border-muted-foreground/30 text-muted-foreground text-[10px]"
            >
              Disabled
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className={cn(
                'text-[10px] font-semibold',
                camera.status === 'online'
                  ? 'border-status-online/50 text-status-online bg-status-online/5'
                  : 'border-status-offline/50 text-status-offline bg-status-offline/5'
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
            <Badge variant="outline" className="border-primary/50 text-primary bg-primary/5 text-[10px] font-semibold">
              AI Active
            </Badge>
          )}
        </div>
      </div>

      {/* Bottom Row Actions - Separated cleanly to prevent overlap */}
      <div className="flex items-center justify-between border-t border-border pt-4 mt-auto">
        <div className="flex items-center gap-2">
          {camera.enabled && camera.status === 'online' ? (
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
              Stop Stream
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5 text-xs h-8 text-status-online border-status-online/30 hover:bg-status-online/10"
              onClick={() => startMutation.mutate(camera.id)}
              disabled={startMutation.isPending}
            >
              {startMutation.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Play className="h-3 w-3 fill-current" />
              )}
              Start Stream
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
