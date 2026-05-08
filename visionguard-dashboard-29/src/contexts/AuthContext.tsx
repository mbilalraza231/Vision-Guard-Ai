import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { supabase } from '@/lib/supabase';
import type { User, AuthState, LoginCredentials, UserRole } from '@/types';

interface AuthContextType extends AuthState {
  login: (credentials: LoginCredentials) => Promise<{ success: boolean; error?: string }>;
  register: (credentials: LoginCredentials & { name: string; role: UserRole }) => Promise<{ success: boolean; error?: string }>;
  logout: () => Promise<void>;
  resetPassword: (email: string) => Promise<{ success: boolean; error?: string }>;
  updatePassword: (password: string) => Promise<{ success: boolean; error?: string }>;
  updateProfile: (data: { name?: string; avatar?: string }) => Promise<{ success: boolean; error?: string }>;
}

const AuthContext = createContext<AuthContextType | null>(null);

// Fetch the full profile from public.profiles (single source of truth)
async function fetchProfile(userId: string): Promise<Partial<User>> {
  try {
    const { data, error } = await supabase
      .from('profiles')
      .select('name, role, status, avatar, email, "createdAt"')
      .eq('id', userId)
      .single();
    
    if (error) {
      console.error('[AuthContext] Error fetching profile:', error);
      return {};
    }
    return data || {};
  } catch (err) {
    console.error('[AuthContext] Fetch profile exception:', err);
    return {};
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isAuthenticated: false,
    isLoading: true,
  });

  // Build the full User object by combining auth session + public.profiles
  const buildUser = async (sbUser: any): Promise<User> => {
    const profile = await fetchProfile(sbUser.id);
    return {
      id: sbUser.id,
      email: sbUser.email || '',
      name: profile.name || sbUser.user_metadata?.name || 'User',
      role: (profile.role as UserRole) || sbUser.user_metadata?.role || 'viewer',
      status: profile.status || 'active',
      avatar: profile.avatar || sbUser.user_metadata?.avatar || undefined,
      createdAt: (profile as any)?.createdAt || sbUser.created_at,
    };
  };

  useEffect(() => {
    const initializeAuth = async () => {
      const { data: { session } } = await supabase.auth.getSession();

      if (session?.user) {
        const user = await buildUser(session.user);
        setState({ user, isAuthenticated: true, isLoading: false });
      } else {
        setState(prev => ({ ...prev, isLoading: false }));
      }

      const { data: { subscription } } = supabase.auth.onAuthStateChange(async (_event, session) => {
        if (session?.user) {
          const user = await buildUser(session.user);
          setState({ user, isAuthenticated: true, isLoading: false });
        } else {
          setState({ user: null, isAuthenticated: false, isLoading: false });
        }
      });

      return () => subscription.unsubscribe();
    };

    initializeAuth();
  }, []);

  const login = async (credentials: LoginCredentials) => {
    try {
      const { error } = await supabase.auth.signInWithPassword({
        email: credentials.email,
        password: credentials.password,
      });
      if (error) return { success: false, error: error.message };
      return { success: true };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  };

  const register = async (credentials: LoginCredentials & { name: string; role: UserRole }) => {
    try {
      const { error } = await supabase.auth.signUp({
        email: credentials.email,
        password: credentials.password,
        options: { data: { name: credentials.name, role: credentials.role } },
      });
      if (error) return { success: false, error: error.message };
      return { success: true };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  };

  // Update profile in public.profiles AND auth.user_metadata — keeps both in sync
  const updateProfile = async (data: { name?: string; avatar?: string }) => {
    console.log('[AuthContext] updateProfile called with:', data);
    
    try {
      if (!state.user) {
        console.error('[AuthContext] Update failed: Not authenticated');
        return { success: false, error: 'Not authenticated' };
      }

      // 1. Update public.profiles (Primary Source of Truth)
      console.log('[AuthContext] Step 1: Updating profiles table...');
      const { error: dbError } = await supabase
        .from('profiles')
        .update(data)
        .eq('id', state.user.id);
      
      if (dbError) {
        console.error('[AuthContext] Step 1 FAILED:', dbError.message);
        throw new Error(`Database: ${dbError.message}`);
      }
      console.log('[AuthContext] Step 1 SUCCESS');

      // 2. Update auth.user_metadata (Background Sync)
      // We do NOT 'await' this anymore because it hangs in some environments.
      // This keeps the session metadata in sync eventually without blocking the UI.
      console.log('[AuthContext] Step 2: Triggering Auth metadata sync (Background)...');
      supabase.auth.updateUser({ data: { ...data } })
        .then(({ error }) => {
          if (error) console.warn('[AuthContext] Background Auth sync failed:', error.message);
          else console.log('[AuthContext] Background Auth sync SUCCESS');
        })
        .catch(err => console.warn('[AuthContext] Background Auth sync exception:', err));

      // 3. Update local state immediately
      console.log('[AuthContext] Step 3: Syncing local state');
      setState(prev => ({
        ...prev,
        user: prev.user ? { ...prev.user, ...data } : null,
      }));

      return { success: true };
    } catch (err: any) {
      console.error('[AuthContext] updateProfile EXCEPTION:', err);
      return { success: false, error: err.message || 'An unexpected error occurred' };
    }
  };

  const resetPassword = async (email: string) => {
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/auth/update-password`,
      });
      if (error) return { success: false, error: error.message };
      return { success: true };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  };

  const updatePassword = async (password: string) => {
    try {
      const { error } = await supabase.auth.updateUser({ password });
      if (error) return { success: false, error: error.message };
      return { success: true };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  };

  const logout = async () => {
    await supabase.auth.signOut();
  };

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, resetPassword, updatePassword, updateProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
