import { Button } from '@/components/ui/button';
import { SeverityBadge, StatusBadge } from '@/components/common/StatusBadge';
import type { Incident } from '@/types';

interface RecentIncidentsTableProps {
  incidents: Incident[];
  onViewIncident?: (incident: Incident) => void;
}

export function RecentIncidentsTable({ incidents, onViewIncident }: RecentIncidentsTableProps) {
  return (
    <div className="dashboard-card p-6">
      <h2 className="text-xl font-bold mb-4">Recent Incidents</h2>
      <div className="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Camera</th>
              <th>Event Type</th>
              <th>Severity</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((incident) => (
              <tr key={incident.id} className="hover:bg-secondary/30 transition-colors">
                <td className="text-sm">{incident.time}</td>
                <td>
                  <div>
                    <div className="text-sm font-medium">{incident.camera.name}</div>
                    <div className="text-xs text-muted-foreground">{incident.camera.location}</div>
                  </div>
                </td>
                <td className="text-sm capitalize">{incident.type}</td>
                <td>
                  <SeverityBadge severity={incident.severity} />
                </td>
                <td>
                  <StatusBadge status={incident.status} />
                </td>
                <td>
                  <Button
                    variant="link"
                    size="sm"
                    className="text-primary p-0 h-auto"
                    onClick={() => onViewIncident?.(incident)}
                  >
                    View
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
