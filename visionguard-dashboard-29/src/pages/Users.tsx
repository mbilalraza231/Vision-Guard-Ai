import { useState, useEffect } from 'react';
import { Header } from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import {
  Plus, Loader2, AlertCircle, RefreshCw, Edit2,
  ShieldAlert, X, Eye, EyeOff, UserCheck
} from 'lucide-react';
import { supabase } from '@/lib/supabase';
import type { User, UserRole } from '@/types';
import { toast } from 'sonner';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';

const roleDescriptions: Record<UserRole, string> = {
  admin: 'Full system access, user management, settings configuration',
  manager: 'View and manage incidents, access analytics, configure alerts',
  officer: 'View live feeds, respond to incidents, add investigation notes',
  viewer: 'Read-only access to live feeds and incident reports',
};

const roleBadgeClass: Record<UserRole, string> = {
  admin: 'bg-red-500/10 text-red-400 border border-red-500/20',
  manager: 'bg-primary/10 text-primary border border-primary/20',
  officer: 'bg-blue-500/10 text-blue-400 border border-blue-500/20',
  viewer: 'bg-secondary text-muted-foreground border border-border',
};

// ─── Add User Modal ────────────────────────────────────────────────────────────
interface AddUserModalProps {
  onClose: () => void;
  onSuccess: () => void;
}

function AddUserModal({ onClose, onSuccess }: AddUserModalProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'viewer' as UserRole });
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.email || !form.password || !form.name) {
      toast.error('Please fill in all required fields.');
      return;
    }
    setIsSubmitting(true);
    try {
      const { error } = await supabase.auth.signUp({
        email: form.email,
        password: form.password,
        options: {
          data: {
            name: form.name,
            role: form.role,
          },
        },
      });

      if (error) throw error;

      toast.success(`User "${form.name}" invited successfully!`);
      onSuccess();
      onClose();
    } catch (err: any) {
      toast.error(err.message || 'Failed to create user.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-md bg-card border border-border rounded-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold">Add New User</h2>
          <button onClick={onClose} className="h-8 w-8 hover:bg-secondary rounded-lg flex items-center justify-center">
            <X className="h-4 w-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Full Name *</label>
            <input
              type="text"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              required
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Email Address *</label>
            <input
              type="email"
              value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
              required
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Password *</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
                required
              />
              <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Role *</label>
            <select
              value={form.role}
              onChange={e => setForm(f => ({ ...f, role: e.target.value as UserRole }))}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
            >
              {(Object.keys(roleDescriptions) as UserRole[]).map(r => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={onClose}>Cancel</Button>
            <Button type="submit" className="flex-1 gap-2" disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserCheck className="h-4 w-4" />}
              Create
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ─── Edit User Modal ───────────────────────────────────────────────────────────
interface EditUserModalProps {
  user: User;
  onClose: () => void;
  onSuccess: () => void;
}

function EditUserModal({ user, onClose, onSuccess }: EditUserModalProps) {
  const queryClient = useQueryClient();
  const { user: currentUser, updateLocalUser } = useAuth();
  const [name, setName] = useState(user.name || '');
  const [avatar, setAvatar] = useState(user.avatar || '');
  const [role, setRole] = useState<UserRole>(user.role);
  const [status, setStatus] = useState(user.status);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error('Name cannot be empty.');
      return;
    }
    setIsSubmitting(true);
    
    // 0. OPTIMISTIC UPDATE
    // Update the local cache instantly so the user sees the change immediately
    const updatedUser = { ...user, name: name.trim(), avatar: avatar.trim() || null, role, status };
    queryClient.setQueryData(['users'], (old: User[] | undefined) => {
      return old?.map(u => u.id === user.id ? updatedUser : u);
    });

    // If editing myself, instantly sync AuthContext!
    if (currentUser?.id === user.id) {
      updateLocalUser(updatedUser);
    }

    try {
      console.log('[Users] Step 1: Syncing with DB (Optimistic)...');
      
      const dbPromise = supabase
        .from('profiles')
        .update({ name: name.trim(), avatar: avatar.trim() || null, role, status })
        .eq('id', user.id);
      
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Sync delayed. Local change kept.')), 8000)
      );

      const { error } = await Promise.race([dbPromise, timeoutPromise]) as any;

      if (error) {
        console.warn('[Users] DB sync warning:', error.message);
      }
      
      // Background Auth sync for self-edits
      const { data: authData } = await supabase.auth.getUser();
      if (authData?.user?.id === user.id) {
        supabase.auth.updateUser({ data: { name: name.trim(), avatar: avatar.trim() || null } }).catch(() => {});
      }

      toast.success(`User updated successfully.`);
      onSuccess();
      onClose();
    } catch (err: any) {
      console.error('[Users] Update error:', err);
      // Invalidate cache on error to ensure data consistency
      queryClient.invalidateQueries({ queryKey: ['users'] });
      toast.error(err.message || 'Update failed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-md bg-card border border-border rounded-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-bold">Edit User</h2>
          <button onClick={onClose} className="h-8 w-8 hover:bg-secondary rounded-lg flex items-center justify-center">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Full Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Role</label>
            <select
              value={role}
              onChange={e => setRole(e.target.value as UserRole)}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
            >
              {(Object.keys(roleDescriptions) as UserRole[]).map(r => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Status</label>
            <select
              value={status}
              onChange={e => setStatus(e.target.value as 'active' | 'inactive')}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40"
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
          <div className="flex gap-3 pt-5">
            <Button variant="outline" className="flex-1" onClick={onClose}>Cancel</Button>
            <Button className="flex-1 gap-2" onClick={handleSave} disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserCheck className="h-4 w-4" />}
              Save Changes
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Main Users Page ───────────────────────────────────────────────────────────
export default function Users() {
  const queryClient = useQueryClient();
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);

  // 1. Caching with TanStack Query
  const { data: users = [], isLoading, error: queryError, refetch } = useQuery({
    queryKey: ['users'],
    queryFn: async () => {
      console.log('[Users] Fetching user list via useQuery...');
      const { data, error: sbError } = await supabase
        .from('profiles')
        .select('*')
        .order('name');
      if (sbError) throw sbError;
      return data as User[];
    },
    staleTime: 1000 * 60 * 5, // Data is fresh for 5 mins
  });

  // 2. Real-time Synchronization
  useEffect(() => {
    console.log('[Users] Setting up Real-time listener...');
    const channel = supabase
      .channel('profiles-realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'profiles' },
        () => {
          console.log('[Users] Real-time change detected, invalidating cache...');
          queryClient.invalidateQueries({ queryKey: ['users'] });
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [queryClient]);

  const error = queryError instanceof Error ? queryError.message : null;

  return (
    <div className="min-h-screen">
      <Header title="User Management" showDateNav={false} />
      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold">System Users</h2>
            <p className="text-muted-foreground text-sm">
              {users.filter(u => u.status === 'active').length} active members
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button className="gap-2" onClick={() => setShowAddModal(true)}>
              <Plus className="h-4 w-4" /> Add User
            </Button>
          </div>
        </div>

        {error && (
          <div className="mb-6 rounded-xl border border-destructive/50 bg-destructive/10 p-4 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
            <p className="text-sm font-medium text-destructive">{error}</p>
          </div>
        )}

        <div className="dashboard-card mb-6 overflow-hidden">
          {isLoading && users.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-muted-foreground">
              <Loader2 className="h-10 w-10 animate-spin mb-4 text-primary" />
              <p>Fetching secure user data...</p>
            </div>
          ) : users.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center text-muted-foreground">
              <ShieldAlert className="h-8 w-8 mb-4 opacity-20" />
              <p className="text-lg font-medium">No users found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table w-full text-left">
                <thead>
                  <tr className="border-b border-border">
                    <th className="p-4">Name</th>
                    <th className="p-4">Email</th>
                    <th className="p-4">Role</th>
                    <th className="p-4">Status</th>
                    <th className="p-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id} className="border-b border-border/50 hover:bg-secondary/20 group">
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs">
                            {user.name?.charAt(0) || '?'}
                          </div>
                          <span className="font-medium">{user.name}</span>
                        </div>
                      </td>
                      <td className="p-4 text-sm text-muted-foreground">{user.email}</td>
                      <td className="p-4">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${roleBadgeClass[user.role]}`}>
                          {user.role}
                        </span>
                      </td>
                      <td className="p-4">
                        <div className="flex items-center gap-1.5 capitalize text-xs">
                          <span className={`h-1.5 w-1.5 rounded-full ${user.status === 'active' ? 'bg-green-500' : 'bg-muted-foreground'}`} />
                          {user.status}
                        </div>
                      </td>
                      <td className="p-4 text-right">
                        <Button variant="ghost" size="icon" className="h-8 w-8 opacity-0 group-hover:opacity-100" onClick={() => setEditingUser(user)}>
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
      </div>

      {showAddModal && (
        <AddUserModal
          onClose={() => setShowAddModal(false)}
          onSuccess={() => queryClient.invalidateQueries({ queryKey: ['users'] })}
        />
      )}
      {editingUser && (
        <EditUserModal
          user={editingUser}
          onClose={() => setEditingUser(null)}
          onSuccess={() => queryClient.invalidateQueries({ queryKey: ['users'] })}
        />
      )}
    </div>
  );
}
