import { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { SeverityBadge, StatusBadge } from '@/components/common/StatusBadge';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { formatDateTime, formatTimeString } from '@/lib/utils';
import { API_ENDPOINTS, buildApiUrl, API_CONFIG } from '@/config/api';
import { apiService } from '@/services/api.service';
import {
  ChevronLeft,
  Clock,
  Camera,
  Shield,
  Video,
  AlertTriangle,
  Loader2,
  Zap,
  CheckCircle,
  XCircle
} from 'lucide-react';

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
  return 'email';
}

function parseNoteAuthor(userName: string | undefined): { name: string; channel?: string } {
  const raw = String(userName ?? '').trim();
  const channelMatch = raw.match(/^\[System:(\w+)\] (.+)$/);
  if (channelMatch) {
    const source = parseActionSource(channelMatch[1]);
    return { name: channelMatch[2], channel: source === 'email' ? 'Email' : source === 'whatsapp' ? 'WhatsApp' : 'Dashboard' };
  }
  if (raw.startsWith('[System] ')) {
    return { name: raw.slice('[System] '.length), channel: 'Dashboard' };
  }
  return { name: raw || 'Unknown' };
}

function isSystemNote(userName: string | undefined): boolean {
  return /^\[System(?::\w+)?\]/.test(String(userName ?? ''));
}

export default function PublicIncident() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const token = searchParams.get('token');
  const action = searchParams.get('action');
  const source = parseActionSource(searchParams.get('from'));
  
  const [contactName, setContactName] = useState('');
  const [isResolveModalOpen, setIsResolveModalOpen] = useState(false);
  const [resolutionType, setResolutionType] = useState('False Alarm');
  const [resolveNote, setResolveNote] = useState('');
  const [isNoteModalOpen, setIsNoteModalOpen] = useState(false);
  const [newNote, setNewNote] = useState('');
  
  const queryClient = useQueryClient();

  // Fetch public incident data with token validation
  const { data: incident, isLoading: incidentLoading, error: incidentError } = useQuery({
    queryKey: ['public-incident', id, token],
    queryFn: async () => {
      const response = await fetch(`${API_CONFIG.baseUrl}${API_ENDPOINTS.incidents.list}/${id}/public?token=${token}`);
      if (!response.ok) {
        if (response.status === 401) {
          throw new Error('Invalid or expired access token');
        }
        if (response.status === 404) {
          throw new Error('Incident not found');
        }
        throw new Error('Failed to load incident');
      }
      return response.json();
    },
    enabled: !!id && !!token,
  });

  const { data: evidence, isLoading: evidenceLoading } = useQuery<EvidenceResponse>({
    queryKey: ['evidence', id],
    queryFn: () => apiService.getData<EvidenceResponse>(API_ENDPOINTS.incidents.evidence(id!)),
    enabled: !!id && !!incident,
  });

  const { data: notes = [] } = useQuery<any[]>({
    queryKey: ['incident-notes', id],
    queryFn: () => apiService.getData<any[]>(API_ENDPOINTS.incidents.notes(id!)),
    enabled: !!id && !!incident,
  });

  const acknowledgeMutation = useMutation({
    mutationFn: () => {
      return apiService.putData(`${API_ENDPOINTS.incidents.list}/${id}/public/acknowledge?token=${token}`, {
        user_name: `[System:${source}] Alert Contact`,
        source,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['public-incident', id, token] });
      queryClient.invalidateQueries({ queryKey: ['incident-notes', id] });
      toast.success('Incident acknowledged successfully');
    },
    onError: (error: any) => {
      toast.error(error?.message || 'Failed to acknowledge incident');
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (data: { resolution: string; content?: string }) => {
      return apiService.putData(`${API_ENDPOINTS.incidents.list}/${id}/public/resolve?token=${token}`, {
        user_name: `[System:${source}] Alert Contact`,
        resolution: data.resolution,
        content: data.content,
        source,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['public-incident', id, token] });
      queryClient.invalidateQueries({ queryKey: ['incident-notes', id] });
      setIsResolveModalOpen(false);
      setResolveNote('');
      toast.success('Incident resolved successfully');
    },
    onError: (error: any) => {
      toast.error(error?.message || 'Failed to resolve incident');
    },
  });

  const addNoteMutation = useMutation({
    mutationFn: (noteContent: string) => {
      return apiService.postData(`${API_ENDPOINTS.incidents.list}/${id}/public/notes?token=${token}`, {
        content: noteContent,
        user_name: `[System:${source}] Alert Contact (${source === 'email' ? 'Email' : 'WhatsApp'})`,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['incident-notes', id] });
      setNewNote('');
      setIsNoteModalOpen(false);
      toast.success('Note added successfully');
    },
    onError: (error: any) => {
      toast.error(error?.message || 'Failed to add note');
    },
  });

  // Auto-execute action from URL params
  useEffect(() => {
    if (action === 'acknowledge' && incident && incident.status === 'active' && !incident.acknowledgedBy) {
      acknowledgeMutation.mutate();
      searchParams.delete('action');
      setSearchParams(searchParams, { replace: true });
    }
  }, [action, incident, acknowledgeMutation, searchParams, setSearchParams]);

  if (incidentLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (incidentError || !incident) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center gap-4 p-6">
        <XCircle className="h-12 w-12 text-red-500" />
        <h2 className="text-xl font-bold text-center">
          {incidentError instanceof Error ? incidentError.message : 'Incident Not Found'}
        </h2>
        <p className="text-muted-foreground text-center max-w-md">
          This link may be invalid or expired. Please contact your system administrator.
        </p>
      </div>
    );
  }

  const getMediaUrl = (url: string | null) => {
    if (!url) return undefined;
    if (url.startsWith('http')) return url;
    return buildApiUrl(url);
  };

  const handleAcknowledge = () => {
    acknowledgeMutation.mutate();
  };

  const handleResolve = () => {
    resolveMutation.mutate({ resolution: resolutionType, content: resolveNote });
  };

  const handleAddNote = () => {
    if (!newNote.trim()) {
      toast.error('Please enter a note');
      return;
    }
    addNoteMutation.mutate(newNote.trim());
  };

  const timezone = 'UTC'; // Public page uses UTC by default

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-white/10 bg-white/5 p-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Shield className="h-6 w-6 text-primary" />
            <h1 className="text-xl font-bold">VisionGuard AI - Public Incident View</h1>
          </div>
          <Badge variant="outline" className="gap-1">
            <AlertTriangle className="h-3 w-3" />
            Alert Contact Access
          </Badge>
        </div>
      </div>

      <div className="p-6 max-w-7xl mx-auto">
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
                  <span className="font-bold capitalize">{incident.event_type}</span>
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
                  <span className="font-mono text-sm">{formatDateTime(incident.start_ts * 1000, timezone)}</span>
                </div>
                <div className="flex justify-between items-center py-2 border-b border-white/5">
                  <span className="text-muted-foreground flex items-center gap-2">
                    <Camera className="h-4 w-4" /> Camera
                  </span>
                  <span className="font-medium">{incident.camera_id}</span>
                </div>
                <div className="flex justify-between items-center py-2">
                  <span className="text-muted-foreground">Status</span>
                  <StatusBadge status={incident.status || 'active'} />
                </div>
                {incident.acknowledged_by && (
                  <div className="flex justify-between items-center py-2 border-t border-white/5">
                    <span className="text-muted-foreground text-xs">Acknowledged By</span>
                    <span className="text-xs font-semibold">{incident.acknowledged_by}</span>
                  </div>
                )}
                {incident.resolved_by && (
                  <div className="flex flex-col gap-1 py-2 border-t border-white/5">
                    <div className="flex justify-between items-center">
                      <span className="text-muted-foreground text-xs">Resolved By</span>
                      <span className="text-xs font-semibold">{incident.resolved_by}</span>
                    </div>
                    <div className="flex justify-between items-center text-[11px]">
                      <span className="text-muted-foreground">Reason</span>
                      <span className="text-primary font-medium">{incident.resolution}</span>
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
                      style={{ width: `${(incident.confidence * 100).toFixed(1)}%` }}
                    />
                  </div>
                  <span className="font-mono font-bold text-primary">
                    {(incident.confidence * 100).toFixed(1)}%
                  </span>
                </div>
              </div>

              <div className="mt-6 pt-6 border-t border-white/10 space-y-3">
                {incident.status === 'active' && (
                  <Button 
                    className="w-full gap-2"
                    onClick={handleAcknowledge}
                    disabled={acknowledgeMutation.isPending}
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
                    disabled={resolveMutation.isPending}
                  >
                    <Shield className="h-4 w-4" />
                    Mark as Resolved
                  </Button>
                )}
                {incident.status === 'resolved' && (
                  <Button 
                    className="w-full gap-2"
                    variant="outline"
                    onClick={() => setIsNoteModalOpen(true)}
                  >
                    <Shield className="h-4 w-4" />
                    Add Follow-up Note
                  </Button>
                )}
                {incident.status === 'resolved' && (
                  <div className="bg-green-500/10 text-green-500 border border-green-500/20 text-center py-2.5 rounded-lg text-sm font-semibold flex items-center justify-center gap-2">
                    <CheckCircle className="h-4 w-4" />
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
                      ? 'No notes yet. Add a follow-up note above.'
                      : 'Notes can be added after this incident is resolved.'}
                  </p>
                ) : (
                  // Group notes by author
                  Object.entries(
                    notes.reduce((groups: Record<string, any[]>, note) => {
                      const author = parseNoteAuthor(note.user_name).name;
                      if (!groups[author]) groups[author] = [];
                      groups[author].push(note);
                      return groups;
                    }, {})
                  ).map(([author, groupNotes]: [string, any[]], groupIndex) => {
                    const systemNote = isSystemNote(groupNotes[0].user_name);
                    const { channel } = parseNoteAuthor(groupNotes[0].user_name);
                    
                    // Sort notes within group: follow-up → resolve → acknowledge
                    const sortedGroupNotes = [...groupNotes].sort((a, b) => {
                      const aIsAck = a.content.startsWith('Acknowledged');
                      const aIsRes = a.content.startsWith('Resolved');
                      const bIsAck = b.content.startsWith('Acknowledged');
                      const bIsRes = b.content.startsWith('Resolved');
                      
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
                            <span className="text-xs font-semibold text-primary truncate">{author}</span>
                            {systemNote && channel && (
                              <span className="text-[10px] text-muted-foreground shrink-0">· {channel}</span>
                            )}
                          </div>
                        </div>
                        <div className="space-y-1.5 overflow-hidden">
                          {sortedGroupNotes.map((note) => {
                            // Shorten system note messages for display
                            let displayContent = note.content;
                            if (displayContent.startsWith('Acknowledged the incident')) {
                              displayContent = 'Acknowledged';
                            } else if (displayContent.startsWith('Resolved the incident')) {
                              displayContent = displayContent.replace('Resolved the incident', 'Resolved');
                            }
                            
                            return (
                              <div key={note.id} className="flex gap-2 text-xs min-w-0">
                                <span className="text-muted-foreground shrink-0 font-mono">
                                  {formatDateTime(note.created_at * 1000, timezone).split(',')[1]?.trim() || formatDateTime(note.created_at * 1000, timezone)}
                                </span>
                                <span className="text-foreground/90 whitespace-pre-wrap break-words flex-1 min-w-0">{displayContent}</span>
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
            <Button onClick={handleAddNote} disabled={addNoteMutation.isPending}>
              {addNoteMutation.isPending && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
              Save Note
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
