import { useQuery, useQueryClient } from '@tanstack/react-query';
import { apiService } from '@/services/api.service';
import type { SystemSettings } from '@/types';

const SETTINGS_CACHE_KEY = 'vg:settings:cache';

// Read cached settings synchronously from localStorage (instant, no API call needed)
export function getCachedSettings(): SystemSettings | null {
  try {
    const raw = localStorage.getItem(SETTINGS_CACHE_KEY);
    if (raw) return JSON.parse(raw) as SystemSettings;
  } catch {/* ignore */}
  return null;
}

// Write settings to localStorage cache
function setCachedSettings(data: SystemSettings) {
  try {
    localStorage.setItem(SETTINGS_CACHE_KEY, JSON.stringify(data));
  } catch {/* ignore */}
}

export function useSettings() {
  return useQuery({
    queryKey: ['system-settings'],
    queryFn: async () => {
      const data = await apiService.getData<SystemSettings>('/api/v1/settings');
      // Persist to localStorage so next render is instant
      setCachedSettings(data);
      return data;
    },
    // Use localStorage cache as initial data (synchronous — no loading flash)
    initialData: () => getCachedSettings() ?? undefined,
    staleTime: 5 * 60 * 1000, // 5 minutes before re-fetching
  });
}
