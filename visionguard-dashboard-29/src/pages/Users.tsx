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
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'viewer' as UserRole });
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.email || !form.password || !form.name) {
      toast.error('Please fill in all required fields.');
      return;
    }
    if (form.password.length < 8) {
      toast.error('Password must be at least 8 characters.');
      return;
    }

    setIsSubmitting(true);
    try {
      // signUp creates auth.users row → trigger automatically creates public.profiles row
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

      toast.success(`User "${form.name}" invited successfully! They will receive a confirmation email.`);
      onSuccess();
      onClose();
    } catch (err: any) {
      toast.error(err.message || 'Failed to create user.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl p-6 animate-in slide-in-from-bottom-4 duration-300">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-bold">Add New User</h2>
            <p className="text-xs text-muted-foreground mt-0.5">User will receive a confirmation email to activate their account.</p>
          </div>
          <button onClick={onClose} className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-secondary transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Name */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Full Name *</label>
            <input
              id="add-user-name"
              type="text"
              placeholder="John Smith"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40 transition-all"
              required
            />
          </div>

          {/* Email */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Email Address *</label>
            <input
              id="add-user-email"
              type="email"
              placeholder="john@visionguard.ai"
              value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40 transition-all"
              required
            />
          </div>

          {/* Password */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Temporary Password *</label>
            <div className="relative">
              <input
                id="add-user-password"
                type={showPassword ? 'text' : 'password'}
                placeholder="Min 8 characters"
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                className="w-full bg-secondary border border-border rounded-lg px-3 py-2 pr-10 text-sm outline-none focus:ring-2 focus:ring-primary/40 transition-all"
                required
                minLength={8}
              />
              <button
                type="button"
                onClick={() => setShowPassword(v => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </div>

          {/* Role */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Role *</label>
            <select
              id="add-user-role"
              value={form.role}
              onChange={e => setForm(f => ({ ...f, role: e.target.value as UserRole }))}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40 transition-all"
            >
              {(Object.keys(roleDescriptions) as UserRole[]).map(r => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
            <p className="text-xs text-muted-foreground mt-1">{roleDescriptions[form.role]}</p>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button type="submit" className="flex-1 gap-2" disabled={isSubmitting}>
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserCheck className="h-4 w-4" />}
              {isSubmitting ? 'Creating...' : 'Create User'}
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
  const [role, setRole] = useState<UserRole>(user.role);
  const [status, setStatus] = useState(user.status);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSave = async () => {
    setIsSubmitting(true);
    try {
      const { error } = await supabase
        .from('profiles')
        .update({ role, status })
        .eq('id', user.id);

      if (error) throw error;

      toast.success(`User "${user.name}" updated successfully.`);
      onSuccess();
      onClose();
    } catch (err: any) {
      toast.error(err.message || 'Failed to update user.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-sm bg-card border border-border rounded-2xl shadow-2xl p-6 animate-in slide-in-from-bottom-4 duration-300">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-bold">Edit User</h2>
            <p className="text-xs text-muted-foreground mt-0.5">{user.email}</p>
          </div>
          <button onClick={onClose} className="h-8 w-8 flex items-center justify-center rounded-lg hover:bg-secondary transition-colors">
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Avatar */}
        <div className="flex items-center gap-3 mb-5 p-3 bg-secondary/50 rounded-xl">
          <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm">
            {user.name.split(' ').map(n => n[0]).join('')}
          </div>
          <div>
            <p className="text-sm font-semibold">{user.name}</p>
            <p className="text-xs text-muted-foreground">Joined {user.createdAt ? new Date(user.createdAt).toLocaleDateString() : 'N/A'}</p>
          </div>
        </div>

        <div className="space-y-4">
          {/* Role */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Role</label>
            <select
              id="edit-user-role"
              value={role}
              onChange={e => setRole(e.target.value as UserRole)}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40 transition-all"
            >
              {(Object.keys(roleDescriptions) as UserRole[]).map(r => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
          </div>

          {/* Status */}
          <div>
            <label className="text-xs font-medium text-muted-foreground mb-1.5 block">Status</label>
            <select
              id="edit-user-status"
              value={status}
              onChange={e => setStatus(e.target.value as 'active' | 'inactive')}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-primary/40 transition-all"
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </div>
        </div>

        <div className="flex gap-3 pt-5">
          <Button type="button" variant="outline" className="flex-1" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button className="flex-1 gap-2" onClick={handleSave} disabled={isSubmitting}>
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserCheck className="h-4 w-4" />}
            {isSubmitting ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ─── Main Users Page ───────────────────────────────────────────────────────────
export default function Users() {
  const [users, setUsers] = useState<User[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);

  const fetchUsers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const { data, error: sbError } = await supabase
        .from('profiles')
        .select('*')
        .order('name');

      if (sbError) throw sbError;
      if (data) setUsers(data as User[]);
    } catch (err: any) {
      console.error('Error fetching users:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  return (
    <div className="min-h-screen">
      <Header title="User Management" showDateNav={false} />
      <div className="p-6">

        {/* Header Actions */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-semibold">System Users</h2>
            <p className="text-muted-foreground text-sm">
              {users.filter(u => u.status === 'active').length} active members in the system
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={fetchUsers} disabled={isLoading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
            <Button id="add-user-btn" className="gap-2 shadow-lg shadow-primary/20" onClick={() => setShowAddModal(true)}>
              <Plus className="h-4 w-4" />
              Add User
            </Button>
          </div>
        </div>

        {/* Error State */}
        {error && (
          <div className="mb-6 rounded-xl border border-destructive/50 bg-destructive/10 p-4 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-destructive mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-destructive">{error}</p>
              {error.includes('profiles') && (
                <p className="text-xs text-muted-foreground mt-1">
                  Please ensure you have created the <code className="bg-background px-1 rounded">profiles</code> table in your Supabase SQL editor.
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
              <p className="text-sm text-muted-foreground max-w-xs mx-auto mt-1 mb-4">
                Click "Add User" to create the first system user.
              </p>
              <Button className="gap-2" onClick={() => setShowAddModal(true)}>
                <Plus className="h-4 w-4" /> Add First User
              </Button>
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
                          <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-xs shrink-0">
                            {user.name?.split(' ').map(n => n[0]).join('') || '?'}
                          </div>
                          <span className="text-sm font-medium">{user.name}</span>
                        </div>
                      </td>
                      <td className="text-sm text-muted-foreground">{user.email}</td>
                      <td>
                        <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${roleBadgeClass[user.role] || roleBadgeClass.viewer}`}>
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
                        <div className="flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => setEditingUser(user)}
                            title="Edit user"
                          >
                            <Edit2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
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
          {(Object.entries(roleDescriptions) as [UserRole, string][]).map(([role, description]) => (
            <div key={role} className="dashboard-card p-5 border border-white/5 hover:border-primary/20 transition-colors">
              <h4 className="font-bold capitalize mb-2 flex items-center justify-between">
                {role}
                <div className={`h-2 w-2 rounded-full ${
                  role === 'admin' ? 'bg-red-400' :
                  role === 'manager' ? 'bg-primary' :
                  role === 'officer' ? 'bg-blue-400' :
                  'bg-muted-foreground'
                }`} />
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Modals */}
      {showAddModal && (
        <AddUserModal
          onClose={() => setShowAddModal(false)}
          onSuccess={fetchUsers}
        />
      )}
      {editingUser && (
        <EditUserModal
          user={editingUser}
          onClose={() => setEditingUser(null)}
          onSuccess={fetchUsers}
        />
      )}
    </div>
  );
}
