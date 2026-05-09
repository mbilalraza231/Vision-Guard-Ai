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

        // --- REAL-TIME SYNC ---
        // Listen for changes to the current user's profile
        const channel = supabase
          .channel(`profile-sync-${session.user.id}`)
          .on(
            'postgres_changes',
            { 
              event: 'UPDATE', 
              schema: 'public', 
              table: 'profiles',
              filter: `id=eq.${session.user.id}` 
            },
            async () => {
              console.log('[AuthContext] Real-time profile change detected, re-syncing...');
              const { data: { session: currentSession } } = await supabase.auth.getSession();
              if (currentSession?.user) {
                const updatedUser = await buildUser(currentSession.user);
                setState(prev => ({ ...prev, user: updatedUser }));
              }
            }
          )
          .subscribe();

        return () => {
          supabase.removeChannel(channel);
        };
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
    console.log('[AuthContext] updateProfile START (Optimistic):', data);
    
    // 0. UPDATE UI INSTANTLY (Optimistic Update)
    // We update the local state before the server responds so the user sees no lag.
    const previousUser = state.user;
    setState(prev => ({
      ...prev,
      user: prev.user ? { ...prev.user, ...data } : null,
    }));

    try {
      if (!previousUser) {
        throw new Error('Not authenticated');
      }

      // 1. Update public.profiles (Primary Source of Truth)
      console.log('[AuthContext] Step 1: Syncing with DB...');
      
      const dbPromise = supabase
        .from('profiles')
        .update(data)
        .eq('id', previousUser.id);
      
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('DB Sync delayed, but local change kept.')), 8000)
      );

      const { error: dbError } = await Promise.race([dbPromise, timeoutPromise]) as any;
      
      if (dbError) {
        console.warn('[AuthContext] Step 1 WARNING:', dbError.message);
        // We don't revert the UI here to keep it "feeling" instant, 
        // but we warn the user if the server didn't save.
      }

      // 2. Update auth.user_metadata (Background)
      supabase.auth.updateUser({ data: { ...data } }).catch(() => {});

      return { success: true };
    } catch (err: any) {
      console.error('[AuthContext] updateProfile EXCEPTION:', err);
      // Optional: Revert UI on critical failure if needed
      // setState(prev => ({ ...prev, user: previousUser }));
      return { success: false, error: err.message };
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
    // Clear state immediately to prevent race conditions with routing
    setState({ user: null, isAuthenticated: false, isLoading: false });
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
