import { useState, useEffect } from 'react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Plus, Loader2, AlertCircle, RefreshCw, Edit2, ShieldAlert } from 'lucide-react';
import { supabase } from '@/lib/supabase';
import type { User, UserRole } from '@/types';
import { toast } from 'sonner';

const roleDescriptions: Record<UserRole, string> = {
  admin: 'Full system access, user management, settings configuration',
  manager: 'View and manage incidents, access analytics, configure alerts',
  officer: 'View live feeds, respond to incidents, add investigation notes',
  viewer: 'Read-only access to live feeds and incident reports',
};

export default function Users() {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsers = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      // We try to fetch from 'profiles' table which should exist in public schema
      // and be synced with auth.users via triggers.
      const { data, error: sbError } = await supabase
        .from('profiles')
        .select('*')
        .order('name');

      if (sbError) throw sbError;

      if (data) {
        setUsers(data as User[]);
      }
    } catch (err: any) {
      console.error('Error fetching users:', err);
      setError(err.message);
      
      // Fallback message for setup
      if (err.message.includes('relation "profiles" does not exist')) {
        setError('Database Setup Required: The "profiles" table was not found in Supabase.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  return (
    <div className="min-h-screen">
      <Header title="User Management" showDateNav={false} />
      <div className="p-6">
        {/* Header Actions */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold">System Users</h2>
            <p className="text-muted-foreground text-sm">
              {users.length} active members in the system
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={fetchUsers} disabled={isLoading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button className="gap-2 shadow-lg shadow-primary/20">
              <Plus className="h-4 w-4" />
              Add User
            </Button>
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="mb-6 rounded-xl border border-destructive/50 bg-destructive/10 p-4 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-destructive mt-0.5" />
            <div>
              <p className="text-sm font-medium text-destructive">{error}</p>
              {error.includes('profiles') && (
                <p className="text-xs text-muted-foreground mt-1">
                  Please ensure you have created the <code className="bg-background px-1 rounded">profiles</code> table in your Supabase SQL editor and set up the synchronization triggers.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Users Table */}
        <div className="dashboard-card mb-6 overflow-hidden">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
              <Loader2 className="h-10 w-10 animate-spin mb-4 text-primary" />
              <p>Fetching secure user data...</p>
            </div>
          ) : users.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <div className="h-16 w-16 bg-secondary/50 rounded-full flex items-center justify-center mb-4">
                <ShieldAlert className="h-8 w-8 text-muted-foreground" />
              </div>
              <p className="text-lg font-medium">No users found</p>
              <p className="text-sm text-muted-foreground max-w-xs mx-auto mt-1">
                If this is a new installation, please check your database connection.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Joined</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id} className="hover:bg-secondary/30 transition-colors group">
                      <td>
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs">
                            {user.name.split(' ').map(n => n[0]).join('')}
                          </div>
                          <span className="text-sm font-medium">{user.name}</span>
                        </div>
                      </td>
                      <td className="text-sm text-muted-foreground">{user.email}</td>
                      <td>
                        <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                          user.role === 'admin' ? 'bg-severity-critical/10 text-severity-critical border border-severity-critical/20' :
                          user.role === 'manager' ? 'bg-primary/10 text-primary border border-primary/20' :
                          'bg-secondary text-muted-foreground border border-border'
                        }`}>
                          {user.role}
                        </span>
                      </td>
                      <td>
                        <div className="flex items-center gap-1.5">
                          <span className={`h-1.5 w-1.5 rounded-full ${user.status === 'active' ? 'bg-green-500' : 'bg-muted-foreground'}`} />
                          <span className="text-xs capitalize">{user.status}</span>
                        </div>
                      </td>
                      <td className="text-xs text-muted-foreground">
                        {user.createdAt ? new Date(user.createdAt).toLocaleDateString() : 'N/A'}
                      </td>
                      <td className="text-right">
                        <Button 
                          variant="ghost" 
                          size="icon" 
                          className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
                        >
                          <Edit2 className="h-3.5 w-3.5" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Role Descriptions */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {Object.entries(roleDescriptions).map(([role, description]) => (
            <div key={role} className="dashboard-card p-5 border border-white/5 hover:border-primary/20 transition-colors">
              <h4 className="font-bold capitalize mb-2 flex items-center justify-between">
                {role}
                <div className={`h-2 w-2 rounded-full ${
                  role === 'admin' ? 'bg-severity-critical' :
                  role === 'manager' ? 'bg-primary' :
                  'bg-muted-foreground'
                }`} />
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
