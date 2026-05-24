import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { buildApiUrl } from '@/config/api';

/**
 * Global SSE Hook
 * Connects to the /api/stream/global endpoint and populates the
 * React Query cache automatically. This allows all components to
 * instantly re-render with fresh data without polling the backend.
 */
export function useGlobalSSE() {
  const queryClient = useQueryClient();
  const isConnected = useRef(false);
  // Track the last known event total to detect genuinely new events
  const lastEventTotal = useRef<number | null>(null);

  useEffect(() => {
    // Only open one connection
    if (isConnected.current) return;

    const sseUrl = buildApiUrl('/stream/global');
    const eventSource = new EventSource(sseUrl);
    isConnected.current = true;

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);

        if (payload.error) {
          console.error('[Global SSE] Backend stream error:', payload.error);
          return;
        }

        // 1. System Status & Metrics (Used by Dashboard, Analytics, Settings)
        if (payload.status) {
          queryClient.setQueryData(['dashboard-system'], payload.status);
          queryClient.setQueryData(['settings-status'], payload.status);
        }
        if (payload.metrics) {
          queryClient.setQueryData(['settings-metrics'], payload.metrics);
        }

        // 2. Camera List (Used by Cameras, Dashboard, Analytics, LiveMonitoring)
        if (payload.cameras) {
          queryClient.setQueryData(['dashboard-cameras'], payload.cameras);
          queryClient.setQueryData(['cameras-list'], payload.cameras);
        }

        // 3. Event Stats (Used by Dashboard, Analytics)
        if (payload.stats) {
          queryClient.setQueryData(['dashboard-stats'], payload.stats);
          queryClient.setQueryData(['analytics-stats'], payload.stats);
        }

        // 4. Recent Events (Used by Dashboard & Header Bell icon)
        if (payload.recentEvents) {
          queryClient.setQueryData(['dashboard-recent-events'], payload.recentEvents);

          // SSE-driven Incidents page refresh:
          // If the total event count has grown since last SSE tick, a new incident
          // has arrived. Invalidate the Incidents query so it silently re-fetches
          // with the user's current filters still intact (HTTP GET, stateless).
          const newTotal: number = payload.recentEvents?.total ?? 0;
          if (lastEventTotal.current !== null && newTotal > lastEventTotal.current) {
            console.log(`[Global SSE] New event detected (${lastEventTotal.current} → ${newTotal}). Refreshing Incidents table.`);
            queryClient.invalidateQueries({ queryKey: ['incidents'] });
          }
          lastEventTotal.current = newTotal;
        }

        // 5. Live Bounding Boxes (Used by LiveMonitoring)
        if (payload.boxes) {
          queryClient.setQueryData(['live-boxes'], payload.boxes);
        }

        // 6. Alert History (Used by AlertContacts)
        if (payload.alerts) {
          queryClient.setQueryData(['alert-history'], payload.alerts);
        }

      } catch (err) {
        console.error('[Global SSE] Parse error:', err);
      }
    };

    eventSource.onerror = (error) => {
      console.error('[Global SSE] Connection lost. Reconnecting...', error);
      // EventSource auto-reconnects, but we log it
    };

    return () => {
      eventSource.close();
      isConnected.current = false;
    };
  }, [queryClient]);
}
