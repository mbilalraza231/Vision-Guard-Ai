import { Header } from '@/components/layout/Header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useQuery } from '@tanstack/react-query';
import { buildApiUrl, API_ENDPOINTS, API_CONFIG } from '@/config/api';
import { apiService } from '@/services/api.service';
import { RefreshCw, Camera, Loader2, Shield, Flame, PersonStanding, Maximize2, Minimize2 } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';

// ────── Types ──────

interface CameraItem {
  id: string;
  name: string;
  source: string;
  fps: number;
  priority: string;
  enabled: boolean;
  status: string;
}

interface BBox {
  model: string;
  confidence: number;
  camera_id: string;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2] in 640x640 coords
  age_seconds: number;
}

interface BoxesResponse {
  boxes: BBox[];
  count: number;
}

// ────── Model Styling ──────

const MODEL_STYLES: Record<string, { label: string; color: string; border: string; bg: string }> = {
  weapon: { label: 'WEAPON', color: '#ef4444', border: 'rgba(239,68,68,0.8)', bg: 'rgba(239,68,68,0.15)' },
  fire: { label: 'FIRE', color: '#f97316', border: 'rgba(249,115,22,0.8)', bg: 'rgba(249,115,22,0.15)' },
  fall: { label: 'FALL', color: '#3b82f6', border: 'rgba(59,130,246,0.8)', bg: 'rgba(59,130,246,0.15)' },
};

// ────── BoundingBoxOverlay Component ──────

function BoundingBoxOverlay({ cameraId }: { cameraId: string }) {
  // Poll for live bounding boxes every 1.5 seconds
  const { data } = useQuery({
    queryKey: ['live-boxes', cameraId],
    queryFn: async () => {
      const url = `${buildApiUrl('/detections/boxes')}?camera_id=${encodeURIComponent(cameraId)}&limit=10`;
      return apiService.getData<BoxesResponse>(`/detections/boxes`, { camera_id: cameraId, limit: '10' })
        .catch(() => ({ boxes: [], count: 0 }));
    },
    refetchInterval: 1500,
  });

  const boxes = data?.boxes ?? [];

  return (
    <>
      {boxes.map((box, idx) => {
        const [x1, y1, x2, y2] = box.bbox;
        const style = MODEL_STYLES[box.model] ?? MODEL_STYLES.weapon;

        // Convert from 640x640 coords to percentage
        const left = (x1 / 640) * 100;
        const top = (y1 / 640) * 100;
        const width = ((x2 - x1) / 640) * 100;
        const height = ((y2 - y1) / 640) * 100;

        // Fade effect based on age
        const opacity = Math.max(0.3, 1 - box.age_seconds / 5);

        return (
          <div key={`${box.model}-${idx}`}>
            {/* Bounding box */}
            <div
              style={{
                position: 'absolute',
                left: `${left}%`,
                top: `${top}%`,
                width: `${width}%`,
                height: `${height}%`,
                border: `2px solid ${style.border}`,
                backgroundColor: style.bg,
                opacity,
                transition: 'opacity 0.5s ease',
                pointerEvents: 'none',
                zIndex: 10,
                borderRadius: '2px',
              }}
            />
            {/* Label */}
            <div
              style={{
                position: 'absolute',
                left: `${left}%`,
                top: `${Math.max(0, top - 4)}%`,
                backgroundColor: style.color,
                color: 'white',
                fontSize: '11px',
                fontWeight: 700,
                padding: '1px 6px',
                borderRadius: '2px',
                opacity,
                transition: 'opacity 0.5s ease',
                pointerEvents: 'none',
                zIndex: 11,
                whiteSpace: 'nowrap',
              }}
            >
              {style.label} {(box.confidence * 100).toFixed(0)}%
            </div>
          </div>
        );
      })}
    </>
  );
}

// ────── CameraFeed Component ──────

function CameraFeed({
  camera,
  onLoadStateChange,
}: {
  camera: CameraItem;
  onLoadStateChange: (isLive: boolean) => void;
}) {
  const [hasError, setHasError] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);

  // Reset error when camera changes
  useEffect(() => {
    setHasError(false);
    onLoadStateChange(false);
  }, [camera.source]);

  return (
    <div
      className={cn(
        'dashboard-card overflow-hidden border border-border/50 transition-all duration-300',
        isExpanded && 'col-span-full'
      )}
    >
      {/* Video feed container */}
      <div className="relative bg-black" style={{ aspectRatio: isExpanded ? '21/9' : '16/9' }}>
        {!hasError ? (
          <>
            {/* Live MJPEG stream from camera */}
            <img
              ref={imgRef}
              src={camera.source}
              alt={`Live feed: ${camera.name}`}
              className="w-full h-full object-contain"
              onLoad={() => {
                setHasError(false);
                onLoadStateChange(true);
              }}
              onError={() => {
                setHasError(true);
                onLoadStateChange(false);
              }}
            />

            {/* Bounding box overlay — positioned over the video */}
            <div className="absolute inset-0" style={{ pointerEvents: 'none' }}>
              <BoundingBoxOverlay cameraId={camera.id} />
            </div>
          </>
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <div className="h-16 w-16 rounded-full bg-secondary/50 flex items-center justify-center mx-auto mb-3">
                <Camera className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground">Camera feed unavailable</p>
              <p className="text-xs text-muted-foreground mt-1">{camera.source}</p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                onClick={() => {
                  setHasError(false);
                  onLoadStateChange(false);
                }}
              >
                <RefreshCw className="h-3 w-3 mr-1" /> Retry
              </Button>
            </div>
          </div>
        )}

        {/* Top overlay: status + AI badge */}
        <div className="absolute top-3 left-3 right-3 flex items-start justify-between" style={{ zIndex: 20 }}>
          <Badge
            variant="outline"
            className="backdrop-blur-md border-green-500/50 bg-green-500/10 text-green-400"
          >
            <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-green-400 pulse-live inline-block" />
            Live
          </Badge>
          <div className="flex gap-1.5">
            <Badge variant="outline" className="backdrop-blur-md border-primary/50 bg-primary/10 text-primary">
              AI Active
            </Badge>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 backdrop-blur-md bg-background/30 hover:bg-background/50"
              onClick={() => setIsExpanded(!isExpanded)}
              style={{ zIndex: 21 }}
            >
              {isExpanded ? <Minimize2 className="h-3 w-3" /> : <Maximize2 className="h-3 w-3" />}
            </Button>
          </div>
        </div>

        {/* Bottom overlay: camera info */}
        <div className="absolute bottom-3 left-3 right-3" style={{ zIndex: 20 }}>
          <div className="rounded-lg bg-background/80 backdrop-blur-md px-3 py-2">
            <p className="font-medium text-sm">{camera.name}</p>
            <p className="text-xs text-muted-foreground">{camera.id} • {camera.fps} FPS • {camera.priority}</p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ────── Main Page ──────

export default function LiveMonitoring() {
  const [liveFeedState, setLiveFeedState] = useState<Record<string, boolean>>({});

  // Fetch real camera list from backend
  const { data: cameras, isLoading, error, refetch } = useQuery({
    queryKey: ['cameras-list'],
    queryFn: async () => {
      return apiService.getData<CameraItem[]>(API_ENDPOINTS.cameras.list);
    },
    refetchInterval: 30000, // Refresh camera list every 30s
  });

  const enabledCameras = cameras?.filter(c => c.enabled) ?? [];
  const liveCameras = enabledCameras.filter((camera) => liveFeedState[camera.id]);

  useEffect(() => {
    setLiveFeedState((current) => {
      const next: Record<string, boolean> = {};
      for (const camera of enabledCameras) {
        next[camera.id] = current[camera.id] ?? false;
      }
      return next;
    });
  }, [enabledCameras]);

  return (
    <div className="min-h-screen">
      <Header title="Live Monitoring" />
      <div className="p-6">
        {/* Title + controls */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold">Live Camera Feed</h2>
            <Badge variant="outline" className="border-green-500/50 bg-green-500/10 text-green-400">
              <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-green-400 pulse-live inline-block" />
              {liveCameras.length} Camera{liveCameras.length !== 1 ? 's' : ''} Live
            </Badge>
          </div>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => refetch()}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center min-h-[40vh]">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="rounded-lg bg-destructive/10 border border-destructive/30 p-6 text-center">
            <p className="text-destructive font-medium">Failed to load cameras</p>
            <p className="text-sm text-muted-foreground mt-1">{(error as Error).message}</p>
            <Button variant="outline" size="sm" className="mt-3" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4 mr-1.5" /> Retry
            </Button>
          </div>
        )}

        {/* Camera grid */}
        {!isLoading && !error && enabledCameras.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {enabledCameras.map(camera => (
              <CameraFeed
                key={camera.id}
                camera={camera}
                onLoadStateChange={(isLive) =>
                  setLiveFeedState((current) => ({ ...current, [camera.id]: isLive }))
                }
              />
            ))}
          </div>
        )}

        {/* No cameras */}
        {!isLoading && !error && enabledCameras.length === 0 && (
          <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4">
            <div className="h-20 w-20 rounded-full bg-secondary/50 flex items-center justify-center">
              <Camera className="h-10 w-10 text-muted-foreground" />
            </div>
            <div className="text-center">
              <p className="text-lg font-medium">No cameras enabled</p>
              <p className="text-sm text-muted-foreground mt-1">
                Enable cameras in cameras.json and restart the camera service.
              </p>
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="mt-6 rounded-lg bg-secondary/30 border border-border p-4">
          <div className="flex items-center justify-center gap-6 text-sm">
            <span className="flex items-center gap-1.5">
              <Shield className="h-4 w-4 text-red-400" /> Weapon
            </span>
            <span className="flex items-center gap-1.5">
              <Flame className="h-4 w-4 text-orange-400" /> Fire
            </span>
            <span className="flex items-center gap-1.5">
              <PersonStanding className="h-4 w-4 text-blue-400" /> Fall
            </span>
            <span className="text-muted-foreground">|</span>
            <span className="text-muted-foreground">
              Bounding boxes appear when AI detects objects in real-time
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
