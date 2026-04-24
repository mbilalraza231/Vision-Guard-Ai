import { useState } from 'react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { SeverityBadge, StatusBadge } from '@/components/common/StatusBadge';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Download,
  Loader2,
  RefreshCw,
  Paperclip,
  X,
  Camera,
  Video,
  AlertTriangle,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { API_ENDPOINTS } from '@/config/api';
import { apiService } from '@/services/api.service';
import type { Incident, IncidentFilters, Severity, IncidentStatus } from '@/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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

interface EvidenceRow {
  id: string;
  event_id: string;
  evidence_type: 'snapshot' | 'clip';
  storage_provider: string;
  public_url: string;
  created_at: number;
}

interface EvidenceResponse {
  event_id: string;
  evidence: EvidenceRow[];
  snapshot_url: string | null;
  clip_url: string | null;
  clip_status?: 'pending' | 'ready' | 'failed';
  clip_error?: string | null;
  error?: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function adaptEventToIncident(event: BackendEvent): Incident & { confidence: number } {
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
    confidence: event.confidence,
  };
}

// ---------------------------------------------------------------------------
// EvidenceModal
// ---------------------------------------------------------------------------

interface EvidenceModalProps {
  incident: (Incident & { confidence: number }) | null;
  onClose: () => void;
}

function EvidenceModal({ incident, onClose }: EvidenceModalProps) {
  const open = incident !== null;

  const { data, isLoading } = useQuery<EvidenceResponse>({
    queryKey: ['evidence', incident?.id],
    queryFn: () =>
      apiService.getData<EvidenceResponse>(API_ENDPOINTS.incidents.evidence(incident!.id)),
    enabled: open,
    staleTime: 30_000,
    refetchInterval: 30_000,
  });

  // Check if event is recent (< 2 minutes)
  const isRecent = incident
    ? Date.now() - new Date(incident.createdAt).getTime() < 2 * 60 * 1000
    : false;

  // Severity colour helper
  const severityColor: Record<string, string> = {
    critical: '#ef4444',
    high: '#f97316',
    medium: '#eab308',
    low: '#22c55e',
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent
        className="max-w-2xl border border-white/10 bg-[#0f1117] text-white shadow-2xl"
        style={{ borderRadius: '1rem' }}
      >
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute right-4 top-4 rounded-full p-1 text-white/50 hover:text-white transition-colors"
          aria-label="Close"
        >
          <X className="h-5 w-5" />
        </button>

        <DialogHeader>
          <DialogTitle className="flex items-center gap-3 text-lg font-semibold">
            <Paperclip className="h-5 w-5 text-primary" />
            Event Evidence
          </DialogTitle>
        </DialogHeader>

        {incident && (
          <>
            {/* Event meta */}
            <div className="grid grid-cols-2 gap-3 rounded-lg bg-white/5 p-4 text-sm mt-2">
              <div>
                <span className="text-white/50">Type</span>
                <div className="mt-1 font-semibold capitalize">{incident.type}</div>
              </div>
              <div>
                <span className="text-white/50">Severity</span>
                <div
                  className="mt-1 font-semibold capitalize"
                  style={{ color: severityColor[incident.severity] ?? '#fff' }}
                >
                  {incident.severity}
                </div>
              </div>
              <div>
                <span className="text-white/50">Camera</span>
                <div className="mt-1 font-mono text-xs">{incident.camera.name}</div>
              </div>
              <div>
                <span className="text-white/50">Confidence</span>
                <div className="mt-1 font-mono">{(incident.confidence * 100).toFixed(1)}%</div>
              </div>
              <div className="col-span-2">
                <span className="text-white/50">Time</span>
                <div className="mt-1 font-mono text-xs">
                  {new Date(incident.createdAt).toLocaleString()}
                </div>
              </div>
            </div>

            {/* Loading spinner */}
            {isLoading && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
                <span className="ml-3 text-white/50">Loading evidence…</span>
              </div>
            )}

            {/* Evidence content */}
            {!isLoading && data && (
              <div className="space-y-5 mt-2">
                {/* Snapshot */}
                <div>
                  <div className="flex items-center gap-2 mb-2 text-sm font-medium text-white/70">
                    <Camera className="h-4 w-4" />
                    Snapshot
                  </div>
                  {data.snapshot_url ? (
                    <img
                      src={data.snapshot_url}
                      alt="Detection snapshot"
                      className="w-full rounded-lg border border-white/10"
                      style={{ maxHeight: '300px', objectFit: 'contain', background: '#000' }}
                    />
                  ) : (
                    <div className="flex items-center justify-center rounded-lg border border-dashed border-white/20 bg-white/5 py-8 text-sm text-white/40">
                      <AlertTriangle className="mr-2 h-4 w-4" />
                      No snapshot available
                    </div>
                  )}
                </div>

                {/* Clip */}
                <div>
                  <div className="flex items-center gap-2 mb-2 text-sm font-medium text-white/70">
                    <Video className="h-4 w-4" />
                    Video Clip
                  </div>
                  {data.clip_url ? (
                    <video
                      controls
                      src={data.clip_url}
                      className="w-full rounded-lg border border-white/10 bg-black"
                      style={{ maxWidth: '100%' }}
                    >
                      Your browser does not support video playback.
                    </video>
                  ) : (
                    <div className="flex items-center justify-center rounded-lg border border-dashed border-white/20 bg-white/5 py-8 text-sm text-white/40">
                      <Loader2
                        className={`mr-2 h-4 w-4 ${data.clip_status === 'pending' || isRecent ? 'animate-spin' : ''}`}
                      />
                      {data.clip_status === 'failed'
                        ? `Clip generation failed${data.clip_error ? ` (${data.clip_error})` : ''}`
                        : data.clip_status === 'pending' || isRecent
                          ? 'Processing clip…'
                          : 'Clip not available'}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Error state */}
            {!isLoading && data?.error && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-400 mt-2">
                {data.error}
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function Incidents() {
  const [filters, setFilters] = useState<IncidentFilters>({
    severity: 'all',
    type: 'all',
    status: 'all',
    camera: 'all',
  });
  const [selectedIncidents, setSelectedIncidents] = useState<string[]>([]);
  const [activeIncident, setActiveIncident] = useState<(Incident & { confidence: number }) | null>(null);

  // Build query params from filters
  const queryParams: Record<string, string> = { limit: '50' };
  if (filters.severity && filters.severity !== 'all') {
    queryParams.severity = filters.severity;
  }
  if (filters.type && filters.type !== 'all') {
    queryParams.event_type = filters.type;
  }
  if (filters.camera && filters.camera !== 'all') {
    queryParams.camera_id = filters.camera;
  }

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['incidents', filters],
    queryFn: () => apiService.getData<EventsListResponse>(API_ENDPOINTS.incidents.list, queryParams),
    refetchInterval: 10000,
  });

  const incidents = data?.events?.map(adaptEventToIncident) ?? [];

  const toggleSelectAll = () => {
    if (selectedIncidents.length === incidents.length) {
      setSelectedIncidents([]);
    } else {
      setSelectedIncidents(incidents.map((i) => i.id));
    }
  };

  const toggleSelect = (id: string) => {
    if (selectedIncidents.includes(id)) {
      setSelectedIncidents(selectedIncidents.filter((i) => i !== id));
    } else {
      setSelectedIncidents([...selectedIncidents, id]);
    }
  };

  return (
    <div className="min-h-screen">
      <Header title="Incidents" showDateNav={false} />
      <div className="p-6">
        {/* Filters */}
        <div className="flex flex-wrap items-center gap-3 mb-6">
          <Select
            value={filters.severity as string}
            onValueChange={(value) => setFilters({ ...filters, severity: value as Severity | 'all' })}
          >
            <SelectTrigger className="w-40 bg-secondary/50">
              <SelectValue placeholder="All Severities" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Severities</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={filters.type as string}
            onValueChange={(value) => setFilters({ ...filters, type: value as Incident['type'] | 'all' })}
          >
            <SelectTrigger className="w-36 bg-secondary/50">
              <SelectValue placeholder="All Types" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="fire">Fire</SelectItem>
              <SelectItem value="weapon">Weapon</SelectItem>
              <SelectItem value="fall">Fall</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={filters.status as string}
            onValueChange={(value) => setFilters({ ...filters, status: value as IncidentStatus | 'all' })}
          >
            <SelectTrigger className="w-36 bg-secondary/50">
              <SelectValue placeholder="All Statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Statuses</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="acknowledged">Acknowledged</SelectItem>
              <SelectItem value="resolved">Resolved</SelectItem>
            </SelectContent>
          </Select>

          <Select defaultValue="7days">
            <SelectTrigger className="w-36 bg-secondary/50">
              <SelectValue placeholder="Time Period" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="24h">Last 24 Hours</SelectItem>
              <SelectItem value="7days">Last 7 Days</SelectItem>
              <SelectItem value="30days">Last 30 Days</SelectItem>
              <SelectItem value="custom">Custom Range</SelectItem>
            </SelectContent>
          </Select>

          <div className="ml-auto flex items-center gap-2">
            <span className="text-sm text-muted-foreground">
              {data?.total ?? 0} total events
            </span>
            <Button variant="outline" className="gap-2">
              <Download className="h-4 w-4" />
              Export
            </Button>
          </div>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center min-h-[40vh]">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="flex flex-col items-center justify-center gap-4 min-h-[40vh]">
            <p className="text-severity-critical text-lg">Failed to load incidents</p>
            <p className="text-muted-foreground text-sm">{(error as Error).message}</p>
            <Button variant="outline" className="gap-2" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4" />
              Retry
            </Button>
          </div>
        )}

        {/* Incidents Table */}
        {!isLoading && !error && (
          <div className="dashboard-card">
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th className="w-12">
                      <Checkbox
                        checked={incidents.length > 0 && selectedIncidents.length === incidents.length}
                        onCheckedChange={toggleSelectAll}
                      />
                    </th>
                    <th>ID</th>
                    <th>Time</th>
                    <th>Camera</th>
                    <th>Type</th>
                    <th>Severity</th>
                    <th>Confidence</th>
                    <th>Status</th>
                    <th>
                      <span className="flex items-center gap-1">
                        <Paperclip className="h-3.5 w-3.5" />
                        Evidence
                      </span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="text-center text-muted-foreground py-8">
                        No incidents found
                      </td>
                    </tr>
                  ) : (
                    incidents.map((incident) => (
                      <tr key={incident.id} className="hover:bg-secondary/30 transition-colors">
                        <td>
                          <Checkbox
                            checked={selectedIncidents.includes(incident.id)}
                            onCheckedChange={() => toggleSelect(incident.id)}
                          />
                        </td>
                        <td className="text-sm font-mono">#{incident.id.slice(0, 8)}</td>
                        <td className="text-sm">{incident.time}</td>
                        <td>
                          <div>
                            <div className="text-sm font-medium">{incident.camera.name}</div>
                            <div className="text-xs text-muted-foreground">
                              {incident.camera.location}
                            </div>
                          </div>
                        </td>
                        <td className="text-sm capitalize">{incident.type}</td>
                        <td>
                          <SeverityBadge severity={incident.severity} />
                        </td>
                        <td className="text-sm font-mono">
                          {(incident.confidence * 100).toFixed(1)}%
                        </td>
                        <td>
                          <StatusBadge status={incident.status} />
                        </td>
                        <td>
                          <Button
                            id={`view-evidence-${incident.id}`}
                            size="sm"
                            variant="outline"
                            className="gap-1.5 text-xs h-7 px-2"
                            onClick={() => setActiveIncident(incident)}
                          >
                            <Paperclip className="h-3 w-3" />
                            View
                          </Button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Evidence modal */}
      <EvidenceModal
        incident={activeIncident}
        onClose={() => setActiveIncident(null)}
      />
    </div>
  );
}
