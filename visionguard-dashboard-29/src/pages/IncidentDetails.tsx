import { useState, useEffect } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { SeverityBadge, StatusBadge } from '@/components/common/StatusBadge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { useSettings } from '@/hooks/useSettings';
import { useProfile } from '@/hooks/useProfile';
import { formatDateTime, formatTimeString } from '@/lib/utils';
import { API_ENDPOINTS, buildApiUrl } from '@/config/api';
import { apiService } from '@/services/api.service';
import {
  ChevronLeft,
  Clock,
  Camera,
  MapPin,
  Shield,
  Video,
  Download,
  Share2,
  MessageSquare,
  AlertTriangle,
  Loader2,
  Zap
} from 'lucide-react';
import type { Incident } from '@/types';

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
}

type ActionSource = 'dashboard' | 'email' | 'whatsapp';

const ACTION_CHANNEL_LABELS: Record<ActionSource, string> = {
  dashboard: 'Dashboard',
  email: 'Email',
  whatsapp: 'WhatsApp',
};

function parseActionSource(value: string | null): ActionSource {
  const key = (value ?? '').toLowerCase();
  if (key === 'email' || key === 'whatsapp') return key;
  return 'dashboard';
}

function parseNoteAuthor(userName: string | undefined): { name: string; channel?: string } {
  const raw = String(userName ?? '').trim();
  const channelMatch = raw.match(/^\[System:(\w+)\] (.+)$/);
  if (channelMatch) {
    const source = parseActionSource(channelMatch[1]);
    return { name: channelMatch[2], channel: ACTION_CHANNEL_LABELS[source] };
  }
  if (raw.startsWith('[System] ')) {
    return { name: raw.slice('[System] '.length), channel: 'Dashboard' };
  }
  return { name: raw || 'Unknown' };
}

function isSystemNote(userName: string | undefined): boolean {
  return /^\[System(?::\w+)?\]/.test(String(userName ?? ''));
}

export default function IncidentDetails() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: settings } = useSettings();
  const timezone = settings?.general?.timezone || 'UTC';
  
  const [isNoteModalOpen, setIsNoteModalOpen] = useState(false);
  const [newNote, setNewNote] = useState('');
  const [isResolveModalOpen, setIsResolveModalOpen] = useState(false);
  const [resolutionType, setResolutionType] = useState('False Alarm');
  const [resolveNote, setResolveNote] = useState('');
  const queryClient = useQueryClient();

  const { data: profile } = useProfile();

  const { data: notes = [] } = useQuery<any[]>({
    queryKey: ['incident-notes', id],
    queryFn: () => apiService.getData<any[]>(API_ENDPOINTS.incidents.notes(id!)),
    enabled: !!id,
  });

  const addNoteMutation = useMutation({
    mutationFn: (noteContent: string) => {
      const userStr = profile 
        ? `${profile.name} (${profile.role.toUpperCase()})` 
        : 'Security Operator';
      return apiService.postData(API_ENDPOINTS.incidents.notes(id!), { 
        content: noteContent,
        user_name: `[System:dashboard] ${userStr}`
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incident-notes', id] });
      setNewNote('');
      setIsNoteModalOpen(false);
    },
  });

  const getActorName = () =>
    profile ? `${profile.name} (${profile.role.toUpperCase()})` : 'Security Operator';

  const acknowledgeMutation = useMutation({
    mutationFn: (source: ActionSource = 'dashboard') => {
      return apiService.putData(API_ENDPOINTS.incidents.acknowledge(id!), {
        user_name: getActorName(),
        source,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incident', id] });
      queryClient.invalidateQueries({ queryKey: ['incident-notes', id] });
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (data: { resolution: string; content?: string; source?: ActionSource }) => {
      return apiService.putData(API_ENDPOINTS.incidents.resolve(id!), {
        user_name: getActorName(),
        resolution: data.resolution,
        content: data.content,
        source: data.source ?? 'dashboard',
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incident', id] });
      queryClient.invalidateQueries({ queryKey: ['incident-notes', id] });
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
    },
  });

  const { data: incident, isLoading: incidentLoading, error: incidentError } = useQuery({
    queryKey: ['incident', id],
    queryFn: async () => {
      // Fetch single incident
      // For now we fetch from list and find, but in production we'd have a single GET endpoint
      const response = await apiService.getData<{ events: any[] }>(API_ENDPOINTS.incidents.list, { limit: '100' });
      const event = response.events.find(e => e.id === id);
      if (!event) throw new Error('Incident not found');

      return {
        id: event.id,
        time: formatTimeString(event.start_ts * 1000, timezone),
        camera: {
          id: event.camera_id,
          name: event.camera_id,
          location: 'Camera',
          status: 'online',
          aiActive: true,
        },
        type: event.event_type as Incident['type'],
        severity: event.severity as Incident['severity'],
        status: (event.status || 'active') as Incident['status'],
        acknowledgedBy: event.acknowledged_by,
        acknowledgedAt: event.acknowledged_at,
        resolvedBy: event.resolved_by,
        resolvedAt: event.resolved_at,
        resolution: event.resolution,
        incidentTime: formatDateTime(event.start_ts * 1000, timezone),
        reportingTime: formatDateTime(event.created_at * 1000, timezone),
        processingDelay: event.created_at - event.start_ts,
        createdAt: new Date(event.created_at * 1000).toISOString(),
        updatedAt: new Date(event.end_ts * 1000).toISOString(),
        confidence: event.confidence,
      };
    },
  });

  const { data: evidence, isLoading: evidenceLoading } = useQuery<EvidenceResponse>({
    queryKey: ['evidence', id],
    queryFn: () => apiService.getData<EvidenceResponse>(API_ENDPOINTS.incidents.evidence(id!)),
    enabled: !!id && !!incident,
  });

  useEffect(() => {
    if (searchParams.get('action') === 'acknowledge' && incident && incident.status === 'active' && !incident.acknowledgedBy) {
      const source = parseActionSource(searchParams.get('from'));
      acknowledgeMutation.mutate(source);
      searchParams.delete('action');
      searchParams.delete('from');
      setSearchParams(searchParams, { replace: true });
    }
  }, [searchParams, incident, acknowledgeMutation, setSearchParams]);

  if (incidentLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (incidentError || !incident) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background">
        <AlertTriangle className="h-12 w-12 text-severity-critical" />
        <h2 className="text-xl font-bold">Incident Not Found</h2>
        <Button onClick={() => navigate('/incidents')}>Back to Incidents</Button>
      </div>
    );
  }

  const getMediaUrl = (url: string | null) => {
    if (!url) return undefined;
    if (url.startsWith('http')) return url;
    return buildApiUrl(url);
  };

  const handleDownloadEvidence = async () => {
    try {
      const mediaUrl = evidence?.clip_url ? getMediaUrl(evidence.clip_url) : getMediaUrl(evidence?.snapshot_url || null);
      if (!mediaUrl) {
        toast.error('No evidence available to download');
        return;
      }
      
      // Try to fetch and trigger a direct file download
      toast.info('Starting download...');
      const response = await fetch(mediaUrl);
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `incident-${id}-evidence.${evidence?.clip_url ? 'mp4' : 'jpg'}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
      toast.success('Evidence downloaded successfully');
    } catch (err) {
      console.error('Download failed', err);
      // Fallback: Open in new tab if direct download fails (e.g. CORS)
      const fallbackUrl = evidence?.clip_url ? getMediaUrl(evidence.clip_url) : getMediaUrl(evidence?.snapshot_url || null);
      if (fallbackUrl) {
        window.open(fallbackUrl, '_blank');
      } else {
        toast.error('Failed to download evidence');
      }
    }
  };

  const handleShare = async () => {
    try {
      const shareData = {
        title: `VisionGuard Incident: ${incident?.type}`,
        text: `Review this security incident on VisionGuard AI.`,
        url: window.location.href,
      };
      
      if (navigator.share && navigator.canShare && navigator.canShare(shareData)) {
        await navigator.share(shareData);
      } else {
        await navigator.clipboard.writeText(window.location.href);
        toast.success('Link copied to clipboard');
      }
    } catch (err) {
      console.error('Error sharing:', err);
      try {
        await navigator.clipboard.writeText(window.location.href);
        toast.success('Link copied to clipboard');
      } catch {
        toast.error('Failed to copy link');
      }
    }
  };

  const handleAddPostResolutionNote = () => {
    if (!newNote.trim()) return;
    toast.promise(
      addNoteMutation.mutateAsync(newNote.trim()),
      {
        loading: 'Saving follow-up note...',
        success: 'Follow-up note saved',
        error: (err: any) => err?.message || 'Failed to save follow-up note',
      }
    );
  };

  const sortedNotes = [...notes].sort((a, b) => b.created_at - a.created_at);

  // Group notes by user and channel for compact card display
  type NoteGroup = { name: string; channel?: string; notes: any[] };
  const groupedNotes = sortedNotes.reduce((groups, note) => {
    const systemNote = isSystemNote(note.user_name);
    const { name, channel } = parseNoteAuthor(note.user_name);
    const key = `${name}|${channel || ''}`;
    
    if (!groups[key]) {
      groups[key] = {
        name,
        channel,
        notes: []
      };
    }
    groups[key].notes.push(note);
    return groups;
  }, {} as Record<string, NoteGroup>);

  const handleAcknowledge = () => {
    toast.promise(
      acknowledgeMutation.mutateAsync('dashboard'),
      {
        loading: 'Acknowledging alert...',
        success: 'Alert acknowledged successfully',
        error: (err: any) => err?.message || 'Failed to acknowledge alert',
      }
    );
  };

  const handleResolve = () => {
    toast.promise(
      resolveMutation.mutateAsync({ resolution: resolutionType, content: resolveNote, source: 'dashboard' }),
      {
        loading: 'Resolving incident...',
        success: () => {
          setIsResolveModalOpen(false);
          setResolveNote('');
          return 'Incident resolved successfully';
        },
        error: (err: any) => err?.message || 'Failed to resolve incident',
      }
    );
  };

  return (
    <div className="min-h-screen bg-background">
      <Header title="Incident Details" showDateNav={false} />

      <div className="p-6">
        {/* Navigation & Actions */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <Button
            variant="ghost"
            className="gap-2"
            onClick={() => navigate('/incidents')}
          >
            <ChevronLeft className="h-4 w-4" />
            Back to Incidents
          </Button>

          <div className="flex items-center gap-2">
            <Button variant="outline" className="gap-2" onClick={handleDownloadEvidence}>
              <Download className="h-4 w-4" />
              Download Evidence
            </Button>
            <Button variant="outline" className="gap-2" onClick={handleShare}>
              <Share2 className="h-4 w-4" />
              Share
            </Button>
            {incident.status === 'resolved' && (
              <Button
                className="gap-2"
                onClick={() => setIsNoteModalOpen(true)}
                disabled={profile?.role === 'viewer'}
              >
                <MessageSquare className="h-4 w-4" />
                Add Follow-up Note
              </Button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Main Content: Media */}
          <div className="lg:col-span-2 space-y-6">
            <div className="dashboard-card overflow-hidden">
              <div className="border-b border-white/5 bg-white/5 p-4 flex items-center justify-between">
                <div className="flex items-center gap-2 font-medium">
                  <Video className="h-4 w-4 text-primary" />
                  Video Evidence
                </div>
                {evidence?.clip_status === 'pending' && (
                  <Badge variant="outline" className="animate-pulse">Processing Clip...</Badge>
                )}
              </div>
              <div className="aspect-video bg-black relative flex items-center justify-center">
                {evidence?.clip_url ? (
                  <video
                    controls
                    className="h-full w-full object-contain"
                    src={getMediaUrl(evidence.clip_url)}
                  />
                ) : (
                  <div className="text-center text-muted-foreground">
                    <Loader2 className="h-8 w-8 animate-spin mx-auto mb-2 text-primary" />
                    <p>Loading video evidence...</p>
                  </div>
                )}
              </div>
            </div>

            <div className="dashboard-card overflow-hidden">
              <div className="border-b border-white/5 bg-white/5 p-4 flex items-center gap-2 font-medium">
                <Camera className="h-4 w-4 text-primary" />
                Detection Snapshot
              </div>
              <div className="bg-black relative flex items-center justify-center" style={{ minHeight: '300px' }}>
                {evidence?.snapshot_url ? (
                  <img
                    className="w-full object-contain"
                    src={getMediaUrl(evidence.snapshot_url)}
                    alt="Detection snapshot"
                  />
                ) : (
                  <div className="text-center text-muted-foreground">
                    <AlertTriangle className="h-8 w-8 mx-auto mb-2 opacity-20" />
                    <p>Snapshot unavailable</p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Sidebar: Details */}
          <div className="space-y-6">
            <div className="dashboard-card p-6">
              <h3 className="text-lg font-bold mb-4">Incident Info</h3>
              <div className="space-y-4">
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-muted-foreground flex items-center gap-2">
                    <Shield className="h-4 w-4" /> Type
                  </span>
                  <span className="font-bold capitalize">{incident.type}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-muted-foreground flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4" /> Severity
                  </span>
                  <SeverityBadge severity={incident.severity} />
                </div>
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-muted-foreground flex items-center gap-2">
                    <Clock className="h-4 w-4" /> Incident Time
                  </span>
                  <span className="font-mono text-sm">{incident.incidentTime}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-muted-foreground flex items-center gap-2">
                    <Zap className="h-4 w-4 text-status-online" /> Reporting Time
                  </span>
                  <span className="font-mono text-sm">{incident.reportingTime}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-muted-foreground flex items-center gap-2">
                    <Camera className="h-4 w-4" /> Camera
                  </span>
                  <span className="font-medium">{incident.camera.name}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-muted-foreground flex items-center gap-2">
                    <MapPin className="h-4 w-4" /> Location
                  </span>
                  <span>{incident.camera.location}</span>
                </div>
                <div className="flex justify-between items-center py-2">
                  <span className="text-muted-foreground">Status</span>
                  <StatusBadge status={incident.status} />
                </div>
                {incident.status === 'acknowledged' && (incident as any).acknowledgedBy && (
                  <div className="flex justify-between items-center py-2 border-t border-white/5">
                    <span className="text-muted-foreground text-xs">Acknowledged By</span>
                    <span className="text-xs font-semibold">{(incident as any).acknowledgedBy}</span>
                  </div>
                )}
                {incident.status === 'resolved' && (incident as any).resolvedBy && (
                  <div className="flex flex-col gap-1 py-2 border-t border-white/5">
                    <div className="flex justify-between items-center">
                      <span className="text-muted-foreground text-xs">Resolved By</span>
                      <span className="text-xs font-semibold">{(incident as any).resolvedBy}</span>
                    </div>
                    <div className="flex justify-between items-center text-[11px]">
                      <span className="text-muted-foreground">Reason</span>
                      <span className="text-primary font-medium">{(incident as any).resolution}</span>
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-6 pt-6 border-t border-white/10">
                <h4 className="text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">AI Confidence</h4>
                <div className="flex items-center gap-4">
                  <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
                    <div
                      className="h-full bg-primary"
                      style={{ width: `${(incident as any).confidence * 100}%` }}
                    />
                  </div>
                  <span className="font-mono font-bold text-primary">
                    {((incident as any).confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="mt-6 pt-6 border-t border-white/10 space-y-3">
                {incident.status === 'active' && (
                  <Button 
                    className="w-full gap-2"
                    onClick={() => handleAcknowledge()}
                    disabled={profile?.role === 'viewer' || acknowledgeMutation.isPending}
                  >
                    {acknowledgeMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Zap className="h-4 w-4" />
                    )}
                    Acknowledge Alert
                  </Button>
                )}
                {incident.status === 'acknowledged' && (
                  <Button 
                    className="w-full gap-2"
                    variant="outline"
                    onClick={() => setIsResolveModalOpen(true)}
                    disabled={profile?.role === 'viewer'}
                  >
                    <Shield className="h-4 w-4" />
                    Mark as Resolved
                  </Button>
                )}
                {incident.status === 'resolved' && (
                  <div className="bg-status-online/10 text-status-online border border-status-online/20 text-center py-2.5 rounded-lg text-sm font-semibold flex items-center justify-center gap-2">
                    <Shield className="h-4 w-4" />
                    Incident Resolved
                  </div>
                )}
              </div>
            </div>

            <div className="dashboard-card p-6 max-h-[400px] overflow-hidden flex flex-col">
              <h3 className="text-lg font-bold mb-4 shrink-0">Investigation Notes</h3>
              <div className="space-y-3 overflow-y-auto pr-2">
                {notes.length === 0 ? (
                  <p className="text-sm text-muted-foreground italic">
                    {incident.status === 'resolved'
                      ? 'No notes yet. Use Add Follow-up Note next to Share.'
                      : 'Notes can be added after this incident is resolved.'}
                  </p>
                ) : (
                  (Object.values(groupedNotes) as NoteGroup[]).map((group, groupIndex) => {
                    const systemNote = isSystemNote(group.notes[0].user_name);
                    // Sort notes within group: follow-up notes first, then resolves, then acknowledges
                    const sortedGroupNotes = [...group.notes].sort((a, b) => {
                      const aContent = a.content.toLowerCase();
                      const bContent = b.content.toLowerCase();
                      
                      const aIsAck = aContent.includes('acknowledged');
                      const bIsAck = bContent.includes('acknowledged');
                      const aIsRes = aContent.includes('resolved');
                      const bIsRes = bContent.includes('resolved');
                      
                      // Follow-up notes (not ack/resolve) come first
                      if (!aIsAck && !aIsRes && (bIsAck || bIsRes)) return -1;
                      if ((aIsAck || aIsRes) && !bIsAck && !bIsRes) return 1;
                      
                      // Resolves come before acknowledges
                      if (aIsRes && bIsAck) return -1;
                      if (aIsAck && bIsRes) return 1;
                      
                      // Same type: newer first
                      return b.created_at - a.created_at;
                    });
                    
                    return (
                      <div
                        key={groupIndex}
                        className={`p-3 rounded-lg border ${
                          systemNote
                            ? 'bg-secondary/20 border-white/5'
                            : 'bg-primary/5 border-primary/20'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-2 gap-2">
                          <div className="flex items-center gap-1.5 min-w-0">
                            <span className="text-xs font-semibold text-primary truncate">{group.name}</span>
                            {systemNote && group.channel && (
                              <span className="text-[10px] text-muted-foreground shrink-0">· {group.channel}</span>
                            )}
                          </div>
                        </div>
                        <div className="space-y-1.5">
                          {sortedGroupNotes.map((note) => {
                            // Shorten system note messages for display
                            let displayContent = note.content;
                            if (displayContent.startsWith('Acknowledged the incident')) {
                              displayContent = 'Acknowledged';
                            } else if (displayContent.startsWith('Resolved the incident')) {
                              displayContent = displayContent.replace('Resolved the incident', 'Resolved');
                            }
                            
                            return (
                              <div key={note.id} className="flex gap-2 text-xs">
                                <span className="text-muted-foreground shrink-0 font-mono">
                                  {formatDateTime(note.created_at * 1000, timezone).split(',')[1]?.trim() || formatDateTime(note.created_at * 1000, timezone)}
                                </span>
                                <span className="text-foreground/90 whitespace-pre-wrap flex-1">{displayContent}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={isNoteModalOpen} onOpenChange={setIsNoteModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add Follow-up Note</DialogTitle>
          </DialogHeader>
          <div className="py-4">
            <textarea
              className="w-full h-32 bg-secondary/50 border border-white/10 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
              placeholder="Enter follow-up details..."
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsNoteModalOpen(false)}>Cancel</Button>
            <Button onClick={handleAddPostResolutionNote}>Save Note</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isResolveModalOpen} onOpenChange={setIsResolveModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Resolve Incident</DialogTitle>
          </DialogHeader>
          <div className="py-4 space-y-4">
            <div className="space-y-2">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block">Resolution Reason</label>
              <select 
                className="w-full bg-secondary/50 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 text-foreground"
                value={resolutionType}
                onChange={(e) => setResolutionType(e.target.value)}
              >
                <option value="False Alarm">False Alarm</option>
                <option value="Resolved by Guard">Resolved by Guard</option>
                <option value="System Test">System Test</option>
                <option value="Other">Other</option>
              </select>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider block">Resolution Notes (Optional)</label>
              <textarea
                className="w-full h-24 bg-secondary/50 border border-white/10 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary/50"
                placeholder="Enter details on how the alert was resolved..."
                value={resolveNote}
                onChange={(e) => setResolveNote(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsResolveModalOpen(false)}>Cancel</Button>
            <Button onClick={handleResolve} disabled={resolveMutation.isPending}>
              {resolveMutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Resolve Incident
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
