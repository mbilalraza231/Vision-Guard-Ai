import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Plus, Edit } from 'lucide-react';
import { SeverityBadge } from '@/components/common/StatusBadge';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import type { Zone, Severity } from '@/types';

// Mock zone data
const mockZones: Zone[] = [
  {
    id: '1',
    name: 'Warehouse Zone A',
    cameras: [],
    activeHours: '24/7',
    alertRecipients: 5,
    detectionPriority: { fire: 'critical', weapon: 'critical', fall: 'high', intrusion: 'medium' },
    recentActivity: 41,
  },
  {
    id: '2',
    name: 'Warehouse Zone B',
    cameras: [],
    activeHours: '24/7',
    alertRecipients: 5,
    detectionPriority: { fire: 'critical', weapon: 'critical', fall: 'high', intrusion: 'medium' },
    recentActivity: 41,
  },
  {
    id: '3',
    name: 'Office Area',
    cameras: [],
    activeHours: '8AM - 8PM',
    alertRecipients: 3,
    detectionPriority: { fire: 'critical', weapon: 'critical', fall: 'high', intrusion: 'medium' },
    recentActivity: 15,
  },
];

const getChartData = (zone: Zone) => [
  { type: 'Fire', count: Math.floor(Math.random() * 20) + 40 },
  { type: 'Weapon', count: Math.floor(Math.random() * 20) + 35 },
  { type: 'Fall', count: Math.floor(Math.random() * 15) + 30 },
  { type: 'Intrusion', count: Math.floor(Math.random() * 15) + 25 },
];

export default function Zones() {
  return (
    <div className="min-h-screen">
      <Header title="Zones Management" showDateNav={false} />
      <div className="p-6">
        {/* Header Actions */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-muted-foreground">
              {mockZones.length} zones configured
            </p>
          </div>
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            Add Zone
          </Button>
        </div>

        {/* Zones List */}
        <div className="space-y-4">
          {mockZones.map((zone) => (
            <div key={zone.id} className="dashboard-card p-6">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Chart */}
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={getChartData(zone)} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                      <XAxis type="number" stroke="hsl(var(--muted-foreground))" fontSize={12} domain={[0, 60]} />
                      <YAxis
                        type="category"
                        dataKey="type"
                        stroke="hsl(var(--muted-foreground))"
                        fontSize={12}
                        width={60}
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
                    <Button variant="outline" size="sm" className="gap-2">
                      <Edit className="h-4 w-4" />
                      Edit
                    </Button>
                  </div>

                  <div className="space-y-2 text-sm mb-4">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Active Hours:</span>
                      <span>{zone.activeHours}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Cameras:</span>
                      <span>2</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Alert Recipients:</span>
                      <span>{zone.alertRecipients} users</span>
                    </div>
                  </div>

                  {/* Detection Priority */}
                  <div className="mb-4">
                    <h4 className="font-medium mb-2">Detection Priority</h4>
                    <div className="grid grid-cols-4 gap-4">
                      {Object.entries(zone.detectionPriority).map(([type, severity]) => (
                        <div key={type} className="text-center">
                          <p className="text-sm font-medium capitalize mb-1">{type}</p>
                          <SeverityBadge severity={severity as Severity} />
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Recent Activity */}
                  <p className="text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">Recent Activity:</span>{' '}
                    {zone.recentActivity} incidents (7d)
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
