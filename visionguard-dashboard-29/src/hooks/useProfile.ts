import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import { useAuth } from '@/contexts/AuthContext';
import type { User, UserRole } from '@/types';
import { useEffect } from 'react';

// 1. Fetching Hook (Server State SSOT)
export function useProfile() {
  const { session } = useAuth();
  
  return useQuery({
    queryKey: ['profile', session?.user?.id],
    queryFn: async (): Promise<User | null> => {
      if (!session?.user?.id) return null;
      
      // Fetch strictly from public.profiles
      const { data, error } = await supabase
        .from('profiles')
        .select('name, role, status, avatar, email, "createdAt"')
        .eq('id', session.user.id)
        .single();
        
      if (error) {
        // If the profile doesn't exist yet (e.g. old user before triggers), fallback gracefully
        if (error.code === 'PGRST116') {
          console.warn('[useProfile] No profile found in DB for user, using fallback.');
          return {
            id: session.user.id,
            email: session.user.email || '',
            name: session.user.user_metadata?.name || 'Unknown User',
            role: (session.user.user_metadata?.role as UserRole) || 'viewer',
            status: 'active',
            createdAt: session.user.created_at,
          };
        }
        console.error('[useProfile] Fetch error:', error);
        throw error;
      }
      
      // Merge Auth constraints with Profile DB Truth
      return {
        id: session.user.id,
        email: data?.email || session.user.email || '',
        name: data?.name || 'User',
        role: (data?.role as UserRole) || 'viewer',
        status: data?.status || 'active',
        avatar: data?.avatar || undefined,
        createdAt: data?.createdAt || session.user.created_at,
      };
    },
    enabled: !!session?.user?.id,
    staleTime: 1000 * 60 * 5, // Cache profile for 5 minutes
    retry: 0, // Fail fast if Supabase rejects the connection
  });
}

// 2. Mutation Hook (Optimistic Caching without mirrored metadata)
export function useUpdateProfile() {
  const queryClient = useQueryClient();
  const { session } = useAuth();

  return useMutation({
    mutationFn: async (data: { name?: string; avatar?: string }) => {
      if (!session?.user?.id) throw new Error('No user session');
      
      // Strict single source of truth update (no auth.users mirroring)
      const { error } = await supabase
        .from('profiles')
        .update(data)
        .eq('id', session.user.id);
        
      if (error) throw error;
      return data;
    },
    onMutate: async (newData) => {
      if (!session?.user?.id) return;
      
      const queryKey = ['profile', session.user.id];
      await queryClient.cancelQueries({ queryKey });
      
      const previousProfile = queryClient.getQueryData<User>(queryKey);
      
      // Optimistically update current user cache
      queryClient.setQueryData<User | undefined>(queryKey, (old) => {
        if (!old) return old;
        return { ...old, ...newData };
      });
      
      // Optimistically update the global users list cache
      queryClient.setQueryData(['users'], (old: User[] | undefined) => {
        if (!old) return old;
        return old.map(u => u.id === session.user.id ? { ...u, ...newData } : u);
      });
      
      return { previousProfile };
    },
    onError: (err, newData, context) => {
      if (context?.previousProfile && session?.user?.id) {
        queryClient.setQueryData(['profile', session.user.id], context.previousProfile);
      }
    },
    onSettled: () => {
      if (session?.user?.id) {
        queryClient.invalidateQueries({ queryKey: ['profile', session.user.id] });
      }
      queryClient.invalidateQueries({ queryKey: ['users'] });
    },
  });
}

// 3. Real-time Subscription Hook
export function useProfileRealtimeSync() {
  const { session } = useAuth();
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!session?.user?.id) return;

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
        () => {
          console.log('[useProfileRealtimeSync] Remote profile update detected, invalidating cache...');
          queryClient.invalidateQueries({ queryKey: ['profile', session.user.id] });
          // Optionally invalidate the global users list if needed
          queryClient.invalidateQueries({ queryKey: ['users'] });
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [session?.user?.id, queryClient]);
}
