import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import type { User, UserRole } from '@/types';

// Mock user data
const mockUsers: User[] = [
  { id: '001', name: 'John Admin', email: 'admin@example.com', role: 'admin', status: 'active', createdAt: '' },
  { id: '002', name: 'Jane Manager', email: 'jane@example.com', role: 'manager', status: 'active', createdAt: '' },
  { id: '003', name: 'Mike Officer', email: 'mike@example.com', role: 'officer', status: 'active', createdAt: '' },
  { id: '004', name: 'Sarah Viewer', email: 'sarah@example.com', role: 'viewer', status: 'active', createdAt: '' },
];

const roleDescriptions: Record<UserRole, string> = {
  admin: 'Full system access, user management, settings configuration',
  manager: 'View and manage incidents, access analytics, configure alerts',
  officer: 'View live feeds, respond to incidents, add investigation notes',
  viewer: 'Read-only access to live feeds and incident reports',
};

export default function Users() {
  return (
    <div className="min-h-screen">
      <Header title="User Management" showDateNav={false} />
      <div className="p-6">
        {/* Header Actions */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <p className="text-muted-foreground">
              {mockUsers.length} users configured
            </p>
          </div>
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            Add User
          </Button>
        </div>

        {/* Users Table */}
        <div className="dashboard-card mb-6">
          <div className="overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {mockUsers.map((user) => (
                  <tr key={user.id} className="hover:bg-secondary/30 transition-colors">
                    <td className="text-sm font-mono">#{user.id}</td>
                    <td className="text-sm font-medium">{user.name}</td>
                    <td className="text-sm text-muted-foreground">{user.email}</td>
                    <td className="text-sm capitalize">{user.role}</td>
                    <td className="text-sm capitalize">{user.status}</td>
                    <td>
                      <Button variant="link" size="sm" className="text-primary p-0 h-auto">
                        Edit
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Role Descriptions */}
        <div className="dashboard-card p-6">
          <h3 className="text-xl font-semibold mb-4">Role Descriptions</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {Object.entries(roleDescriptions).map(([role, description]) => (
              <div key={role} className="rounded-xl bg-secondary/30 p-4">
                <h4 className="font-semibold capitalize mb-2">{role}</h4>
                <p className="text-sm text-muted-foreground">{description}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
