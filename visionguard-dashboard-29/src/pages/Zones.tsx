import { useState } from 'react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Plus, Edit, Trash2, Loader2, MapPin, Users, Camera, Activity } from 'lucide-react';
import { SeverityBadge } from '@/components/common/StatusBadge';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiService } from '@/services/api.service';
import { API_ENDPOINTS } from '@/config/api';
import type { ZoneApiResponse, Severity } from '@/types';

interface ZoneListApiResponse {
  total: number;
  zones: ZoneApiResponse[];
}

interface CameraApiItem {
  id: string;
  name: string;
  zone_id?: string | null;
  status?: string;
}

interface AlertContactApiItem {
  id: string;
  zone_ids?: string;
}

interface BackendEvent {
  id: string;
  camera_id: string;
  event_type: string;
  severity: string;
  start_ts: number;
  created_at: number;
}

// Detection priority is global (based on system model config)
const GLOBAL_DETECTION_PRIORITY: Record<string, Severity> = {
  fire: 'critical',
  weapon: 'critical',
  fall: 'high',
};

// Modal Component
function ZoneModal({
  zone,
  onClose,
  onSave,
  isSaving,
}: {
  zone?: ZoneApiResponse | null;
  onClose: () => void;
  onSave: (data: { name: string; active_hours: string }) => void;
  isSaving: boolean;
}) {
  const [name, setName] = useState(zone?.name ?? '');
  const [activeHours, setActiveHours] = useState(zone?.active_hours ?? '24/7');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    onSave({ name: name.trim(), active_hours: activeHours.trim() || '24/7' });
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="dashboard-card w-full max-w-md p-6 animate-in fade-in zoom-in-95 duration-200">
        <h2 className="text-xl font-bold mb-6">{zone ? 'Edit Zone' : 'Add Zone'}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1" htmlFor="zone-name">
              Zone Name
            </label>
            <input
              id="zone-name"
              type="text"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="e.g. Warehouse Zone A"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1" htmlFor="zone-hours">
              Active Hours
            </label>
            <select
              id="zone-hours"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              value={activeHours}
              onChange={(e) => setActiveHours(e.target.value)}
            >
              <option value="24/7">24/7 (Always On)</option>
              <option value="6AM - 10PM">6AM - 10PM</option>
              <option value="8AM - 6PM">8AM - 6PM (Business Hours)</option>
              <option value="8AM - 8PM">8AM - 8PM</option>
              <option value="10PM - 6AM">10PM - 6AM (Night Only)</option>
              <option value="Weekdays Only">Weekdays Only</option>
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={onClose} disabled={isSaving}>
              Cancel
            </Button>
            <Button type="submit" className="flex-1" disabled={isSaving || !name.trim()}>
              {isSaving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              {zone ? 'Save Changes' : 'Create Zone'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function Zones() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingZone, setEditingZone] = useState<ZoneApiResponse | null>(null);

  // Fetch zones
  const { data: zonesData, isLoading: zonesLoading } = useQuery({
    queryKey: ['zones'],
    queryFn: () => apiService.getData<ZoneListApiResponse>(API_ENDPOINTS.zones.list),
  });

  // Fetch cameras (for zone camera count)
  const { data: camerasData } = useQuery({
    queryKey: ['cameras-for-zones'],
    queryFn: () => apiService.getData<CameraApiItem[]>(API_ENDPOINTS.cameras.list),
  });

  // Fetch alert contacts (for zone recipient count)
  const { data: contactsData } = useQuery({
    queryKey: ['contacts-for-zones'],
    queryFn: () => apiService.getData<{ contacts: AlertContactApiItem[] }>(API_ENDPOINTS.alerts.contacts.list),
  });

  // Fetch all events from last 7 days (for chart + recent activity count)
  const { data: eventsData } = useQuery({
    queryKey: ['events-7d-zones'],
    queryFn: () => apiService.getData<{ events: BackendEvent[] }>(API_ENDPOINTS.incidents.list, { limit: '100', time_period: '7days' }),
  });

  // Create zone
  const createMutation = useMutation({
    mutationFn: (data: { name: string; active_hours: string }) =>
      apiService.postData(API_ENDPOINTS.zones.create, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['zones'] });
      setModalOpen(false);
    },
  });

  // Update zone
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name: string; active_hours: string } }) =>
      apiService.putData(API_ENDPOINTS.zones.update(id), data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['zones'] });
      setEditingZone(null);
    },
  });

  // Delete zone
  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiService.delete(API_ENDPOINTS.zones.delete(id)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['zones'] }),
  });

  const zones = zonesData?.zones ?? [];
  const cameras = camerasData ?? [];
  const contacts = contactsData?.contacts ?? [];
  const allEvents = eventsData?.events ?? [];

  // Build a map: camera_id -> zone_id for quick lookup
  const cameraZoneMap = new Map<string, string>();
  cameras.forEach((c) => { if (c.zone_id) cameraZoneMap.set(c.id, c.zone_id); });

  const getCameraCountForZone = (zoneId: string) =>
    cameras.filter((c) => c.zone_id === zoneId).length;

  const getRecipientCountForZone = (zoneId: string) =>
    contacts.filter((c) => {
      try {
        const ids: string[] = JSON.parse(c.zone_ids ?? '[]');
        return ids.includes(zoneId);
      } catch {
        return false;
      }
    }).length;

  // Filter events belonging to a zone (via camera mapping)
  const getEventsForZone = (zoneId: string) =>
    allEvents.filter((e) => cameraZoneMap.get(e.camera_id) === zoneId);

  const getChartData = (zoneId: string) => {
    const events = getEventsForZone(zoneId);
    const counts: Record<string, number> = { fire: 0, weapon: 0, fall: 0 };
    events.forEach((e) => {
      const type = e.event_type.replace('_detected', '').toLowerCase();
      if (type in counts) counts[type]++;
    });
    return [
      { type: 'Fire', count: counts.fire },
      { type: 'Weapon', count: counts.weapon },
      { type: 'Fall', count: counts.fall },
    ];
  };

  const handleSave = (data: { name: string; active_hours: string }) => {
    if (editingZone) {
      updateMutation.mutate({ id: editingZone.id, data });
    } else {
      createMutation.mutate(data);
    }
  };

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="min-h-screen">
      <Header title="Zones Management" showDateNav={false} />
      <div className="p-6">
        {/* Header Actions */}
        <div className="flex items-center justify-between mb-6">
          <p className="text-muted-foreground">
            {zones.length} zone{zones.length !== 1 ? 's' : ''} configured
          </p>
          <Button className="gap-2" onClick={() => { setEditingZone(null); setModalOpen(true); }}>
            <Plus className="h-4 w-4" />
            Add Zone
          </Button>
        </div>

        {/* Loading State */}
        {zonesLoading ? (
          <div className="flex items-center justify-center min-h-[40vh]">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : zones.length === 0 ? (
          <div className="dashboard-card p-12 text-center">
            <MapPin className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
            <h3 className="text-lg font-semibold mb-2">No Zones Configured</h3>
            <p className="text-muted-foreground mb-6">
              Create your first zone to organize cameras and alert recipients by physical location.
            </p>
            <Button onClick={() => { setEditingZone(null); setModalOpen(true); }} className="gap-2">
              <Plus className="h-4 w-4" />
              Create First Zone
            </Button>
          </div>
        ) : (
          /* Zones List */
          <div className="space-y-4">
            {zones.map((zone) => {
              const cameraCount = getCameraCountForZone(zone.id);
              const recipientCount = getRecipientCountForZone(zone.id);
              const chartData = getChartData(zone.id);
              const recentActivity = getEventsForZone(zone.id).length;
              return (
                <div key={zone.id} className="dashboard-card p-6">
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    {/* Chart */}
                    <div className="h-48">
                      <p className="text-xs text-muted-foreground mb-2">Detection Activity (7d)</p>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} layout="vertical">
                          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                          <XAxis type="number" stroke="hsl(var(--muted-foreground))" fontSize={12} />
                          <YAxis
                            type="category"
                            dataKey="type"
                            stroke="hsl(var(--muted-foreground))"
                            fontSize={12}
                            width={50}
                          />
                          <Tooltip
                            contentStyle={{
                              backgroundColor: 'hsl(var(--card))',
                              border: '1px solid hsl(var(--border))',
                              borderRadius: '8px',
                            }}
                          />
                          <Bar dataKey="count" fill="hsl(var(--primary))" radius={[0, 4, 4, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>

                    {/* Zone Info */}
                    <div>
                      <div className="flex items-start justify-between mb-4">
                        <h3 className="text-xl font-semibold">{zone.name}</h3>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-2"
                            onClick={() => { setEditingZone(zone); setModalOpen(true); }}
                          >
                            <Edit className="h-4 w-4" />
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1 text-severity-critical border-severity-critical/30 hover:bg-severity-critical/10"
                            onClick={() => deleteMutation.mutate(zone.id)}
                            disabled={deleteMutation.isPending}
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>

                      <div className="space-y-2 text-sm mb-4">
                        <div className="flex justify-between items-center">
                          <span className="text-muted-foreground flex items-center gap-1">
                            <Activity className="h-3 w-3" /> Active Hours:
                          </span>
                          <span className="font-medium">{zone.active_hours}</span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-muted-foreground flex items-center gap-1">
                            <Camera className="h-3 w-3" /> Cameras:
                          </span>
                          <span className="font-medium">{cameraCount}</span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-muted-foreground flex items-center gap-1">
                            <Users className="h-3 w-3" /> Alert Recipients:
                          </span>
                          <span className="font-medium">{recipientCount} users</span>
                        </div>
                      </div>

                      {/* Detection Priority */}
                      <div className="mb-4">
                        <h4 className="font-medium mb-2 text-sm">Detection Priority</h4>
                        <div className="grid grid-cols-3 gap-3">
                          {Object.entries(GLOBAL_DETECTION_PRIORITY).map(([type, severity]) => (
                            <div key={type} className="text-center">
                              <p className="text-sm font-medium capitalize mb-1">{type}</p>
                              <SeverityBadge severity={severity} />
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Recent Activity */}
                      <p className="text-sm text-muted-foreground mt-3">
                        <span className="font-medium text-foreground">Recent Activity:</span>{' '}
                        {recentActivity} incident{recentActivity !== 1 ? 's' : ''} (7d)
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Modal */}
      {modalOpen && (
        <ZoneModal
          zone={editingZone}
          onClose={() => { setModalOpen(false); setEditingZone(null); }}
          onSave={handleSave}
          isSaving={isSaving}
        />
      )}
    </div>
  );
}
